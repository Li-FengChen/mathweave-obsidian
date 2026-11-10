"""Credential lifecycle checks use a fake keyring, never the user's secrets."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, Qt
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from PySide6.QtWidgets import QApplication, QLineEdit
from core import config as credentials
from core.config import Config
from ui.api_key_editor import ApiKeyEditor
from ui.main_window import SettingsDialog


class MemoryKeyring:
    def __init__(self):
        self.values = {"openai_api_key": "fake-openai-original", "deepseek_api_key": "fake-deepseek-original"}
        self.writes = []
        self.fail_value = None
        self.fail_delete = False

    def get_password(self, service, username):
        return self.values.get(username)

    def set_password(self, service, username, value):
        self.writes.append(("set", username))
        if value == self.fail_value:
            # Emulate a backend which fails after updating the credential.
            self.values[username] = value
            raise RuntimeError(value)
        self.values[username] = value

    def delete_password(self, service, username):
        self.writes.append(("delete", username))
        if self.fail_delete:
            raise RuntimeError("fake-openai-original")
        self.values.pop(username, None)


class ApiKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.backend = MemoryKeyring()
        self.patches = [patch.object(credentials, "KEYRING_AVAILABLE", True),
                        patch.object(credentials, "keyring", self.backend),
                        patch.dict(os.environ, {}, clear=True)]
        for mocked in self.patches:
            mocked.start()
            self.addCleanup(mocked.stop)
        self.widgets = []
        self.addCleanup(self.close_widgets)

    def close_widgets(self):
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        self.app.processEvents()

    def editor(self):
        editor = ApiKeyEditor("openai")
        self.widgets.append(editor)
        return editor

    def dialog(self):
        dialog = SettingsDialog(Config(use_ai_extraction=False))
        self.widgets.append(dialog)
        return dialog

    def test_saved_keys_load_masked_and_provider_switch_keeps_them_separate(self):
        editor = self.editor()
        self.assertEqual(editor.edit.text(), "fake-openai-original")
        self.assertEqual(editor.edit.echoMode(), QLineEdit.EchoMode.Password)
        editor.visibility_btn.click()
        self.assertEqual(editor.edit.echoMode(), QLineEdit.EchoMode.Normal)
        self.assertEqual(editor.visibility_btn.text(), "隐藏")
        editor.visibility_btn.click()
        self.assertEqual(editor.edit.echoMode(), QLineEdit.EchoMode.Password)
        editor.visibility_btn.click()
        editor.select_provider("deepseek")
        self.assertEqual(editor.edit.text(), "fake-deepseek-original")
        self.assertEqual(editor.edit.echoMode(), QLineEdit.EchoMode.Password)
        editor.select_provider("ollama")
        self.assertFalse(editor.visibility_btn.isEnabled())
        self.assertEqual(editor.edit.text(), "")

    def test_deletion_is_staged_and_cancel_preserves_credential(self):
        dialog = self.dialog()
        dialog.api_key_editor.visibility_btn.click()
        dialog.api_key_editor.delete_btn.click()
        self.assertEqual(dialog.api_key_edit.text(), "")
        self.assertEqual(dialog.api_key_edit.echoMode(), QLineEdit.EchoMode.Password)
        self.assertEqual(self.backend.writes, [])
        dialog.reject()
        self.assertEqual(credentials.get_api_key(), "fake-openai-original")

    def test_save_deletion_does_not_remove_other_providers(self):
        dialog = self.dialog()
        dialog.api_key_editor.delete_btn.click()
        with patch.object(Config, "save") as save:
            dialog.save_and_close()
            save.assert_called_once()
        self.assertIsNone(credentials.get_api_key())
        self.assertEqual(credentials.get_api_key("deepseek"), "fake-deepseek-original")
        self.assertEqual(dialog.result(), SettingsDialog.DialogCode.Accepted)

    def test_unchanged_or_manually_empty_field_preserves_stored_key(self):
        editor = self.editor()
        editor.save_changes(lambda: None)
        editor.edit.clear()
        editor.save_changes(lambda: None)
        self.assertEqual(self.backend.writes, [])
        self.assertEqual(credentials.get_api_key(), "fake-openai-original")
        self.assertFalse(editor.has_pending_changes("openai"))

    def test_provider_drafts_commit_to_the_correct_provider(self):
        dialog = self.dialog()
        dialog.api_key_edit.setText("fake-openai-replacement")
        dialog.provider_combo.setCurrentText("deepseek")
        self.assertEqual(dialog.api_key_edit.text(), "fake-deepseek-original")
        dialog.api_key_editor.delete_btn.click()
        dialog.provider_combo.setCurrentText("openai")
        self.assertEqual(dialog.api_key_edit.text(), "fake-openai-replacement")
        with patch.object(Config, "save"):
            dialog.save_and_close()
        self.assertEqual(credentials.get_api_key(), "fake-openai-replacement")
        self.assertIsNone(credentials.get_api_key("deepseek"))

    def test_failed_key_write_restores_all_attempted_provider_changes(self):
        editor = self.editor()
        original = self.backend.values.copy()
        editor.edit.setText("fake-openai-replacement")
        editor.select_provider("deepseek")
        editor.edit.setText("fake-failing-secret")
        self.backend.fail_value = "fake-failing-secret"
        with self.assertLogs("math_obsidian_agent", level="ERROR") as logs:
            with self.assertRaises(ValueError):
                editor.save_changes(lambda: self.fail("Settings must not be saved"))
        self.assertEqual(self.backend.values, original)
        self.assertNotIn("fake-failing-secret", "\n".join(logs.output))

    def test_failed_settings_write_restores_deleted_key(self):
        editor = self.editor()
        editor.delete_btn.click()
        def fail_save():
            raise OSError("configuration is read only")
        with self.assertRaises(OSError):
            editor.save_changes(fail_save)
        self.assertEqual(credentials.get_api_key(), "fake-openai-original")

    def test_concurrent_credential_change_is_not_overwritten(self):
        editor = self.editor()
        editor.edit.setText("fake-draft-key")
        self.backend.values["openai_api_key"] = "fake-externally-changed-key"
        with self.assertRaisesRegex(ValueError, "发生变化"):
            editor.save_changes(lambda: self.fail("Settings must not be saved"))
        self.assertEqual(credentials.get_api_key(), "fake-externally-changed-key")
        self.assertEqual(self.backend.writes, [])

    def test_delete_failure_never_reports_success(self):
        dialog = self.dialog()
        dialog.api_key_editor.delete_btn.click()
        self.backend.fail_delete = True
        with patch.object(Config, "save") as save, patch("ui.main_window.QMessageBox.warning") as warning:
            dialog.save_and_close()
            save.assert_not_called()
            warning.assert_called_once()
            self.assertIn("删除", warning.call_args.args[2])
        self.assertEqual(dialog.result(), SettingsDialog.DialogCode.Rejected)
        self.assertEqual(credentials.get_api_key(), "fake-openai-original")

    def test_environment_fallback_is_identified_and_not_silently_removed(self):
        self.backend.values.pop("openai_api_key")
        os.environ["OPENAI_API_KEY"] = "fake-environment-secret"
        editor = self.editor()
        self.assertIn("环境变量", editor.status.text())
        self.assertNotIn("fake-environment-secret", repr(credentials.get_api_key_info()))
        editor.delete_btn.click()
        editor.save_changes(lambda: None)
        self.assertEqual(self.backend.writes, [])
        self.assertEqual(credentials.get_api_key(), "fake-environment-secret")
        self.assertIn("系统中移除", editor.status.text())
        self.assertTrue(credentials.delete_api_key())  # Already absent is successful.

    def test_key_never_enters_config_json(self):
        dialog = self.dialog()
        dialog.api_key_edit.setText("fake-private-replacement")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with patch.object(credentials, "CONFIG_DIR", Path(directory)), patch.object(credentials, "CONFIG_FILE", path):
                dialog.save_and_close()
            self.assertNotIn("fake-private-replacement", path.read_text(encoding="utf-8"))
        self.assertEqual(credentials.get_api_key(), "fake-private-replacement")

    def test_unchanged_loaded_key_can_test_connection(self):
        dialog = self.dialog()
        loop = QEventLoop()
        with patch("ui.main_window.AIClient") as client:
            client.return_value.test_connection.return_value = (True, "fake connection passed")
            dialog.test_btn.click()
            self.assertIsNotNone(dialog.test_task)
            self.assertFalse(dialog.api_key_editor.isEnabled())
            dialog.test_task.finished.connect(loop.quit)
            QTimer.singleShot(3000, loop.quit)
            loop.exec()
            self.assertIsNone(dialog.test_task)
            self.assertEqual(dialog.test_status.text(), "fake connection passed")
            self.assertTrue(dialog.api_key_editor.isEnabled())
        dialog.api_key_editor.delete_btn.click()
        dialog.test_btn.click()
        self.assertIsNone(dialog.test_task)
        self.assertIn("先保存密钥更改", dialog.test_status.text())


if __name__ == "__main__":
    unittest.main()
