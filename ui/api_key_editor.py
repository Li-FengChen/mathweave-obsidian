"""Masked credential editor with per-provider drafts and save/cancel semantics."""
from dataclasses import dataclass, field

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel
from core.config import ApiKeyInfo, get_api_key_info, set_api_key, delete_api_key


@dataclass
class KeyDraft:
    original: ApiKeyInfo = field(repr=False)
    text: str = field(repr=False)
    delete_saved: bool = False

    def action(self):
        key = self.text.strip()
        if key and key != (self.original.value or ""):
            return "set"
        if not key and self.delete_saved:
            return "delete"
        return "keep"


class ApiKeyEditor(QWidget):
    def __init__(self, provider, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.drafts = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("输入 API 密钥；Ollama 可留空")
        self.edit.setAccessibleName("API 密钥")
        self.visibility_btn = QPushButton("显示")
        self.visibility_btn.setCheckable(True)
        self.visibility_btn.setToolTip("显示或隐藏当前密钥")
        self.delete_btn = QPushButton("删除")
        self.delete_btn.setToolTip("清空输入；已存密钥在点击保存后删除，取消则保留")
        # Return in the input should save settings, never activate a key action.
        for button in (self.visibility_btn, self.delete_btn):
            button.setAutoDefault(False)
        row.addWidget(self.edit, 1)
        row.addWidget(self.visibility_btn)
        row.addWidget(self.delete_btn)
        layout.addLayout(row)
        self.status = QLabel()
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.edit.textChanged.connect(self.on_text_changed)
        self.visibility_btn.toggled.connect(self.set_visible)
        self.delete_btn.clicked.connect(self.clear_key)
        self.select_provider(provider)

    def select_provider(self, provider):
        self.provider = provider
        if provider not in self.drafts:
            original = get_api_key_info(provider)
            self.drafts[provider] = KeyDraft(original, original.value or "")
        draft = self.drafts[provider]
        self.edit.blockSignals(True)
        self.edit.setText(draft.text)
        self.edit.blockSignals(False)
        self.hide_key()
        self.update_status()

    def set_visible(self, visible):
        self.edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.visibility_btn.setText("隐藏" if visible else "显示")
        if hasattr(self, "status") and self.provider in self.drafts:
            self.update_status()

    def hide_key(self):
        self.visibility_btn.setChecked(False)
        self.set_visible(False)

    def on_text_changed(self, text):
        self.drafts[self.provider].text = text
        if not text:
            self.hide_key()
        self.update_status()

    def clear_key(self):
        draft = self.drafts[self.provider]
        draft.delete_saved = draft.original.source == "keyring"
        self.edit.clear()
        self.hide_key()
        self.update_status()

    def has_pending_changes(self, provider):
        return self.drafts[provider].action() != "keep"

    def update_status(self):
        draft = self.drafts[self.provider]
        action = draft.action()
        if draft.original.read_failed:
            message = "系统密钥读取失败。请检查凭据服务后重新打开设置。"
        elif action == "delete":
            message = "点击保存后删除此服务商的已存密钥；取消则保留。"
            if draft.original.has_environment_key:
                message += "删除后仍会使用环境变量提供的密钥。"
        elif action == "set":
            message = "密钥已修改，点击保存后生效。切换服务商会保留本次修改。"
        elif draft.original.source == "environment":
            message = f"密钥来自 {self.provider.upper()}_API_KEY 环境变量；如需彻底删除，请在系统中移除该变量。"
        elif not draft.text and draft.original.value:
            message = "输入已清空，保存时保留原密钥；要移除已存密钥，请点击删除。"
        elif draft.original.value:
            message = ("密钥正在显示，点击隐藏可遮住内容。" if self.visibility_btn.isChecked()
                       else "已载入此服务商的已存密钥，点击显示可查看。")
        else:
            message = "尚未保存密钥。Ollama 可留空。"
        self.status.setText(message)
        self.visibility_btn.setEnabled(bool(draft.text))
        self.delete_btn.setEnabled(bool(draft.text) or (bool(draft.original.value) and not draft.delete_saved))

    def save_changes(self, save_settings):
        """Commit edited providers; restore credentials if any write fails."""
        pending = [(provider, draft) for provider, draft in self.drafts.items()
                   if draft.action() != "keep"]
        if any(draft.original.read_failed for _, draft in pending):
            raise ValueError("无法读取原密钥，本次密钥更改未保存。请检查系统凭据服务后重试。")
        for provider, draft in pending:
            current = get_api_key_info(provider)
            if current.read_failed or current.source != draft.original.source or current.value != draft.original.value:
                raise ValueError("密钥在设置打开期间已发生变化。本次更改未保存，请重新打开设置。")
        attempted = []
        try:
            for provider, draft in pending:
                attempted.append((provider, draft))
                if draft.action() == "delete":
                    if not delete_api_key(provider):
                        raise ValueError("密钥未能从系统密钥链删除，请检查系统凭据服务后重试。")
                elif not set_api_key(draft.text.strip(), provider):
                    raise ValueError("密钥未能存入系统密钥链，请检查系统凭据服务后重试。")
            save_settings()
        except Exception as err:
            restored = True
            for provider, draft in reversed(attempted):
                if draft.original.source == "keyring":
                    ok = set_api_key(draft.original.value, provider)
                else:
                    ok = delete_api_key(provider)
                restored = ok and restored
            if not restored:
                raise ValueError("保存失败，部分密钥更改未能恢复。请重新打开设置检查各服务商密钥。") from err
            raise
