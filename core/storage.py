"""Atomic files, process locks and recoverable multi-file changes."""
import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

_UNSPECIFIED = object()


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = content.encode('utf-8') if isinstance(content, str) else content
    fd, temporary = tempfile.mkstemp(prefix='.mathweave-write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class VaultLock:
    """OS locks are automatically released even if a process crashes."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.stream = None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        if (self.root / '.mathweave.lock').is_symlink():
            raise ValueError('仓库锁文件不能是符号链接。')
        self.stream = open(self.root / '.mathweave.lock', 'a+b')
        if self.stream.seek(0, 2) == 0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as err:
            self.stream.close()
            self.stream = None
            raise RuntimeError('这个仓库正由另一项任务写入，请稍后重试。') from err
        return self

    def __exit__(self, *args):
        if self.stream:
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()


class FileTransaction:
    def __init__(self, root, label='save', backup=True, cancel_check=None):
        self.root = Path(root).resolve()
        self.label = label
        self.backup = backup
        self.cancel_check = cancel_check or (lambda: False)
        self.changes = {}
        self.run_id = datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '-' + uuid.uuid4().hex[:8]
        self.backup_dir = self.root / '.agent_backup' / 'transactions' / self.run_id
        if not self.backup_dir.resolve().is_relative_to(self.root):
            raise ValueError('备份目录不能指向仓库外。')

    def stage(self, path, content, expected=_UNSPECIFIED):
        path = Path(path)
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError('写入目标不在所选仓库内，或是符号链接。')
        before = path.read_bytes() if path.exists() else None
        if expected is not _UNSPECIFIED and digest(before) != expected:
            raise RuntimeError(f'「{path.name}」在分析后发生变化，本次未写入，请重新扫描。')
        after = content.encode('utf-8') if isinstance(content, str) else content
        if before == after:
            return
        previous = self.changes.get(path)
        self.changes[path] = (previous[0] if previous else before, after)

    def commit(self, already_locked=False):
        if not already_locked:
            with VaultLock(self.root):
                return self.commit(already_locked=True)
        if self.cancel_check():
            raise InterruptedError('已取消，没有写入笔记。')
        for path, (before, after) in self.changes.items():
            current = path.read_bytes() if path.exists() else None
            if current != before:
                raise RuntimeError(f'「{path.name}」已被编辑，请重新扫描后再操作。')
        if not self.changes:
            return None
        manifest = dict(id=self.run_id, label=self.label, root=str(self.root), status='prepared', files=[])
        if self.backup:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        for index, (path, (before, after)) in enumerate(self.changes.items()):
            backup_name = f'{index:05}.bin'
            manifest['files'].append(dict(path=path.relative_to(self.root).as_posix(), existed=before is not None,
                                          before=digest(before), after=digest(after), backup=backup_name))
            if self.backup and before is not None:
                atomic_write(self.backup_dir / backup_name, before)
        manifest_path = self.backup_dir / 'manifest.json'
        if self.backup:
            atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
        written = []
        try:
            for path, (before, after) in self.changes.items():
                if self.cancel_check():
                    raise InterruptedError('已取消，正在恢复本次修改。')
                current = path.read_bytes() if path.exists() else None
                if current != before:
                    raise RuntimeError(f'「{path.name}」在写入过程中被编辑。')
                if after is None:
                    path.unlink()
                else:
                    atomic_write(path, after)
                written.append(path)
            manifest['status'] = 'committed'
            if self.backup:
                atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
        except Exception:
            conflicts = []
            for path in reversed(written):
                before, after = self.changes[path]
                current = path.read_bytes() if path.exists() else None
                if current != after:
                    conflicts.append(path.name)
                    continue
                try:
                    if before is None:
                        if path.exists():path.unlink()
                    else:atomic_write(path, before)
                except OSError:
                    conflicts.append(path.name)
            manifest['status'] = 'rollback-conflict' if conflicts else 'rolled-back'
            manifest['conflicts'] = conflicts
            if self.backup:
                atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
            if conflicts:
                raise RuntimeError('写入失败，部分文件未能自动恢复：'+', '.join(conflicts)+'。请核对备份：'+str(self.backup_dir)) from None
            raise
        return str(self.backup_dir) if self.backup else None


def recover_incomplete(root, already_locked=False):
    """Recover interrupted writes only while files still match this transaction."""
    root = Path(root).resolve()
    if not already_locked:
        with VaultLock(root):
            return recover_incomplete(root, already_locked=True)
    recovered = []
    for manifest_path in sorted((root / '.agent_backup' / 'transactions').glob('*/manifest.json')):
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('status') not in ('prepared', 'rollback-conflict'):
            continue
        pending = []
        for entry in manifest['files']:
            path = root / entry['path']
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('恢复记录包含不合法路径。')
            current = path.read_bytes() if path.exists() else None
            if digest(current) == entry['before']:
                continue
            if digest(current) != entry['after']:
                raise RuntimeError(f'上次写入中断，且「{path.name}」随后被编辑。请从 {manifest_path.parent} 手动核对恢复后再操作。')
            backup = manifest_path.parent / entry['backup']
            if backup.is_symlink() or not backup.resolve().is_relative_to(manifest_path.parent.resolve()):
                raise ValueError('恢复记录包含不合法备份路径。')
            before = backup.read_bytes() if entry['existed'] else None
            if digest(before) != entry['before']:
                raise ValueError('中断操作的备份校验失败。')
            pending.append((path, before))
        for path, before in pending:
            if before is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, before)
        manifest['status'] = 'recovered'
        atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
        recovered.append(str(manifest_path.parent))
    return recovered


def restore_transaction(root, backup_dir):
    root = Path(root).resolve()
    backup_dir = Path(backup_dir).resolve()
    if not backup_dir.is_relative_to(root / '.agent_backup' / 'transactions'):
        raise ValueError('恢复快照不在所选仓库内。')
    manifest = json.loads((backup_dir / 'manifest.json').read_text(encoding='utf-8'))
    if Path(manifest['root']).resolve() != root or manifest['status'] != 'committed':
        raise ValueError('这个快照不是可撤销的已完成操作。')
    with VaultLock(root):
        transaction = FileTransaction(root, label='restore', backup=True)
        for entry in manifest['files']:
            path = (root / entry['path']).resolve()
            if not path.is_relative_to(root):
                raise ValueError('快照包含不合法路径。')
            current = path.read_bytes() if path.exists() else None
            if digest(current) != entry['after']:
                raise RuntimeError(f'「{path.name}」整理后又被编辑；为保留后续修改，自动撤销已停止。原内容仍在备份中。')
            backup_file = (backup_dir / entry['backup']).resolve()
            if not backup_file.is_relative_to(backup_dir):
                raise ValueError('不合法的备份文件名。')
            content = backup_file.read_bytes() if entry['existed'] else None
            if digest(content) != entry['before']:
                raise ValueError('备份文件校验失败。')
            transaction.stage(path, content)
        result = transaction.commit(already_locked=True)
        manifest['status'] = 'restored'
        atomic_write(backup_dir / 'manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        return result
