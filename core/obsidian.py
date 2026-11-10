"""Safe Obsidian notes, semantic links, conversation maps and incremental saves."""
import hashlib
import json
import os
import re
import shutil
import tempfile
import copy
import difflib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
import yaml
from core.extractor import MathConcept
from core.logger import get_logger
from core.formatting import format_math_content
from core.storage import atomic_write, FileTransaction, VaultLock, digest, recover_incomplete
logger = get_logger()


def sanitize_filename(name):
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip().rstrip(". ")[:96] or "未命名"
    if re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", cleaned, re.I):
        cleaned = "_" + cleaned
    if cleaned != name:
        cleaned += "-" + hashlib.sha256(name.encode()).hexdigest()[:6]
    return cleaned


def make_wikilink(text):
    return text.replace("]]", "] ]").replace("|", "｜")


def wikilink(title, targets=None):
    target = (targets or {}).get(title, sanitize_filename(title))
    label = make_wikilink(title)
    return f"[[{target}]]" if target == label else f"[[{target}|{label}]]"


def split_frontmatter(content):
    match = re.match(r"\A\ufeff?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", content, re.S)
    if not match:
        return {}, content.strip()
    props = yaml.safe_load(match.group(1)) or {}
    if not isinstance(props, dict):
        raise ValueError("笔记属性必须是 YAML 对象。")
    return props, content[match.end():].strip()


def compose_note(props, body):
    header = yaml.safe_dump(props, allow_unicode=True, sort_keys=False, width=1000).strip()
    return f"---\n{header}\n---\n\n{body.strip()}\n"


def yaml_list(items):
    return json.dumps(list(dict.fromkeys(str(x).strip() for x in items if str(x).strip())), ensure_ascii=False)


def build_concept_note(concept, vault_path="", targets=None, source="", map_title="", styled=True):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    props = dict(title=concept.title, kind=concept.kind, category=concept.category, created=now, updated=now,
                 tags=list(dict.fromkeys(concept.tags + [concept.kind, concept.category, "数学"])),
                 related=[wikilink(x, targets) for x in concept.related])
    if concept.source_refs:
        props['source_refs'] = concept.source_refs
    props['review_status'] = '教学示例' if source == '内置教学示例' else '待核对'
    if styled:
        props['mathweave_format'] = 'native-callouts-v1'
    if source:
        props["sources"] = [source]
    if map_title:
        props["conversation_maps"] = [wikilink(map_title, targets)]
    body = [f"# {concept.title}", "", format_math_content(concept.content, concept.kind) if styled else concept.content.strip()]
    if concept.relations:
        body.extend(["", "## 知识联系", ""])
        for rel in concept.relations:
            reason = rel.get("reason", "").strip()
            suffix = f"：{reason}" if reason else ""
            body.append(f"- **{rel.get('relation', '相关')}** {wikilink(rel['target'], targets)}{suffix}")
    elif concept.related:
        body.extend(["", "## 关联概念", ""] + [f"- {wikilink(x, targets)}" for x in concept.related])
    if map_title:
        body.extend(["", f"> 本次对话的知识全貌：{wikilink(map_title, targets)}"])
    return compose_note(props, "\n".join(body))


