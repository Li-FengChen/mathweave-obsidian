"""Run the packaged executable with isolated sample data and check its result."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
exe = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT / 'dist' / '数学知识织网' / '数学知识织网.exe'
output = ROOT / '.qa' / f'portable-check-{time.time_ns()}' / 'result.json'
output.parent.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, MATH_OBSIDIAN_HOME=str(ROOT / '.qa' / 'portable-state'))
for name in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):
    env.pop(name,None)
if os.name=='nt':
    windows=Path(env.get('SystemRoot','C:/Windows'))
    env['PATH']=os.pathsep.join([str(windows/'System32'),str(windows)])
completed = subprocess.run([str(exe), '--verify-bundle', str(output)], cwd=exe.parent, env=env, timeout=70, capture_output=True)
print('Exit code:', completed.returncode)
if completed.stderr:
    print(completed.stderr.decode('utf-8', errors='replace')[-3000:])
completed.check_returncode()
if output.exists():
    report = json.loads(output.read_text(encoding='utf-8'))
    print(json.dumps(report, ensure_ascii=False))
    assert report['status']=='passed', report
else:
    raise RuntimeError('Portable application did not produce its verification result.')
