"""数学知识织网 · desktop workspace."""
import copy
import json
import sys
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer, QUrl
from PySide6.QtGui import QAction, QFont, QIcon, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QProgressBar, QTabWidget, QSplitter,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QFormLayout,
    QPlainTextEdit, QScrollArea
)
from core.config import Config, PROVIDER_PRESETS
from core.parser import parse_text, parse_file
from core.extractor import extract_with_ai, extract_local, connect_concepts
from core.obsidian import build_concept_note, save_extraction
from core.services import analyze_conversation, save_import, prepare_import
from core.resources import resource_path, APP_NAME, APP_VERSION
from core.demo import DEMO_TEXT, demo_result
from core.logger import get_logger
from ai.client import AIClient
from ui.preview_widget import MarkdownPreview
from ui.theme import STYLE
from ui.notification import SaveSuccessNotice
from ui.api_key_editor import ApiKeyEditor

logger = get_logger()


class Task(QThread):
    resultReady = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            result = self.operation(self)
            if not self.isInterruptionRequested() or getattr(self,'_completed_write',False):
                self.resultReady.emit(result)
        except Exception as err:
            logger.exception("任务失败")
            if not self.isInterruptionRequested():
                self.failed.emit(str(err))


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = copy.deepcopy(config)
        self.test_task = None
        self.setWindowTitle("设置 · " + APP_NAME)
        self.setMinimumWidth(650)
        self.resize(740,800)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 23, 25, 23)
        title = QLabel("连接你的知识仓库")
        title.setObjectName("section")
        layout.addWidget(title)
        description = QLabel("仓库和密钥只保存在这台电脑，分享程序时不会一起打包。")
        description.setObjectName("muted")
        layout.addWidget(description)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        fields=QWidget()
        form = QFormLayout(fields)
        form.setSpacing(14)
        self.vault_edit = QLineEdit(config.vault_path)
        browse = QPushButton("选择文件夹")
        browse.clicked.connect(self.browse_vault)
        row = QHBoxLayout()
        row.addWidget(self.vault_edit, 1)
        row.addWidget(browse)
        form.addRow("Obsidian 仓库", row)
        self.subfolder_edit = QLineEdit(config.notes_subfolder)
        form.addRow("笔记子目录", self.subfolder_edit)
        self.index_edit=QLineEdit(config.index_note_name)
        form.addRow('分类索引名称',self.index_edit)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(PROVIDER_PRESETS)
        self.provider_combo.setCurrentText(config.ai_provider)
        self.api_base_edit = QLineEdit(config.api_base)
        self.model_edit = QLineEdit(config.model)
        self.provider_combo.currentTextChanged.connect(self.on_provider_change)
        form.addRow("AI 服务商", self.provider_combo)
        form.addRow("服务地址", self.api_base_edit)
        form.addRow("模型名称", self.model_edit)
        self.api_key_editor = ApiKeyEditor(config.ai_provider)
        self.api_key_edit = self.api_key_editor.edit
        form.addRow("API 密钥", self.api_key_editor)
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(512, 65536)
        self.max_tokens_spin.setValue(config.max_tokens)
        form.addRow("最大输出长度", self.max_tokens_spin)
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0, 2)
        self.temp_spin.setSingleStep(.1)
        self.temp_spin.setValue(config.temperature)
        form.addRow("生成温度", self.temp_spin)
        self.score_spin=QDoubleSpinBox()
        self.score_spin.setRange(0,1)
        self.score_spin.setSingleStep(.05)
        self.score_spin.setValue(config.min_math_score)
        form.addRow('数学相关度阈值',self.score_spin)
        self.chunk_spin=QSpinBox()
        self.chunk_spin.setRange(2000,60000)
        self.chunk_spin.setSingleStep(2000)
        self.chunk_spin.setValue(config.input_chunk_chars)
        form.addRow('每段输入长度（字符）',self.chunk_spin)
        self.json_combo=QComboBox()
        for title,value in [('自动兼容（推荐）','auto'),('强制 JSON 参数','force'),('仅提示词约束 JSON','off')]:self.json_combo.addItem(title,value)
        self.json_combo.setCurrentIndex(self.json_combo.findData(config.ai_json_mode))
        form.addRow('AI 输出模式',self.json_combo)
        self.scope_combo=QComboBox()
        self.scope_combo.addItem('数学笔记子目录（推荐）','math')
        self.scope_combo.addItem('整个仓库中的数学笔记','vault')
        self.scope_combo.setCurrentIndex(self.scope_combo.findData(config.maintenance_scope))
        form.addRow('AI 整理默认范围',self.scope_combo)
        self.confidence_spin=QDoubleSpinBox()
        self.confidence_spin.setRange(.5,1)
        self.confidence_spin.setSingleStep(.01)
        self.confidence_spin.setValue(config.maintenance_min_confidence)
        form.addRow('自动合并最低置信度',self.confidence_spin)
        self.notes_limit_spin=QSpinBox()
        self.notes_limit_spin.setRange(1,10000)
        self.notes_limit_spin.setValue(config.maintenance_max_notes)
        form.addRow('单次整理笔记上限',self.notes_limit_spin)
        self.use_ai_check = QCheckBox("使用 AI 提取知识点和数学关系")
        self.use_ai_check.setChecked(config.use_ai_extraction)
        self.auto_link_check = QCheckBox("保存后更新数学分类索引")
        self.auto_link_check.setChecked(config.auto_link_notes)
        self.backup_check = QCheckBox("更新已有笔记前保留备份")
        self.backup_check.setChecked(config.backup_before_update)
        self.math_style_check=QCheckBox('使用数学笔记框与可折叠证明')
        self.math_style_check.setChecked(config.math_note_style)
        self.existing_link_check=QCheckBox('保存时用 AI 核对与已有数学笔记的联系')
        self.existing_link_check.setToolTip('仅在本次导入勾选“更新已有笔记”时生效。')
        self.existing_link_check.setChecked(config.link_existing_on_save)
        for check in (self.use_ai_check, self.auto_link_check, self.backup_check,self.math_style_check,self.existing_link_check):
            form.addRow(check)
        scroll.setWidget(fields)
        layout.addWidget(scroll,1)
        self.test_btn = QPushButton("测试已配置的连接")
        self.test_btn.clicked.connect(self.test_connection)
        self.test_status = QLabel("输入新密钥后先保存，再测试连接。")
        self.test_status.setWordWrap(True)
        self.test_status.setObjectName("muted")
        layout.addWidget(self.test_btn)
        layout.addWidget(self.test_status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.buttons.accepted.connect(self.save_and_close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def browse_vault(self):
        path = QFileDialog.getExistingDirectory(self, "选择 Obsidian 仓库")
        if path:
            self.vault_edit.setText(path)

    def on_provider_change(self, name):
        preset = PROVIDER_PRESETS[name]
        self.api_base_edit.setText(preset["api_base"])
        self.model_edit.setText(preset["model"])
        self.api_key_editor.select_provider(name)

    def read_values(self):
        config = copy.deepcopy(self.config)
        config.vault_path = self.vault_edit.text().strip()
        config.notes_subfolder = self.subfolder_edit.text().strip()
        config.index_note_name=self.index_edit.text().strip()
        config.ai_provider = self.provider_combo.currentText()
        config.api_base = self.api_base_edit.text().strip()
        config.model = self.model_edit.text().strip()
        config.max_tokens = self.max_tokens_spin.value()
        config.temperature = self.temp_spin.value()
        config.use_ai_extraction = self.use_ai_check.isChecked()
        config.auto_link_notes = self.auto_link_check.isChecked()
        config.backup_before_update = self.backup_check.isChecked()
        config.min_math_score=self.score_spin.value()
        config.input_chunk_chars=self.chunk_spin.value()
        config.ai_json_mode=self.json_combo.currentData()
        config.maintenance_scope=self.scope_combo.currentData()
        config.maintenance_min_confidence=self.confidence_spin.value()
        config.maintenance_max_notes=self.notes_limit_spin.value()
        config.math_note_style=self.math_style_check.isChecked()
        config.link_existing_on_save=self.existing_link_check.isChecked()
        config.validate()
        if config.vault_path:
            root = Path(config.vault_path).expanduser().resolve()
            if not root.is_dir():
                raise ValueError("请选择已存在的 Obsidian 仓库文件夹。")
            if not (root / config.notes_subfolder).resolve().is_relative_to(root):
                raise ValueError("笔记子目录不能超出 Obsidian 仓库。")
        if config.use_ai_extraction and (not config.api_base.startswith(("https://", "http://")) or not config.model):
            raise ValueError("请输入完整的服务地址和模型名称。")
        return config

    def save_and_close(self):
        try:
            config = self.read_values()
            self.api_key_editor.hide_key()
            self.api_key_editor.save_changes(config.save)
            self.config = config
            self.accept()
        except Exception as err:
            QMessageBox.warning(self, "设置未保存", str(err))

    def test_connection(self):
        try:
            config = self.read_values()
            if self.api_key_editor.has_pending_changes(config.ai_provider):
                self.test_status.setText("请先保存密钥更改，再重新打开设置测试连接。")
                return
            self.api_key_editor.hide_key()
            self.api_key_editor.setEnabled(False)
            self.provider_combo.setEnabled(False)
            self.test_btn.setEnabled(False)
            self.buttons.setEnabled(False)
            self.test_status.setText("正在测试连接…")
            self.test_task = Task(lambda _: AIClient(config).test_connection(), self)
            self.test_task.resultReady.connect(lambda result: self.test_status.setText(result[1]))
            self.test_task.failed.connect(self.test_status.setText)
            self.test_task.finished.connect(self.finish_test)
            self.test_task.start()
        except Exception as err:
            self.api_key_editor.setEnabled(True)
            self.provider_combo.setEnabled(True)
            self.test_btn.setEnabled(True)
            self.buttons.setEnabled(True)
            self.test_status.setText(str(err))

    def finish_test(self):
        self.api_key_editor.setEnabled(True)
        self.provider_combo.setEnabled(True)
        self.test_btn.setEnabled(True)
        self.buttons.setEnabled(True)
        self.test_task.deleteLater()
        self.test_task = None

    def reject(self):
        if self.test_task and self.test_task.isRunning():
            self.test_status.setText("请等待当前连接测试结束。")
            return
        self.api_key_editor.hide_key()
        super().reject()

    def closeEvent(self, event):
        if self.test_task and self.test_task.isRunning():
            event.ignore()
        else:
            self.api_key_editor.hide_key()
            super().closeEvent(event)


def label(text, name="muted"):
    widget = QLabel(text)
    widget.setObjectName(name)
    return widget


def card(number, heading):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 19, 18, 18)
    layout.setSpacing(12)
    layout.addWidget(label(number, "number"))
    layout.addWidget(label(heading, "section"))
    return frame, layout


class MainWindow(QMainWindow):
    def __init__(self, config=None):
        super().__init__()
        self.config = config or Config.load()
        self.task = None
        self.last_result = None
        self.current_concept = None
        self._source = "粘贴对话"
        self._import_text = None
        self._updating = False
        self._closing = False
        self._busy_kind = ""
        self.setWindowTitle(f"{APP_NAME} · {APP_VERSION}")
        self.setWindowIcon(QIcon(str(resource_path("assets/app.ico"))))
        self.resize(1380, 870)
        self.setMinimumSize(1080, 720)
        self.setup_ui()
        self.save_notice = SaveSuccessNotice(self.centralWidget())

    def setup_ui(self):
        menu = self.menuBar().addMenu("文件")
        for name, callback in (("设置", self.open_settings), ("打开仓库", self.open_vault), ("使用教程", self.open_help), ("退出", self.close)):
            action = QAction(name, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        workspace = QWidget()
        workspace.setObjectName("workspace")
        self.setCentralWidget(workspace)
        outer = QVBoxLayout(workspace)
        outer.setContentsMargins(25, 17, 25, 18)
        outer.setSpacing(19)
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QPixmap(str(resource_path("assets/app-icon.png"))).scaled(55, 55, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header.addWidget(icon)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(label(APP_NAME, "brand"))
        titles.addWidget(label("让每一次数学对话，成为相互连接的知识。", "subtitle"))
        header.addLayout(titles)
        header.addStretch()
        self.pill = label("本地公式预览 · 离线可用", "pill")
        header.addWidget(self.pill)
        self.help_btn = QPushButton("使用教程")
        self.help_btn.clicked.connect(self.open_help)
        self.settings_btn = QPushButton("设置")
        self.settings_btn.clicked.connect(self.open_settings)
        self.maintenance_btn=QPushButton('AI 整理笔记库')
        self.maintenance_btn.clicked.connect(self.open_maintenance)
        self.maintenance_btn.setToolTip('按设置中的默认范围自动整理；合并前备份，可撤销。笔记会发往你配置的 AI 服务。')
        header.addWidget(self.maintenance_btn)
        header.addWidget(self.help_btn)
        header.addWidget(self.settings_btn)
        outer.addLayout(header)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        source, source_layout = card("01  /  INPUT", "对话素材")
        source_layout.addWidget(label("粘贴完整对话，保留定义、推导与例子。"))
        actions = QHBoxLayout()
        self.import_btn = QPushButton("导入文件")
        self.import_btn.clicked.connect(self.import_file)
        self.demo_btn = QPushButton("体验示例")
        self.demo_btn.clicked.connect(self.load_demo)
        actions.addWidget(self.import_btn)
        actions.addWidget(self.demo_btn)
        source_layout.addLayout(actions)
        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText("在这里粘贴数学对话…\n\n支持纯文本、Markdown 和 JSON 导出。\n\n第一次使用？点击上方「体验示例」，无需配置即可查看公式和知识联系。")
        source_layout.addWidget(self.text_input, 1)
        self.source_label = label("尚未导入 · 文件内容只在本机解析")
        self.source_label.setWordWrap(True)
        source_layout.addWidget(self.source_label)
        self.analyze_btn = QPushButton("提取知识与联系  →")
        self.analyze_btn.setObjectName("primary")
        self.analyze_btn.clicked.connect(self.start_analysis)
        self.analyze_btn.setToolTip("开启 AI 时，对话将发送到设置中选择的服务。")
        source_layout.addWidget(self.analyze_btn)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        source_layout.addWidget(self.progress_bar)
        self.cancel_btn = QPushButton("取消当前分析")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_task)
        source_layout.addWidget(self.cancel_btn)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(95)
        self.log_view.setMaximumBlockCount(100)
        self.log_view.setPlaceholderText("处理进度")
        source_layout.addWidget(self.log_view)
        notes, notes_layout = card("02  /  KNOWLEDGE", "知识点")
        self.count_label = label("等待分析")
        notes_layout.addWidget(self.count_label)
        self.result_list = QListWidget()
        self.result_list.currentItemChanged.connect(self.select_concept)
        self.result_list.itemChanged.connect(self.update_count)
        notes_layout.addWidget(self.result_list, 1)
        notes_layout.addWidget(label("勾选要保存的笔记。\n点击标题查看公式与关联。"))
        reading, reading_layout = card("03  /  READ & CONNECT", "阅读与校对")
        self.note_heading = label("准备好，开始织网", "summary")
        self.note_heading.setWordWrap(True)
        reading_layout.addWidget(self.note_heading)
        self.tabs = QTabWidget()
        self.render_preview = MarkdownPreview()
        self.render_preview.noteClicked.connect(self.navigate_note)
        self.tabs.addTab(self.render_preview, "笔记预览")
        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(4, 12, 4, 4)
        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.category_edit = QLineEdit()
        self.tags_edit = QLineEdit()
        form.addRow("标题", self.title_edit)
        form.addRow("分类", self.category_edit)
        form.addRow("标签（逗号分隔）", self.tags_edit)
        editor_layout.addLayout(form)
        self.content_edit = QPlainTextEdit()
        self.content_edit.setPlaceholderText("选中知识点后，可以修改正文。公式使用 $…$ 或 $$…$$。")
        editor_layout.addWidget(self.content_edit, 1)
        relations_btn=QPushButton('修改知识联系')
        relations_btn.clicked.connect(self.edit_relations)
        editor_layout.addWidget(relations_btn)
        apply_btn = QPushButton("应用修改并预览")
        apply_btn.clicked.connect(self.apply_edits_and_preview)
        editor_layout.addWidget(apply_btn)
        self.tabs.addTab(editor, "编辑笔记")
        self.graph_preview = MarkdownPreview()
        self.graph_preview.noteClicked.connect(self.navigate_note)
        self.tabs.addTab(self.graph_preview, "知识联系")
        self.tabs.currentChanged.connect(self.tab_changed)
        reading_layout.addWidget(self.tabs, 1)
        import_options=QHBoxLayout()
        self.update_existing_check=QCheckBox('更新已有笔记')
        self.update_existing_check.setChecked(False)
        self.update_existing_check.setEnabled(False)
        self.update_existing_check.setToolTip('勾选：补充同名笔记，并按设置核对新旧联系。\n未勾选：保存到独立导入文件夹，保留本次知识联系。\n每次重新提取后默认不勾选。')
        self.import_mode_label=label('独立保存到新的导入文件夹')
        self.import_mode_label.setWordWrap(True)
        self.update_existing_check.toggled.connect(self.update_import_mode)
        import_options.addWidget(self.update_existing_check)
        import_options.addWidget(self.import_mode_label,1)
        reading_layout.addLayout(import_options)
        footer = QHBoxLayout()
        self.status_label = label("选择知识点，阅读完整笔记。")
        self.status_label.setWordWrap(True)
        self.save_btn = QPushButton("保存到 Obsidian")
        self.save_btn.setObjectName("save")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_to_vault)
        self.diff_btn=QPushButton('变更预览')
        self.diff_btn.clicked.connect(lambda:self.save_to_vault(preview=True))
        self.diff_btn.setEnabled(False)
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.diff_btn)
        footer.addWidget(self.save_btn)
        reading_layout.addLayout(footer)
        self.splitter.addWidget(source)
        self.splitter.addWidget(notes)
        self.splitter.addWidget(reading)
        self.splitter.setSizes([355, 230, 725])
        outer.addWidget(self.splitter, 1)
        bottom = QHBoxLayout()
        self.vault_label = label("")
        self.update_vault_label()
        bottom.addWidget(self.vault_label, 1)
        bottom.addWidget(label("数学知识织网  /  "+APP_VERSION))
        outer.addLayout(bottom)

    def update_vault_label(self):
        self.vault_label.setText("仓库  ·  " + (self.config.vault_path or "尚未设置，点击右上角「设置」"))

    def update_import_mode(self,checked):
        self.import_mode_label.setText('补充同名笔记，按设置核对新旧联系' if checked else '独立保存到新的导入文件夹')

    def log(self, text):
        self.log_view.appendPlainText(text)

    def open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.config
            self.update_vault_label()
            self.log("设置已保存。")
        dialog.deleteLater()

    def open_vault(self):
        if self.config.vault_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.config.vault_path))
        else:
            self.open_settings()

    def open_maintenance(self):
        if self.task:return
        if not self.config.vault_path:
            self.open_settings()
            if not self.config.vault_path:return
        try:
            AIClient(self.config)
            from ui.maintenance_dialog import MaintenanceDialog
            dialog=MaintenanceDialog(self.config,self)
            QTimer.singleShot(200,dialog.start)
            dialog.exec()
        except Exception as err:
            QMessageBox.warning(self,'暂时无法整理',str(err))

    def open_help(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("使用教程 · " + APP_NAME)
        dialog.resize(1000, 780)
        layout = QVBoxLayout(dialog)
        preview = MarkdownPreview(dialog)
        preview.set_markdown(resource_path("docs/使用说明.md").read_text(encoding="utf-8-sig"))
        layout.addWidget(preview)
        dialog.exec()

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入对话", "", "对话文件 (*.txt *.md *.json);;所有文件 (*.*)")
        if not path:
            return
        try:
            conv = parse_file(path)
            self._source = str(Path(path).resolve())
            self._import_text = conv.text
            self.text_input.setPlainText(conv.text)
            self.update_existing_check.setChecked(False)
            self.source_label.setText(f"{Path(path).name} · {len(conv.messages)} 条消息")
            self.log("文件已导入。")
        except Exception as err:
            QMessageBox.warning(self, "导入失败", str(err))

    def load_demo(self):
        self.text_input.setPlainText(DEMO_TEXT)
        self._source = "内置教学示例"
        self._import_text = DEMO_TEXT
        self.source_label.setText("教学示例 · 无需 API · 可以直接预览")
        self.show_result(demo_result())
        self.navigate_note("泰勒公式")
        self.log("已载入教学示例。点击「知识联系」查看关系；示例可以保存到你选择的仓库。")

    def set_busy(self, busy, kind=""):
        if busy:
            self.save_notice.dismiss()
        self._busy_kind = kind if busy else ""
        self.progress_bar.setVisible(busy)
        self.cancel_btn.setVisible(busy)
        self.cancel_btn.setEnabled(True)
        for widget in (self.analyze_btn, self.import_btn, self.demo_btn, self.text_input, self.settings_btn, self.result_list,self.maintenance_btn):
            widget.setEnabled(not busy)
        self.save_btn.setEnabled(not busy and bool(self.last_result and self.last_result.concepts))
        self.diff_btn.setEnabled(not busy and bool(self.last_result and self.last_result.concepts))
        self.update_existing_check.setEnabled(not busy and bool(self.last_result and self.last_result.concepts))
        self.tabs.setEnabled(not busy or kind == "analysis")

    def launch_task(self, operation, on_result, kind):
        self.set_busy(True, kind)
        self.task = Task(operation, self)
        task = self.task
        task.progress.connect(self.log)
        task.resultReady.connect(on_result)
        task.failed.connect(self.on_error)
        task.finished.connect(lambda: self.task_stopped(task))
        task.start()

    def task_stopped(self, task):
        if task.isInterruptionRequested() and not getattr(task,'_completed_write',False) and not self._closing:
            self.status_label.setText("已取消，可以重新分析。")
        if self.task is task:
            self.task = None
            self.set_busy(False)
        task.deleteLater()
        if self._closing:
            self.close()

    def start_analysis(self):
        try:
            text = self.text_input.toPlainText().strip()
            if not text:
                raise ValueError("请先粘贴对话，或点击「体验示例」。")
            source = self._source if text == (self._import_text or "").strip() else "粘贴或编辑的对话"
            conv = parse_text(text, source)
            config = copy.deepcopy(self.config)
            if config.use_ai_extraction:
                AIClient(config)  # Validate credentials before changing the screen.
            self.last_result = None
            self.current_concept = None
            self.result_list.clear()
            self.status_label.setText("正在分析，请稍候…")
            self.log(f"开始处理 {len(conv.messages)} 条消息。")
            def operation(task):
                task.progress.emit("正在提取数学知识及其联系…" if config.use_ai_extraction else "使用本地提取；关系仅根据明确提及建立。")
                return analyze_conversation(conv,config,task.progress.emit,task.isInterruptionRequested)
            self.launch_task(operation, self.show_result, "analysis")
        except Exception as err:
            QMessageBox.warning(self, "暂时无法分析", str(err))

    def cancel_task(self):
        if self.task:
            self.task.requestInterruption()
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("正在取消；当前网络请求结束后停止。")
            self.log("已请求取消，不会保存本次结果。")

    def show_result(self, result):
        self.update_existing_check.setChecked(False)
        self.last_result = result
        self.current_concept = None
        self.result_list.clear()
        for c in result.concepts:
            item = QListWidgetItem(f"{c.title}\n{c.category} · {c.kind}")
            item.setData(Qt.ItemDataRole.UserRole, c)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.result_list.addItem(item)
        self.update_count()
        self.graph_preview.set_graph(result.concepts, result.connections)
        if result.concepts:
            self.result_list.setCurrentRow(0)
            self.status_label.setText(f"{len(result.connections)} 条知识联系 · 可编辑后保存")
        else:
            self.render_preview.set_markdown("# 暂未发现实质数学内容\n\n可以补充定义、公式或推导后重新分析。")
            self.status_label.setText("未提取到知识点")
        self.save_btn.setEnabled(bool(result.concepts) and not self.task)
        self.log(f"完成：{len(result.concepts)} 个知识点，{len(result.connections)} 条联系。")
        for warning in result.warnings:self.log(warning)

    def select_concept(self, item, previous=None):
        if self._updating or not item:
            return
        if self.current_concept and not self.commit_edits():
            return
        self.current_concept = item.data(Qt.ItemDataRole.UserRole)
        c = self.current_concept
        self.title_edit.setText(c.title)
        self.category_edit.setText(c.category)
        self.tags_edit.setText(", ".join(c.tags))
        self.content_edit.setPlainText(c.content)
        self.refresh_preview()

    def refresh_preview(self):
        if self.current_concept:
            c = self.current_concept
            self.note_heading.setText(f"{c.category}  /  {c.kind}  ·  {len(c.relations)} 个关联")
            self.render_preview.set_markdown(build_concept_note(c,styled=self.config.math_note_style), tags=[c.category, c.kind] + c.tags)

    def commit_edits(self):
        if not self.current_concept:
            return True
        c = self.current_concept
        title = self.title_edit.text().strip()
        if not title or not self.content_edit.toPlainText().strip():
            QMessageBox.warning(self, "修改未应用", "标题和正文不能为空。")
            return False
        if self.last_result and any(x is not c and x.title == title for x in self.last_result.concepts):
            QMessageBox.warning(self, "修改未应用", "已有同名知识点，请使用不同标题。")
            return False
        old_title = c.title
        c.title = title
        c.category = self.category_edit.text().strip() or "未分类"
        c.tags = [t.strip() for t in self.tags_edit.text().replace("，", ",").split(",") if t.strip()]
        c.content = self.content_edit.toPlainText().strip()
        if self.last_result:
            if old_title != title:
                for other in self.last_result.concepts:
                    other.related = [title if x == old_title else x for x in other.related]
                    for relation in other.relations:
                        if relation.get("target") == old_title:
                            relation["target"] = title
                for edge in self.last_result.connections:
                    for key in ("source", "target"):
                        if edge[key] == old_title:
                            edge[key] = title
            self._updating = True
            for i in range(self.result_list.count()):
                item = self.result_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) is c:
                    item.setText(f"{c.title}\n{c.category} · {c.kind}")
            self._updating = False
            self.graph_preview.set_graph(self.last_result.concepts, self.last_result.connections)
        return True

    def apply_edits_and_preview(self):
        if self.commit_edits():
            self.refresh_preview()
            self.tabs.setCurrentIndex(0)

    def edit_relations(self):
        if not self.current_concept or not self.commit_edits():return
        from ui.relations_dialog import RelationsDialog
        dialog=RelationsDialog(self.current_concept,[c.title for c in self.last_result.concepts],self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.update_relations(dialog.relations())

    def update_relations(self,relations):
        c=self.current_concept
        for other in self.last_result.concepts:
            if other is not c:
                other.relations=[r for r in other.relations if r.get('target')!=c.title]
                other.related=[t for t in other.related if t!=c.title]
        c.relations=relations
        c.related=list(dict.fromkeys(r['target'] for r in relations))
        remaining=[e for e in self.last_result.connections if e['source']!=c.title and e['target']!=c.title]
        self.last_result.connections=connect_concepts(self.last_result.concepts,remaining)
        self.graph_preview.set_graph(self.last_result.concepts,self.last_result.connections)
        self.refresh_preview()
        self.status_label.setText(f'{len(self.last_result.connections)} 条知识联系 · 修改已应用')

    def tab_changed(self, index):
        if index in (0, 2) and self.current_concept and self.commit_edits():
            self.refresh_preview()

    def navigate_note(self, title):
        from core.obsidian import sanitize_filename
        if self.last_result:
            for i in range(self.result_list.count()):
                c = self.result_list.item(i).data(Qt.ItemDataRole.UserRole)
                if c.title == title or sanitize_filename(c.title) == title:
                    self.result_list.setCurrentRow(i)
                    self.tabs.setCurrentIndex(0)
                    return
        self.status_label.setText(f"「{title}」尚未在本次对话生成，可在 Obsidian 中继续补充。")

    def update_count(self, *args):
        if self._updating:
            return
        count = sum(self.result_list.item(i).checkState() == Qt.CheckState.Checked for i in range(self.result_list.count()))
        self.count_label.setText(f"{count} / {self.result_list.count()} 个已选")
        if not self.task:
            self.save_btn.setEnabled(count > 0)
            self.diff_btn.setEnabled(count > 0)
            self.update_existing_check.setEnabled(count > 0)

    def save_to_vault(self,checked=False,preview=False):
        if self.task or not self.last_result or not self.commit_edits():
            return
        if not self.config.vault_path:
            self.open_settings()
            if not self.config.vault_path:
                return
        result = copy.deepcopy(self.last_result)
        result.concepts = [copy.deepcopy(self.result_list.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.result_list.count()) if self.result_list.item(i).checkState() == Qt.CheckState.Checked]
        if not result.concepts:
            return
        result.connections = connect_concepts(result.concepts)
        config = copy.deepcopy(self.config)
        update_existing=self.update_existing_check.isChecked()
        self.status_label.setText("正在保存笔记与知识联系…")
        def operation(task):
            task.progress.emit('准备笔记并核对已有知识联系…')
            if preview:return prepare_import(result,config,task.progress.emit,task.isInterruptionRequested,update_existing=update_existing)
            saved=save_import(result,config,task.progress.emit,task.isInterruptionRequested,update_existing=update_existing)
            task._completed_write=True
            return saved
        self.launch_task(operation, (lambda plan:self.show_save_diff(plan,config)) if preview else self.saved, "save")

    def show_save_diff(self,plan,config):
        dialog=QDialog(self)
        dialog.setWindowTitle('保存变更预览')
        dialog.resize(980,750)
        layout=QVBoxLayout(dialog)
        layout.addWidget(label('本次选择：更新已有笔记' if plan.update_existing else '本次选择：独立保存，创建本次导入的笔记与知识地图'))
        layout.addWidget(label(f"新增 {plan.counts['created']} · 更新 {plan.counts['updated']} · 跳过 {plan.counts['skipped']}；+ 表示增加，- 表示旧内容。"))
        diff=QPlainTextEdit(plan.diff())
        diff.setReadOnly(True)
        diff.setFont(QFont('Consolas',10))
        layout.addWidget(diff,1)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        # Run after the planning thread's native finished signal cleans it up.
        def show():
            if dialog.exec()==QDialog.DialogCode.Accepted:
                from core.obsidian import apply_save_plan
                def operation(task):
                    saved=apply_save_plan(plan,config,task.isInterruptionRequested)
                    task._completed_write=True
                    return saved
                self.launch_task(operation,self.saved,'save')
        QTimer.singleShot(0,show)

    def saved(self, result):
        counts, directory, map_title = result
        text = f"新增 {counts['created']} · 更新 {counts['updated']} · 跳过 {counts['skipped']}"
        self.status_label.setText(text)
        self.log(f"{text}\n保存位置：{directory}\n知识地图：{map_title}")
        if not self._closing:
            self.save_notice.show_success(counts)

    def on_error(self, text):
        self.status_label.setText("处理未完成，可以调整后重试。")
        self.log(text)
        if not self._closing:
            QMessageBox.warning(self, "处理未完成", text)

    def closeEvent(self, event):
        if self.task and self.task.isRunning():
            self._closing = True
            self.task.requestInterruption()
            self.status_label.setText("正在结束当前任务，随后关闭窗口…")
            event.ignore()
        else:
            event.accept()


def run_app(demo=False, verification_output=None):
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("MathObsidianAgent")
    app.setWindowIcon(QIcon(str(resource_path("assets/app.ico"))))
    app.setFont(QFont("Microsoft YaHei", 10))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    if verification_output:
        from ui.verification import verify_window
        QTimer.singleShot(200, lambda:verify_window(win, verification_output, app))
    elif demo:
        QTimer.singleShot(200, win.load_demo)
    return app.exec()
