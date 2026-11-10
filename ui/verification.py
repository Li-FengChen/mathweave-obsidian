"""Portable-bundle verification; invoked explicitly, never during normal startup."""
import json
import time
from pathlib import Path
from PySide6.QtCore import QTimer
from core.config import Config
from core.demo import demo_result
from core.obsidian import save_extraction


def verify_api_keys(folder, parent):
    """Exercise the actual settings window with synthetic credentials only."""
    import os
    from unittest.mock import patch
    from PySide6.QtWidgets import QLineEdit, QApplication
    from core import config as credentials
    from ui.main_window import SettingsDialog

    class SampleKeyring:
        values = {"openai_api_key": "demo-key-for-ui-check", "deepseek_api_key": "demo-deepseek-key"}
        def get_password(self, service, username):
            return self.values.get(username)
        def set_password(self, service, username, value):
            self.values[username] = value
        def delete_password(self, service, username):
            self.values.pop(username, None)

    environment = {name: value for name, value in os.environ.items() if not name.endswith("_API_KEY")}
    backend = SampleKeyring()
    with patch.object(credentials, "keyring", backend), patch.object(credentials, "KEYRING_AVAILABLE", True), patch.dict(os.environ, environment, clear=True), patch.object(Config, "save"):
        dialog = SettingsDialog(Config(use_ai_extraction=False), parent)
        dialog.show()
        QApplication.processEvents()
        editor = dialog.api_key_editor
        assert editor.edit.text() == "demo-key-for-ui-check"
        assert editor.edit.echoMode() == QLineEdit.EchoMode.Password
        dialog.grab().save(str(Path(folder) / "settings-key-hidden.png"))
        editor.visibility_btn.click()
        assert editor.edit.echoMode() == QLineEdit.EchoMode.Normal
        QApplication.processEvents()
        dialog.grab().save(str(Path(folder) / "settings-key-visible.png"))
        editor.visibility_btn.click()
        editor.edit.setText("demo-key-replacement")
        dialog.provider_combo.setCurrentText("deepseek")
        assert editor.edit.text() == "demo-deepseek-key"
        assert editor.edit.echoMode() == QLineEdit.EchoMode.Password
        editor.delete_btn.click()
        assert backend.values["deepseek_api_key"] == "demo-deepseek-key"
        dialog.provider_combo.setCurrentText("openai")
        assert editor.edit.text() == "demo-key-replacement"
        dialog.save_and_close()
        assert backend.values == {"openai_api_key": "demo-key-replacement"}
        assert dialog.result() == SettingsDialog.DialogCode.Accepted
        dialog.deleteLater()
        cancelled = SettingsDialog(Config(use_ai_extraction=False), parent)
        cancelled.api_key_editor.delete_btn.click()
        cancelled.reject()
        assert backend.values == {"openai_api_key": "demo-key-replacement"}
        cancelled.deleteLater()
        reopened = SettingsDialog(Config(use_ai_extraction=False), parent)
        assert reopened.api_key_edit.text() == "demo-key-replacement"
        assert reopened.api_key_edit.echoMode() == QLineEdit.EchoMode.Password
        reopened.reject()
        reopened.deleteLater()
    return "saved keys loaded; show/hide; isolated provider drafts; deletion on save; cancel preserves key"


def verify_import_choice(window, folder, on_done, on_error):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    config=Config(vault_path=str(folder),use_ai_extraction=False)
    save_extraction(demo_result(),config)
    notes=folder/config.notes_subfolder
    before={p:p.read_bytes() for p in notes.iterdir() if p.is_file()}
    window.config=config
    window.update_vault_label()
    phase=[0]
    deadline=time.monotonic()+20
    assert not window.update_existing_check.isChecked()
    window.save_btn.click()
    def poll():
        try:
            if time.monotonic()>deadline:raise ValueError('import choice timeout')
            if window.task:
                QTimer.singleShot(100,poll)
                return
            if phase[0] in (0,1):
                for path,raw in before.items():assert path.read_bytes()==raw,'unchecked import modified an old file'
                assert len(list((notes/'独立导入').rglob('泰勒公式.md')))==1
                assert window.save_notice.isVisible()
            if phase[0]==0:
                phase[0]=1
                window.save_btn.click()
                QTimer.singleShot(100,poll)
                return
            if phase[0]==1:
                assert '跳过 4' in window.status_label.text()
                phase[0]=2
                window.update_existing_check.setChecked(True)
                window.save_btn.click()
                QTimer.singleShot(100,poll)
                return
            assert (notes/config.index_note_name).with_suffix('.md').read_bytes()!=before[(notes/config.index_note_name).with_suffix('.md')]
            window.load_demo()
            assert not window.update_existing_check.isChecked()
            on_done()
        except Exception as err:on_error(err)
    QTimer.singleShot(100,poll)


