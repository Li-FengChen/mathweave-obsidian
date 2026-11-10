"""One-click maintenance with reports, optional plan preview and guarded undo."""
import copy
import difflib
from pathlib import Path
from PySide6.QtCore import QTimer,QUrl
from PySide6.QtGui import QDesktopServices,QFont
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QCheckBox,QPushButton,QTabWidget,QWidget,QPlainTextEdit,QProgressBar
from core.maintenance import build_maintenance_plan,apply_maintenance_plan,undo_last_maintenance
from ai.client import AIClient
from ui.main_window import Task
from ui.preview_widget import MarkdownPreview


class MaintenanceDialog(QDialog):
    def __init__(self,config,parent=None,ai_factory=AIClient):
        super().__init__(parent)
        self.config=copy.deepcopy(config)
        self.ai_factory=ai_factory
        self.task=None
        self.plan=None
        self._closing=False
        self.setWindowTitle('AI 整理笔记库 · 数学知识织网')
        self.resize(1100,780)
        layout=QVBoxLayout(self)
        title=QLabel('让已有知识，继续相互连接')
        title.setObjectName('section')
        layout.addWidget(title)
        info=QLabel('AI 将核对重复概念、补充双向联系并统一数学笔记格式。所选笔记会发送到你配置的 AI 服务；每次整理都会先备份。')
        info.setWordWrap(True)
        info.setObjectName('muted')
        layout.addWidget(info)
        row=QHBoxLayout()
        self.scope=QComboBox()
        self.scope.addItem('数学笔记子目录（推荐）','math')
        self.scope.addItem('整个仓库中的数学笔记','vault')
        self.scope.setCurrentIndex(self.scope.findData(config.maintenance_scope))
        self.preview_only=QCheckBox('仅生成方案，先查看变更')
        self.start_btn=QPushButton('开始自动整理')
        self.start_btn.setObjectName('primary')
        self.start_btn.clicked.connect(self.start)
        row.addWidget(self.scope)
        row.addWidget(self.preview_only)
        row.addStretch()
        row.addWidget(self.start_btn)
        layout.addLayout(row)
        self.progress=QProgressBar()
        self.progress.setRange(0,0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.tabs=QTabWidget()
        self.report=QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setPlaceholderText('整理进度、合并依据和结果会显示在这里。')
        self.tabs.addTab(self.report,'整理记录')
        self.diff=QPlainTextEdit()
        self.diff.setReadOnly(True)
        self.diff.setFont(QFont('Consolas',10))
        self.tabs.addTab(self.diff,'全部变更')
        reading=QWidget()
        reading_layout=QVBoxLayout(reading)
        self.note_select=QComboBox()
        self.note_select.currentTextChanged.connect(self.show_note)
        self.note_preview=MarkdownPreview()
        reading_layout.addWidget(self.note_select)
        reading_layout.addWidget(self.note_preview,1)
        self.tabs.addTab(reading,'整理后的笔记')
        layout.addWidget(self.tabs,1)
        footer=QHBoxLayout()
        self.undo_btn=QPushButton('撤销最近一次整理')
        self.undo_btn.clicked.connect(self.undo)
        self.backup_btn=QPushButton('打开备份文件夹')
        self.backup_btn.clicked.connect(self.open_backups)
        self.cancel_btn=QPushButton('取消当前任务')
        self.cancel_btn.clicked.connect(self.cancel)
        self.cancel_btn.hide()
        self.apply_btn=QPushButton('应用此方案')
        self.apply_btn.setObjectName('save')
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply)
        self.close_btn=QPushButton('关闭')
        self.close_btn.clicked.connect(self.close)
        for button in (self.undo_btn,self.backup_btn,self.cancel_btn):footer.addWidget(button)
        footer.addStretch()
        footer.addWidget(self.apply_btn)
        footer.addWidget(self.close_btn)
        layout.addLayout(footer)

    def busy(self,active):
        self.progress.setVisible(active)
        self.cancel_btn.setVisible(active)
        self.cancel_btn.setEnabled(True)
        for widget in (self.start_btn,self.scope,self.preview_only,self.undo_btn):widget.setEnabled(not active)
        self.apply_btn.setEnabled(not active and self.plan is not None and bool(self.plan.updates) and not self.plan.backup_path)

    def launch(self,operation,finished):
        if self.task:return
        self.busy(True)
        task=Task(operation,self)
        self.task=task
        task.progress.connect(self.report.appendPlainText)
        task.resultReady.connect(finished)
        task.failed.connect(lambda text:self.report.appendPlainText('处理未完成：'+text))
        task.finished.connect(lambda:self.stopped(task))
        task.start()

    def stopped(self,task):
        if task.isInterruptionRequested() and not getattr(task,'_completed_write',False):
            self.report.appendPlainText('已取消；本次写入如已开始，会恢复到开始前的内容。')
        self.task=None
        self.busy(False)
        task.deleteLater()
        if self._closing:self.close()

    def start(self):
        if self.task:return
        self.plan=None
        self.apply_btn.setEnabled(False)
        scope=self.scope.currentData()
        preview_only=self.preview_only.isChecked()
        self.report.appendPlainText('开始扫描：'+self.scope.currentText())
        def operation(task):
            client=self.ai_factory(self.config,cancel_check=task.isInterruptionRequested)
            plan=build_maintenance_plan(self.config,client,scope,task.progress.emit,task.isInterruptionRequested)
            if not preview_only:
                task.progress.emit('备份并写入；如发生冲突，停止并保留原内容…')
                apply_maintenance_plan(plan,self.config,task.isInterruptionRequested)
                task._completed_write=True
            return plan
        self.launch(operation,self.ready)

    def ready(self,plan):
        self.plan=plan
        summary=plan.summary()
        self.report.appendPlainText(f"完成：扫描 {summary['scanned']} 篇；合并 {summary['merged']} 组；核对 {summary['linked']} 条双向联系；格式整理 {summary['formatted']} 篇；改变 {summary['changed']} 个笔记文件。")
        if not plan.backup_path and plan.updates:self.report.appendPlainText('当前为预览方案，笔记尚未写入。点击「应用此方案」完成整理。')
        if plan.backup_path:self.report.appendPlainText('已写入。备份位置：'+plan.backup_path)
        for group in plan.groups:self.report.appendPlainText('合并到 '+group['canonical']+'：'+group['reason'])
        for edge in plan.links:self.report.appendPlainText(edge['source']+' → '+edge['relation']+' → '+edge['target']+'：'+edge['reason'])
        for warning in plan.warnings:self.report.appendPlainText('提示：'+warning)
        before={n.path:n.text for n in plan.notes}
        diff=[]
        for relative,text in plan.updates.items():
            diff.extend(difflib.unified_diff(before[relative].splitlines(),text.splitlines(),fromfile=relative+'（原）',tofile=relative+'（新）',lineterm=''))
        self.diff.setPlainText('\n'.join(diff) or '本次没有需要写入的变化。')
        self.note_select.clear()
        self.note_select.addItems(list(plan.updates))

    def show_note(self,path):
        if self.plan and path in self.plan.updates:self.note_preview.set_markdown(self.plan.updates[path])

    def apply(self):
        if not self.plan or self.task:return
        plan=self.plan
        def operation(task):
            apply_maintenance_plan(plan,self.config,task.isInterruptionRequested)
            task._completed_write=True
            return plan
        self.launch(operation,self.ready)

    def undo(self):
        if self.task:return
        def operation(task):
            result=undo_last_maintenance(self.config)
            task._completed_write=True
            return result
        def finished(result):
            self.plan=None
            self.note_select.clear()
            self.report.appendPlainText('最近一次整理已撤销；索引与元数据已一并恢复。撤销前内容也另存为恢复快照：'+str(result))
        self.launch(operation,finished)

    def cancel(self):
        if self.task:
            self.task.requestInterruption()
            self.cancel_btn.setEnabled(False)
            self.report.appendPlainText('正在取消；如有网络请求，等待当前请求结束。')

    def open_backups(self):
        path=Path(self.config.vault_path)/'.agent_backup'
        if path.exists():QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def reject(self):
        if self.task:
            self._closing=True
            self.cancel()
        else:super().reject()

    def closeEvent(self,event):
        if self.task:
            self._closing=True
            self.cancel()
            event.ignore()
        else:event.accept()
