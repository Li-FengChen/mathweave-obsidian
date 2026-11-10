"""Exercise the real local renderer and GUI without calling an AI service."""
import json
import os
import sys
import time
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['MATH_OBSIDIAN_HOME'] = str(ROOT / '.qa' / 'state')
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from core.config import Config
from core.demo import demo_result
from core.obsidian import build_concept_note
from ui.main_window import MainWindow
from ui.theme import STYLE

app = QApplication(sys.argv)
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
window = MainWindow(Config(vault_path=str(ROOT / '.qa' / 'vault'), use_ai_extraction=False))
Path(window.config.vault_path).mkdir(parents=True, exist_ok=True)
window.show()


def js(script, page=None):
    loop = QEventLoop()
    value = []
    def callback(v):
        value.append(v)
        loop.quit()
    (page or window.render_preview.page).runJavaScript(script, callback)
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    return value[0] if value else None


def wait_preview():
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        value = js('JSON.stringify(window.previewState)')
        if value:
            state = json.loads(value)
            if state.get('ready'):
                return state
        loop = QEventLoop()
        QTimer.singleShot(150, loop.quit)
        loop.exec()
    raise AssertionError('Renderer timed out')


def run():
    try:
        results = []
        for c in demo_result().concepts:
            window.render_preview.set_markdown(build_concept_note(c), c.tags)
            state = wait_preview()
            assert state['mathCount'] > 0, (c.title, state)
            assert not state['errors'], (c.title, state)
            results.append(dict(title=c.title, **state))
        # Exercise macros, escaped delimiters, body separators and raw HTML.
        text = r'''---
title: test
---
# 自定义公式

$$\newcommand{\RR}{\mathbb{R}} \RR^n$$

---

分隔线后正文必须可见。行内 \(a<b\) 和 $\alpha+\beta$。

```latex
$$do_not_typeset$$
```

<script>window.injected=true</script>
'''
        window.render_preview.set_markdown(text)
        state = wait_preview()
        assert not state['errors'], state
        assert state['mathCount'] == 3, state
        assert js('document.getElementById("content").innerText.includes("分隔线后正文")')
        assert not js('Boolean(window.injected)')
        window.render_preview.set_markdown(text)
        repeated = wait_preview()
        assert not repeated['errors'], repeated
        callouts=r'''# 原生数学笔记

> [!abstract] 定义
> 行内 $f(x)=x^2$。
>
> $$
> \begin{aligned}
> f'(x)&=2x\\
> f''(x)&=2
> \end{aligned}
> $$

> [!tip]- 证明
> \[\lim_{h\to0}\frac{(x+h)^2-x^2}{h}=2x\]
>
> > [!example]+ 嵌套例题
> > $f'(1)=2$。

> 普通引用中的公式：
> $$\begin{pmatrix}1&0\\0&1\end{pmatrix}$$

```md
> [!tip]- 这在代码中
> $不要排版$
[[不要变成链接]]
```
'''
        window.render_preview.set_markdown(callouts)
        folded=wait_preview()
        assert not folded['errors'],folded
        assert folded['mathCount']==5,folded
        assert js('document.querySelectorAll("details.callout").length')==2
        assert not js('document.querySelector("details[data-callout=tip]").open')
        assert js('document.querySelector("details[data-callout=example]").open')
        assert js('document.querySelectorAll("pre .wiki").length')==0
        js('document.querySelector("details[data-callout=tip] summary").click()')
        assert js('document.querySelector("details[data-callout=tip]").open')
        window.render_preview.set_markdown(r'$\href{javascript:window.injected=true}{x}$ 和 $\href{file:///private}{y}$')
        safe=wait_preview()
        assert not safe['errors'],safe
        assert js('document.querySelectorAll("[href^=javascript], [href^=file]").length')==0
        for _ in range(2):
            window.render_preview.set_markdown(r'$$\begin{equation}x=1\label{same}\end{equation}$$')
            assert not wait_preview()['errors']
        # Exercise the complete maintenance dialog using deterministic AI fixtures.
        sys.path.insert(0,str(ROOT/'tests'))
        from test_maintenance import MaintenanceTests,FakeMathAI
        from ui.maintenance_dialog import MaintenanceDialog
        from ui.main_window import SettingsDialog
        with tempfile.TemporaryDirectory() as root:
            config,before=MaintenanceTests().setup_vault(root)
            dialog=MaintenanceDialog(config,window,ai_factory=lambda config,cancel_check:FakeMathAI())
            dialog.show()
            dialog.start()
            deadline=time.monotonic()+20
            while dialog.task and time.monotonic()<deadline:
                loop=QEventLoop();QTimer.singleShot(50,loop.quit);loop.exec()
            assert not dialog.task,'maintenance thread timed out'
            assert dialog.plan and len(dialog.plan.groups)==1,dialog.report.toPlainText()
            assert '已写入' in dialog.report.toPlainText()
            dialog.tabs.setCurrentIndex(2)
            dialog.note_select.setCurrentText('数学笔记/导数.md')
            loop=QEventLoop();QTimer.singleShot(500,loop.quit);loop.exec()
            dialog.grab().save(str(ROOT/'.qa'/'maintenance-window.png'))
            dialog.undo()
            while dialog.task and time.monotonic()<deadline:
                loop=QEventLoop();QTimer.singleShot(50,loop.quit);loop.exec()
            assert not dialog.task
            for name,raw in before.items():assert (Path(root)/name).read_bytes()==raw
            dialog.close()
            settings=SettingsDialog(config,window)
            assert settings.read_values().maintenance_scope=='math'
            assert settings.read_values().math_note_style
            settings.close()
        window.load_demo()
        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()
        assert js('document.querySelectorAll("a.node").length', window.graph_preview.page) == 4
        assert js('document.querySelectorAll(".relation-item").length', window.graph_preview.page) == 3
        window.navigate_note('泰勒公式')
        wait_preview()
        window.grab().save(str(ROOT/'.qa'/'window-2.1.png'))
        from ui.relations_dialog import RelationsDialog
        editor=RelationsDialog(window.current_concept,[c.title for c in window.last_result.concepts],window)
        assert len(editor.relations())==2
        editor.table.selectRow(0)
        editor.remove_rows()
        assert len(editor.relations())==1
        window.update_relations([])
        assert not any(e['source']=='泰勒公式' or e['target']=='泰勒公式' for e in window.last_result.connections)
        assert '泰勒公式' not in next(c for c in window.last_result.concepts if c.title=='导数').related
        editor.close()
        report = dict(status='passed', formulas=results, extra=state, callouts=folded,maintenance_dialog='merge and exact undo passed')
        (ROOT / '.qa' / 'gui-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
        if '--stay-open' not in sys.argv:
            window.close()
            app.quit()
    except Exception:
        import traceback
        traceback.print_exc()
        app.exit(1)


QTimer.singleShot(1000, run)
sys.exit(app.exec())
