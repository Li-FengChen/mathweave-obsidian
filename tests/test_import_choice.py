import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import Config
from core.demo import demo_result
from core.extractor import ExtractionResult, MathConcept
from core.obsidian import apply_save_plan, compose_note, save_extraction, split_frontmatter
from core.services import prepare_import, save_import
from core.storage import digest, FileTransaction, atomic_write


class ImportChoiceTests(unittest.TestCase):
    def baseline(self, root):
        config=Config(vault_path=root,use_ai_extraction=False)
        save_extraction(demo_result(),config)
        note=Path(root)/'数学笔记/泰勒公式.md'
        note.write_text(note.read_text(encoding='utf-8')+'\n人工旧备注：需保留。\n',encoding='utf-8')
        before={p.relative_to(root).as_posix():p.read_bytes() for p in (Path(root)/'数学笔记').iterdir() if p.is_file()}
        result=demo_result()
        result.source='本次数学对话'
        result.concepts[1].content+='\n本次新增讨论。'
        return config,result,before

    def test_unchecked_preserves_all_old_notes_index_and_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            config,result,before=self.baseline(root)
            config.use_ai_extraction=True
            with patch('core.services.scan_library',side_effect=AssertionError('未勾选时不应扫描旧库')),patch('ai.client.AIClient',side_effect=AssertionError('不应核对旧笔记')):
                plan=prepare_import(result,config,update_existing=False)
                self.assertFalse(plan.update_existing)
                self.assertTrue(all('/独立导入/' in name for name in plan.updates))
                apply_save_plan(plan,config)
            for name,raw in before.items():self.assertEqual((Path(root)/name).read_bytes(),raw)
            self.assertEqual(plan.counts,dict(created=4,updated=0,skipped=0))
            self.assertIn('本次新增讨论',(Path(plan.directory)/'泰勒公式.md').read_text(encoding='utf-8'))
            props,body=split_frontmatter((Path(plan.directory)/'泰勒公式.md').read_text(encoding='utf-8'))
            target=(Path(plan.directory)/'导数').relative_to(root).as_posix()
            self.assertIn(f'[[{target}|导数]]',body)
            self.assertTrue((Path(plan.directory)/config.index_note_name).with_suffix('.md').exists())

    def test_repeat_save_skips_and_a_new_import_remains_independent(self):
        with tempfile.TemporaryDirectory() as root:
            config,result,_=self.baseline(root)
            _,directory,_=save_import(result,config,update_existing=False)
            before={p:p.read_bytes() for p in Path(directory).iterdir() if p.is_file()}
            times={p:p.stat().st_mtime_ns for p in before}
            counts,repeated,_=save_import(result,config,update_existing=False)
            self.assertEqual(repeated,directory)
            self.assertEqual(counts,dict(created=0,updated=0,skipped=4))
            self.assertEqual(times,{p:p.stat().st_mtime_ns for p in before})
            another=copy.deepcopy(result)
            another.import_id='另一次导入'
            counts,new_directory,_=save_import(another,config,update_existing=False)
            self.assertNotEqual(new_directory,directory)
            self.assertEqual(counts['created'],4)
            for path,raw in before.items():self.assertEqual(path.read_bytes(),raw)

    def test_changes_create_another_revision_instead_of_overwriting(self):
        with tempfile.TemporaryDirectory() as root:
            config,result,_=self.baseline(root)
            _,directory,_=save_import(result,config,update_existing=False)
            before={p:p.read_bytes() for p in Path(directory).iterdir() if p.is_file()}
            result.concepts[1].tags.append('本次修订')
            _,revision,_=save_import(result,config,update_existing=False)
            self.assertNotEqual(directory,revision)
            for path,raw in before.items():self.assertEqual(path.read_bytes(),raw)

    def test_checked_updates_old_note_and_preserves_manual_content(self):
        with tempfile.TemporaryDirectory() as root:
            config,result,_=self.baseline(root)
            counts,directory,_=save_import(result,config,update_existing=True)
            self.assertEqual(Path(directory),Path(root)/'数学笔记')
            self.assertGreater(counts['updated'],0)
            text=(Path(directory)/'泰勒公式.md').read_text(encoding='utf-8')
            self.assertIn('人工旧备注',text)
            self.assertIn('本次新增讨论',text)

    def test_checked_finds_nested_note_even_when_ai_linking_is_disabled(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'数学笔记/课程'
            folder.mkdir(parents=True)
            path=folder/'导数.md'
            path.write_text(compose_note(dict(title='导数',kind='定义',category='微积分'),'# 导数\n\n人工内容。'),encoding='utf-8')
            result=ExtractionResult(True,.9,[MathConcept('导数',content='补充定义与条件。')])
            config=Config(vault_path=root,use_ai_extraction=False,link_existing_on_save=False)
            self.assertEqual(save_import(result,config,update_existing=True)[0]['updated'],1)
            self.assertIn('补充定义',path.read_text(encoding='utf-8'))
            self.assertFalse((Path(root)/'数学笔记/导数.md').exists())

    def test_apply_guard_cannot_write_existing_markdown_in_unchecked_plan(self):
        with tempfile.TemporaryDirectory() as root:
            config,result,before=self.baseline(root)
            plan=prepare_import(result,config,update_existing=False)
            name='数学笔记/泰勒公式.md'
            plan.updates[name]='错误覆盖内容'
            plan.snapshots[name]=digest((Path(root)/name).read_bytes())
            with self.assertRaises(ValueError):apply_save_plan(plan,config)
            self.assertEqual((Path(root)/name).read_bytes(),before[name])

    def test_unchecked_does_not_recover_or_modify_an_older_interrupted_write(self):
        with tempfile.TemporaryDirectory() as root:
            config,result,before=self.baseline(root)
            path=Path(root)/'数学笔记/泰勒公式.md'
            index=Path(root)/'数学笔记/数学知识索引.md'
            transaction=FileTransaction(root)
            transaction.stage(path,'上次中断时留下的内容')
            transaction.stage(index,'中断前未写入的索引')
            def interrupt(target,content):
                if Path(target)==index:raise KeyboardInterrupt()
                return atomic_write(target,content)
            with patch('core.storage.atomic_write',side_effect=interrupt),self.assertRaises(KeyboardInterrupt):
                transaction.commit()
            interrupted=path.read_bytes()
            save_import(result,config,update_existing=False)
            self.assertEqual(path.read_bytes(),interrupted)
            self.assertEqual(index.read_bytes(),before['数学笔记/数学知识索引.md'])
            with self.assertRaisesRegex(RuntimeError,'已恢复上次中断'):
                save_import(result,config,update_existing=True)
            self.assertEqual(path.read_bytes(),before['数学笔记/泰勒公式.md'])


if __name__=='__main__':unittest.main()
