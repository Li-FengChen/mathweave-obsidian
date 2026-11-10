"""Transient, non-blocking feedback centered over the workspace."""
from PySide6.QtCore import QEvent, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QLabel, QVBoxLayout


class SaveSuccessNotice(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('saveSuccessNotice')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet('''
            QFrame#saveSuccessNotice {
                background: #f3fbf7; border: 1px solid #b9dfd0; border-radius: 14px;
            }
            QLabel { background: transparent; border: none; }
            QLabel#noticeMark { color: #237f72; font-size: 30px; }
            QLabel#noticeTitle { color: #236a5d; font-size: 19px; font-weight: 600; }
            QLabel#noticeDetail { color: #66867c; font-size: 12px; }
        ''')
        self.setMinimumWidth(350)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 18, 30, 22)
        layout.setSpacing(5)
        mark = QLabel('✓')
        mark.setObjectName('noticeMark')
        title = QLabel('保存成功')
        title.setObjectName('noticeTitle')
        self.detail = QLabel()
        self.detail.setObjectName('noticeDetail')
        for label in (mark, title, self.detail):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b'opacity', self)
        self._fade.setDuration(180)
        self._fade.finished.connect(self.hide)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        parent.installEventFilter(self)
        self.hide()

    def show_success(self, counts):
        self.dismiss()
        self.detail.setText(f"新增 {counts['created']} · 更新 {counts['updated']} · 跳过 {counts['skipped']}")
        self._opacity.setOpacity(1)
        self.adjustSize()
        self._center()
        self.show()
        self.raise_()
        self._timer.start(3000)

    def dismiss(self):
        self._timer.stop()
        self._fade.stop()
        self.hide()

    def _fade_out(self):
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0)
        self._fade.start()

    def _center(self):
        rect = self.parentWidget().rect()
        self.move((rect.width() - self.width()) // 2, (rect.height() - self.height()) // 2)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize and self.isVisible():
            self._center()
        return super().eventFilter(watched, event)