def build_index_note(categories, vault_path="", title="数学知识索引"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# {title}", "", "按数学分支浏览你的知识笔记。", ""]
    for cat, titles in sorted(categories.items()):
        lines.extend([f"## {cat}", ""] + [f"- [[{make_wikilink(x)}]]" for x in sorted(titles)] + [""])
    return compose_note(dict(title=title, category="索引", kind="索引", created=now, updated=now, tags=["数学", "索引"]), "\n".join(lines))


def build_conversation_map(result, title, targets):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = [f"# {title}", "", result.summary or "本次对话提取的数学知识及其联系。", "", "## 知识点", ""]
    body.extend(f"- {wikilink(c.title, targets)} · {c.category}" for c in result.concepts)
    body.extend(["", "## 知识联系", ""])
    if not result.connections:
        body.append("本次对话没有明确说明知识点之间的关系，因此未自动添加联系。")
    for edge in result.connections:
        reason = edge.get("reason", "")
        body.append(f"- {wikilink(edge['source'], targets)} **{edge['relation']}** {wikilink(edge['target'], targets)}" + (f"：{reason}" if reason else ""))
    return compose_note(dict(title=title, kind="知识地图", category="知识地图", created=now, updated=now,
                             tags=["数学", "知识地图"], source=result.source), "\n".join(body))


def _atomic_write(path, text):
    atomic_write(path, text)


class VaultManager:
    def __init__(self, vault_path, notes_subfolder="数学笔记", backup_before_update=True, index_note_name="数学知识索引"):
        self.vault_root = Path(vault_path).expanduser().resolve()
        self.notes_dir = (self.vault_root / notes_subfolder).resolve()
        if not self.notes_dir.is_relative_to(self.vault_root):
            raise ValueError("笔记子目录必须位于所选 Obsidian 仓库内。")
        self.index_note_name = index_note_name
        self.index_path = self.notes_dir / f"{sanitize_filename(index_note_name)}.md"
        self.backup_dir = self.vault_root / ".agent_backup"
        self.meta_path = self.notes_dir / ".agent_meta.json"
        self.backup_before_update = backup_before_update
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.meta = self._load_meta()
        self.last_status = ""

    def _load_meta(self):
        if self.meta_path.exists():
            data = json.loads(self.meta_path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("笔记元数据格式错误，请先恢复 .agent_meta.json。")
            return data
        return {}

    def _save_meta(self):
        _atomic_write(self.meta_path, json.dumps(self.meta, ensure_ascii=False, indent=2))

    def note_path(self, title):
        recorded = self.meta.get(title, {}).get("filename")
        if isinstance(recorded,str) and not Path(recorded).is_absolute():
            path = self.notes_dir / recorded
            if path.resolve().is_relative_to(self.notes_dir):
                return path
        safe = sanitize_filename(title)
        path = self.notes_dir / f"{safe}.md"
        if path == self.index_path:
            path = self.notes_dir / f"{safe}-{self.compute_hash(title)[:6]}.md"
        if path.exists():
            props, _ = split_frontmatter(path.read_text(encoding="utf-8"))
            if props.get("title", path.stem) != title:
                path = self.notes_dir / f"{safe}-{self.compute_hash(title)[:6]}.md"
        return path

    def exists(self, title):
        return self.note_path(title).exists()

    def save_note(self, title, content, concept_hash=""):
        path = self.note_path(title)
        if path.exists() and concept_hash and self.meta.get(title, {}).get("hash") == concept_hash:
            self.last_status = "skipped"
            return path
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        merged = self._merge_notes(old, content) if old else content
        if old and old == merged:
            self.last_status = "skipped"
            return path
        if old:
            self._backup(path)
        _atomic_write(path, merged)
        self.last_status = "updated" if old else "created"
        self.meta[title] = dict(hash=concept_hash or self.compute_hash(content), filename=path.name, updated=datetime.now().isoformat())
        self._save_meta()
        return path

    def _backup(self, path):
        if self.backup_before_update:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            shutil.copy2(path, self.backup_dir / f"{path.stem}_{ts}.md")

    def _merge_notes(self, old, new):
        old_props, old_body = split_frontmatter(old)
        new_props, new_body = split_frontmatter(new)
        props = dict(old_props)
        for key, value in new_props.items():
            if key in ("created", "updated"):
                continue
            if isinstance(value, list):
                previous = props.get(key, [])
                previous = previous if isinstance(previous, list) else [previous]
                props[key] = []
                seen = set()
                for item in previous + value:
                    marker = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
                    if marker not in seen:
                        props[key].append(item)
                        seen.add(marker)
            else:
                props[key] = value
        body = old_body
        if new_body and new_body not in old_body:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            body += f"\n\n---\n\n## 补充记录 · {stamp}\n\n{new_body}"
        if props == old_props and body == old_body:
            return old
        props["created"] = old_props.get("created", new_props.get("created", ""))
        props["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        return compose_note(props, body)

    def update_index(self, categories):
        content = build_index_note(categories, str(self.vault_root), self.index_note_name)
        if self.index_path.exists():
            old_props, old_body = split_frontmatter(self.index_path.read_text(encoding="utf-8"))
            props, body = split_frontmatter(content)
            if body == old_body:
                return
            props["created"] = old_props.get("created", props["created"])
            content = compose_note(props, body)
            self._backup(self.index_path)
        _atomic_write(self.index_path, content)

    def get_all_notes(self):
        return {p.relative_to(self.notes_dir).with_suffix('').as_posix(): p.read_text(encoding="utf-8-sig") for p in self.notes_dir.rglob("*.md") if p != self.index_path and not any(part.startswith('.') for part in p.relative_to(self.notes_dir).parts) and not p.is_symlink() and p.resolve().is_relative_to(self.notes_dir)}

    def compute_hash(self, content):
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def get_categories_from_notes(self):
        categories = {}
        for title, body in self.get_all_notes().items():
            try:
                props, _ = split_frontmatter(body)
            except (ValueError,yaml.YAMLError):
                logger.warning("跳过属性损坏的笔记: %s", title)
                continue
            if props.get("kind") not in ("索引", "知识地图", "重定向"):
                categories.setdefault(str(props.get("category", "未分类")), []).append(title)
        return categories


@dataclass
class SavePlan:
    root: str
    directory: str
    map_title: str
    counts: dict
    updates: dict = field(default_factory=dict)
    snapshots: dict = field(default_factory=dict)
    before: dict = field(default_factory=dict)
    update_existing: bool = True

    def diff(self):
        lines = []
        for relative, text in self.updates.items():
            if relative.endswith('.json'): continue
            lines.extend(difflib.unified_diff(self.before.get(relative,'').splitlines(), text.splitlines(), fromfile=relative+'（原）',tofile=relative+'（新）',lineterm=''))
        return '\n'.join(lines) or '内容相同，没有需要写入的变化。'


def prepare_save(result, config, external_updates=None, note_paths=None, update_existing=True):
    if not result.is_math or not result.concepts:
        raise ValueError("没有可保存的数学知识点。")
    config.validate()
    if not isinstance(update_existing,bool):
        raise ValueError('是否更新已有笔记必须是勾选选项。')
    if not config.vault_path or not Path(config.vault_path).expanduser().is_dir():
        raise ValueError('请选择已存在的 Obsidian 仓库文件夹。')
    if any(not isinstance(c.title,str) or not c.title.strip() or not isinstance(c.content,str) or not c.content.strip() for c in result.concepts):
        raise ValueError('笔记标题与正文不能为空。')
    notes_subfolder=config.notes_subfolder
    if not update_existing:
        if external_updates or note_paths:
            raise ValueError('独立保存不能指定旧笔记更新或旧文件目标。')
        snapshot=dict(concepts=[asdict(c) for c in result.concepts],connections=result.connections,
                      summary=result.summary,source=result.source,style=config.math_note_style,
                      index=config.index_note_name,auto_index=config.auto_link_notes)
        revision=hashlib.sha256(json.dumps(snapshot,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:12]
        token=hashlib.sha256(result.import_id.encode()).hexdigest()[:16]
        notes_subfolder=str(Path(notes_subfolder)/'独立导入'/f'导入-{token}-{revision}')
    vault = VaultManager(config.vault_path, notes_subfolder, config.backup_before_update, config.index_note_name)
    batch_id = vault.compute_hash(json.dumps([(c.title, c.content) for c in result.concepts], ensure_ascii=False))[:8]
    map_title = f"对话知识地图-{batch_id}"
    paths, reserved = {}, {str(vault.index_path).casefold()}
    for title in [c.title for c in result.concepts]+[map_title]:
        path = Path((note_paths or {}).get(title) or vault.note_path(title))
        if path.is_symlink() or not path.resolve().is_relative_to(vault.notes_dir):
            raise ValueError('笔记目标必须位于数学笔记目录内。')
        if str(path).casefold() in reserved:
            path = path.with_name(path.stem+'-'+vault.compute_hash(title)[:6]+'.md')
        reserved.add(str(path).casefold())
        paths[title] = path
    targets={}
    for c in result.concepts:targets.update(c.link_targets)
    link_root=vault.notes_dir if update_existing else vault.vault_root
    targets.update({title:path.relative_to(link_root).with_suffix('').as_posix() for title,path in paths.items()})
    # Previously merged titles remain navigable, but new imports should target
    # their canonical note instead of overwriting a redirect with a duplicate.
    for c in result.concepts:
        path=paths[c.title]
        if update_existing and path.exists():
            props,_=split_frontmatter(path.read_text(encoding='utf-8-sig'))
            if props.get('kind')=='重定向' and isinstance(props.get('merged_into'),str):
                canonical=vault.vault_root/props['merged_into']
                if canonical.is_symlink() or not canonical.resolve().is_relative_to(vault.notes_dir) or not canonical.exists():
                    raise ValueError('重定向指向的主笔记不存在或路径不合法。')
                paths[c.title]=canonical
                targets[c.title]=canonical.relative_to(vault.notes_dir).with_suffix('').as_posix()
    counts = dict(created=0, updated=0, skipped=0)
    plan = SavePlan(str(vault.vault_root),str(vault.notes_dir),map_title,counts,update_existing=update_existing)
    meta = copy.deepcopy(vault.meta)
    def stage(path,text,expected_marker=False,expected=None):
        relative = path.relative_to(vault.vault_root).as_posix()
        raw = path.read_bytes() if path.exists() else None
        if expected_marker and digest(raw)!=expected:
            raise RuntimeError(f'「{path.name}」在分析后被修改，请重新处理。')
        previous = raw.decode('utf-8-sig') if raw else ''
        if previous == text: return
        if not update_existing and raw is not None and path.suffix=='.md':
            return
        plan.updates[relative]=text
        plan.snapshots[relative]=digest(raw)
        plan.before[relative]=previous
    for c in result.concepts:
        path = paths[c.title]
        relative=path.relative_to(vault.vault_root).as_posix()
        old=plan.updates.get(relative) or (path.read_text(encoding='utf-8-sig') if path.exists() else '')
        if not update_existing and path.exists():
            counts['skipped']+=1
            continue
        concept_for_note=c
        if old:
            existing_props,_=split_frontmatter(old)
            existing_title=str(existing_props.get('title') or path.stem)
            if existing_title!=c.title:
                concept_for_note=copy.copy(c)
                concept_for_note.title=existing_title
        md = build_concept_note(concept_for_note, targets={**c.link_targets,**targets}, source=result.source, map_title=map_title,styled=config.math_note_style)
        props, body = split_frontmatter(md)
        props.pop("created", None)
        props.pop("updated", None)
        h = vault.compute_hash(json.dumps(props, ensure_ascii=False, sort_keys=True) + body)
        if old and meta.get(c.title,{}).get('hash') == h:
            counts['skipped']+=1
            continue
        merged = vault._merge_notes(old,md) if old else md
        if old==merged:
            counts['skipped']+=1
        else:
            counts['updated' if old else 'created']+=1
            stage(path,merged)
        meta[c.title]=dict(hash=h,filename=path.relative_to(vault.notes_dir).as_posix(),updated=datetime.now().isoformat())
    map_md = build_conversation_map(result, map_title, targets)
    map_path=paths[map_title]
    if update_existing and map_path.exists():
        old=map_path.read_text(encoding='utf-8-sig')
        old_props,old_body=split_frontmatter(old)
        props,body=split_frontmatter(map_md)
        if old_body==body: map_md=old
        else:
            props['created']=old_props.get('created',props['created'])
            map_md=compose_note(props,body)
    stage(map_path,map_md)
    for relative, update in (external_updates or {}).items():
        from core.maintenance import add_relation_text
        path=vault.vault_root/relative
        old=plan.updates.get(relative) or path.read_text(encoding='utf-8-sig')
        stage(path,add_relation_text(old,update['relations']),True,update['fingerprint'])
    if meta!=vault.meta:
        stage(vault.meta_path,json.dumps(meta,ensure_ascii=False,indent=2))
    if config.auto_link_notes:
        all_notes={str(vault.notes_dir/title)+'.md':text for title,text in vault.get_all_notes().items()}
        all_notes.update({str(vault.vault_root/relative):text for relative,text in plan.updates.items() if relative.endswith('.md')})
        categories={}
        for filename,text in all_notes.items():
            if Path(filename)==vault.index_path:continue
            try: props,_=split_frontmatter(text)
            except (ValueError,yaml.YAMLError):continue
            if props.get('kind') in ('索引','知识地图','重定向'):continue
            title=Path(filename).relative_to(link_root).with_suffix('').as_posix() if Path(filename).is_relative_to(link_root) else Path(filename).relative_to(vault.vault_root).with_suffix('').as_posix()
            categories.setdefault(str(props.get('category','未分类')),[]).append(title)
        index=build_index_note(categories,title=config.index_note_name)
        if vault.index_path.exists():
            old=vault.index_path.read_text(encoding='utf-8-sig')
            old_props,old_body=split_frontmatter(old)
            props,body=split_frontmatter(index)
            if body==old_body:index=old
            else:
                props['created']=old_props.get('created',props['created'])
                index=compose_note(props,body)
        stage(vault.index_path,index)
    return plan


def apply_save_plan(plan,config,cancel_check=None):
    if Path(plan.root).resolve()!=Path(config.vault_path).resolve():
        raise ValueError('保存方案与当前仓库不一致。')
    with VaultLock(plan.root):
        # Independent imports must also leave previous interrupted operations alone.
        if plan.update_existing and recover_incomplete(plan.root,already_locked=True):
            raise RuntimeError('已恢复上次中断的写入，请重新预览或保存本次笔记。')
        transaction=FileTransaction(plan.root,label='save',backup=config.backup_before_update,cancel_check=cancel_check)
        for relative,text in plan.updates.items():
            if not plan.update_existing and relative.endswith('.md') and plan.snapshots[relative] is not None:
                raise ValueError('这次导入未允许更新已有笔记，已停止写入。')
            transaction.stage(Path(plan.root)/relative,text,expected=plan.snapshots[relative])
        transaction.commit(already_locked=True)
    return plan.counts,plan.directory,plan.map_title


def save_extraction(result, config, update_existing=True):
    return apply_save_plan(prepare_save(result,config,update_existing=update_existing),config)
