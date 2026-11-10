"""Offline Obsidian-style reading preview powered by local MathJax."""
import json
from urllib.parse import unquote
from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
from core.resources import resource_path


class LocalOnly(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        if info.requestUrl().scheme() in ("http", "https", "ftp"):
            info.block(True)


class NotePage(QWebEnginePage):
    noteClicked = Signal(str)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() == "mathnote":
            self.noteClicked.emit(unquote(url.toString().split(":", 1)[1]))
            return False
        if url.scheme() in ("http", "https", "mailto"):
            if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                QDesktopServices.openUrl(url)
            return False
        return url.scheme() in ("file", "about", "data", "qrc")


class MarkdownPreview(QWidget):
    noteClicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        self._payload = None
        self._mode = "renderNote"
        self.view = QWebEngineView(self)
        self.profile = QWebEngineProfile(self)
        self.interceptor = LocalOnly(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.page = NotePage(self.profile, self.view)
        self.view.setPage(self.page)
        self.page.noteClicked.connect(self.noteClicked)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.view.loadFinished.connect(self._on_load)
        self.view.setUrl(QUrl.fromLocalFile(str(resource_path("assets/preview.html"))))

    def _on_load(self, ok):
        self._loaded = ok
        if ok and self._payload is not None:
            self._render()

    def _render(self):
        if self._loaded and self._payload is not None:
            self.page.runJavaScript(f"window.{self._mode}({json.dumps(self._payload, ensure_ascii=True)});")

    def set_markdown(self, md, tags=None, dark=False):
        self._mode = "renderNote"
        self._payload = {"markdown": md, "tags": tags or [], "dark": dark}
        self._render()

    def set_graph(self, concepts, connections):
        self._mode = "renderGraph"
        self._payload = {"nodes": [{"title": c.title, "category": c.category} for c in concepts], "edges": connections}
        self._render()

    def clear(self):
        self.set_markdown("# 准备阅读\n\n选择一个知识点，查看内容与知识联系。")