class VerificationAI:
    """Deterministic public fixture; never connects to a service."""
    def chat(self,system,user,response_format_json=True):
        from core.maintenance import MERGE_SYSTEM
        notes=json.loads(user)['notes']
        names={n['title']:n['id'] for n in notes}
        if system==MERGE_SYSTEM:
            return json.dumps(dict(same_concept=True,confidence=.99,reason='差商极限的相同定义',covered_ids=[n['id'] for n in notes],aliases=['微商'],content='## 定义\n\n导数是差商极限存在时的值。'),ensure_ascii=False)
        groups=[dict(members=[names['导数'],names['微商']],canonical=names['导数'],confidence=.99,reason='微商明确是导数的别名')] if '导数' in names and '微商' in names else []
        links=[dict(source=names['泰勒公式'],target=names['导数'],relation='依赖',confidence=.99,reason='展开系数使用导数')] if '泰勒公式' in names and '导数' in names else []
        return json.dumps(dict(groups=groups,links=links),ensure_ascii=False)


def verify_window(window, output, app):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        api_keys = verify_api_keys(output.parent, window)
    except Exception as err:
        output.write_text(json.dumps(dict(status='failed',reason=str(err)),ensure_ascii=False),encoding='utf-8')
        app.exit(1)
        return
    deadline = time.monotonic() + 45
    window.load_demo()
    def poll():
        def checked(raw):
            if time.monotonic() > deadline:
                output.write_text(json.dumps({'status':'failed','reason':'renderer timeout'}), encoding='utf-8')
                app.exit(1)
                return
            state = json.loads(raw) if raw else {}
            if not state.get('ready'):
                QTimer.singleShot(200, poll)
                return
            try:
                if state.get('errors') or state.get('mathCount', 0) < 1:
                    raise ValueError(str(state))
                config = Config(vault_path=str(output.parent / 'bundle-vault'))
                Path(config.vault_path).mkdir(parents=True,exist_ok=True)
                first = save_extraction(demo_result(), config)[0]
                second = save_extraction(demo_result(), config)[0]
                assert first['created'] == 4 and second['skipped'] == 4
                from core.obsidian import compose_note
                from ui.maintenance_dialog import MaintenanceDialog
                alias=Path(config.vault_path)/config.notes_subfolder/'微商.md'
                alias.write_text(compose_note(dict(title='微商',category='微积分',kind='定义'), '# 微商\n\n微商就是导数，差商双侧极限存在时的值。\n\n验证人工备注。'),encoding='utf-8')
                before=alias.read_bytes()
                dialog=MaintenanceDialog(config,window,ai_factory=lambda config,cancel_check:VerificationAI())
                phase=['merge']
                def maintenance_poll():
                    if time.monotonic()>deadline:
                        output.write_text(json.dumps(dict(status='failed',reason='maintenance timeout')),encoding='utf-8')
                        app.exit(1)
                        return
                    if dialog.task:
                        QTimer.singleShot(100,maintenance_poll)
                        return
                    try:
                        if phase[0]=='merge':
                            assert dialog.plan and len(dialog.plan.groups)==1,dialog.report.toPlainText()
                            assert dialog.plan.backup_path
                            assert '验证人工备注' in (alias.parent/'导数.md').read_text(encoding='utf-8')
                            phase[0]='undo'
                            dialog.undo()
                            QTimer.singleShot(100,maintenance_poll)
                            return
                        assert alias.read_bytes()==before
                        assert save_extraction(demo_result(),config)[0]['skipped']==4
                        output.write_text(json.dumps(dict(status='passed',api_keys=api_keys,renderer=state,first_save=first,repeat_save=second,import_choice='unchecked leaves old files unchanged; checked updates index; next import resets choice',maintenance='merge, original records and exact undo passed',version=__import__('core.resources',fromlist=['APP_VERSION']).APP_VERSION),ensure_ascii=False,indent=2),encoding='utf-8')
                        dialog.close()
                        app.quit()
                    except Exception as err:
                        output.write_text(json.dumps(dict(status='failed',reason=str(err)),ensure_ascii=False),encoding='utf-8')
                        app.exit(1)
                def imports_checked():
                    dialog.show()
                    dialog.start()
                    QTimer.singleShot(100,maintenance_poll)
                def imports_failed(err):
                    output.write_text(json.dumps(dict(status='failed',reason=str(err)),ensure_ascii=False),encoding='utf-8')
                    app.exit(1)
                verify_import_choice(window,output.parent/'gui-import-vault',imports_checked,imports_failed)
            except Exception as err:
                output.write_text(json.dumps(dict(status='failed', reason=str(err)),ensure_ascii=False), encoding='utf-8')
                app.exit(1)
        window.render_preview.page.runJavaScript('JSON.stringify(window.previewState)', checked)
    QTimer.singleShot(500, poll)
