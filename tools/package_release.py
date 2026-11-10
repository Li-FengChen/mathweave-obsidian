"""Package portable binaries and source using explicit public-file allowlists."""
import hashlib
import importlib.metadata
import json
import shutil
import zipfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'release'
sys.path.insert(0,str(ROOT))
from core.resources import APP_VERSION as VERSION


def zip_tree(folder, output):
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(folder.parent))


def main():
    RELEASE.mkdir(exist_ok=True)
    source = ROOT / 'dist' / '数学知识织网'
    if not (source / '数学知识织网.exe').exists():
        raise RuntimeError('请先运行 PyInstaller 构建。')
    # Keep mutable documentation/resources in sync with the final source tree.
    shutil.copytree(ROOT / 'assets', source / '_internal' / 'assets', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'docs' / '使用说明.md', source / '_internal' / 'docs' / '使用说明.md')
    portable = RELEASE / f'数学知识织网-{VERSION}-Windows'
    portable.mkdir(exist_ok=True)
    shutil.copytree(source, portable, dirs_exist_ok=True)
    # Remove only known obsolete generated ICU files from earlier builds.
    for filename in ('icuuc.dll', 'icudt78.dll'):
        obsolete = portable / '_internal' / filename
        if obsolete.exists():
            if not obsolete.resolve().is_relative_to(RELEASE.resolve()):
                raise ValueError('Unsafe obsolete runtime path')
            obsolete.unlink()
    for name in ('README.md', 'requirements-lock.txt', 'THIRD_PARTY_NOTICES.md','LICENSE'):
        shutil.copy2(ROOT / name, portable / name)
    readme=(portable/'README.md').read_text(encoding='utf-8').replace('(assets/app-icon.png)','(_internal/assets/app-icon.png)')
    (portable/'README.md').write_text(readme,encoding='utf-8')
    (portable/'docs').mkdir(exist_ok=True)
    for path in (ROOT/'docs').glob('*.md'):
        text=path.read_text(encoding='utf-8-sig').replace(ROOT.as_posix()+'/','../')
        (portable/'docs'/path.name).write_text(text,encoding='utf-8')
    for name in ('使用说明.md', '分享与打包.md'):
        shutil.copy2(ROOT / 'docs' / name, portable / name)
    (portable / '开始使用.txt').write_text(f'数学知识织网 {VERSION}\n\n1. 双击「数学知识织网.exe」。\n2. 点击「体验示例」，查看公式、定义框和折叠证明。\n3. 点击「设置」，选择自己的 Obsidian 仓库和 AI 服务。\n4. 粘贴对话，分析后校对、编辑并保存。\n5. 点击「AI 整理笔记库」，默认自动整理数学笔记子目录；备份后可撤销。\n\n先完整解压文件夹；不要只复制 exe。\n分享时发送完整 Windows.zip，每个人配置自己的密钥和仓库。\n详细教程可在窗口右上角打开。\n', encoding='utf-8-sig')
    licenses = portable / 'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copytree(ROOT / 'assets' / 'licenses', licenses, dirs_exist_ok=True)
    for distribution in importlib.metadata.distributions():
        dist_name = distribution.metadata['Name']
        for entry in distribution.files or []:
            path = Path(str(entry))
            if ('license' in str(path).lower() or 'copying' in path.name.lower()) and distribution.locate_file(entry).is_file():
                target = licenses / dist_name / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(distribution.locate_file(entry), target)
    python_license = Path(__import__('sys').base_prefix) / 'LICENSE.txt'
    if python_license.exists():
        shutil.copy2(python_license, licenses / 'Python-LICENSE.txt')
    # Chromium attribution file ships with the WebEngine wheel.
    import PySide6
    qt_root = Path(PySide6.__file__).parent
    for path in qt_root.rglob('*'):
        if path.is_file() and path.name.lower() in ('qtwebengine_license', 'qtwebengine_license.txt'):
            shutil.copy2(path, licenses / path.name)
    binary_zip = RELEASE / f'数学知识织网-{VERSION}-Windows.zip'
    zip_tree(portable, binary_zip)
    source_zip = RELEASE / f'数学知识织网-{VERSION}-源码.zip'
    allowed_dirs = ('core', 'ai', 'ui', 'assets', 'tools', 'tests','.github')
    allowed_files = ('main.py', 'README.md', 'requirements.txt', 'requirements-build.txt', 'requirements-lock.txt', 'MathWeave.spec', 'build_windows.ps1', '启动数学知识织网.cmd', 'THIRD_PARTY_NOTICES.md','LICENSE','.gitignore')
    with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for directory in allowed_dirs:
            for path in sorted((ROOT / directory).rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                    archive.write(path, Path('数学知识织网-源码') / path.relative_to(ROOT))
        for filename in allowed_files:
            archive.write(ROOT / filename, Path('数学知识织网-源码') / filename)
        for path in (ROOT/'docs').glob('*.md'):
            text=path.read_text(encoding='utf-8-sig').replace(ROOT.as_posix()+'/','../')
            archive.writestr(str(Path('数学知识织网-源码/docs')/path.name),text.encode('utf-8'))
    checksums = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (binary_zip, source_zip)}
    (RELEASE / 'SHA256.json').write_text(json.dumps(checksums, ensure_ascii=False, indent=2), encoding='utf-8')
    (RELEASE / f'SHA256-{VERSION}.json').write_text(json.dumps(checksums, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'portable':str(portable), 'archives':checksums},ensure_ascii=False))


if __name__ == '__main__':
    main()
