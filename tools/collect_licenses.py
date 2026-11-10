"""Keep upstream license texts and the installed Qt WebEngine information page."""
import os
import sys
import time
import urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'assets' / 'licenses'
OUTPUT.mkdir(parents=True, exist_ok=True)
for filename, url in {
    'LGPL-3.0.txt':'https://raw.githubusercontent.com/qt/qtbase/v6.11.2/LICENSES/LGPL-3.0-only.txt',
    'GPL-3.0.txt':'https://raw.githubusercontent.com/qt/qtbase/v6.11.2/LICENSES/GPL-3.0-only.txt',
    'LGPL-2.1.txt':'https://raw.githubusercontent.com/FFmpeg/FFmpeg/n7.1.1/COPYING.LGPLv2.1',
}.items():
    if (OUTPUT / filename).exists() and (OUTPUT / filename).stat().st_size > 1000:
        continue
    for attempt in range(4):
        try:
            (OUTPUT / filename).write_bytes(urllib.request.urlopen(url, timeout=30).read())
            break
        except OSError:
            if attempt == 3:
                raise
            time.sleep(1)
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage
app = QApplication(sys.argv)
page = QWebEnginePage()
def done(ok):
    if not ok:
        print('Could not load local Qt WebEngine information page.', flush=True)
        app.exit(1)
        return
    def save(html):
        if 'qt' not in html.lower():
            app.exit(1)
            return
        home = str(Path.home())
        for prefix in (home, home.replace('\\', '/'), home.replace('\\', '\\\\')):
            html = html.replace(prefix, '%USERPROFILE%')
        (OUTPUT / 'QtWebEngine-About.html').write_text(html, encoding='utf-8')
        print('Saved upstream licenses and installed Qt WebEngine information.', flush=True)
        app.quit()
    page.toHtml(save)
page.loadFinished.connect(done)
page.setUrl(QUrl('chrome://qt'))
QTimer.singleShot(60000, lambda:app.exit(1))
sys.exit(app.exec())
