# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.win32.versioninfo import VSVersionInfo,FixedFileInfo,StringFileInfo,StringTable,StringStruct,VarFileInfo,VarStruct
root = Path(SPECPATH)
import sys
sys.path.insert(0,str(root))
from core.resources import APP_VERSION,APP_NAME
version=VSVersionInfo(ffi=FixedFileInfo(filevers=tuple(map(int,APP_VERSION.split('.')))+(0,),prodvers=tuple(map(int,APP_VERSION.split('.')))+(0,),mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('080404b0',[StringStruct('FileDescription',APP_NAME),StringStruct('FileVersion',APP_VERSION),StringStruct('ProductName',APP_NAME),StringStruct('ProductVersion',APP_VERSION),StringStruct('OriginalFilename','数学知识织网.exe')])]),VarFileInfo([VarStruct('Translation',[2052,1200])])])
a = Analysis(
    [str(root / 'main.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'assets'), 'assets'), (str(root / 'docs' / '使用说明.md'), 'docs')],
    hiddenimports=['keyring.backends.Windows', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['matplotlib', 'PyQt6', 'PyQt5', 'tkinter', 'PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.QtQuickWidgets', 'PySide6.QtPositioning'],
    noarchive=False,
)
# Qt 6.11 uses the Windows ICU API. Do not substitute an unrelated ICU DLL
# discovered on the developer's PATH; its version-suffixed exports are incompatible.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in ('icuuc.dll', 'icudt78.dll')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='数学知识织网',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False, icon=str(root / 'assets' / 'app.ico'),version=version)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='数学知识织网')
