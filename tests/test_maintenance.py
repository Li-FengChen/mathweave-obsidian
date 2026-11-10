import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.config import Config
from core.extractor import ExtractionResult,MathConcept,extract_local
from core.parser import parse_text
from core.formatting import format_math_content
from core.obsidian import compose_note,split_frontmatter,prepare_save,apply_save_plan,save_extraction
from core.maintenance import PLAN_SYSTEM,MERGE_SYSTEM,build_maintenance_plan,apply_maintenance_plan,undo_last_maintenance,maintenance_batches
from core.services import prepare_import,conversation_chunks,extract_long_conversation,analyze_conversation
from core.storage import FileTransaction,VaultLock,atomic_write,recover_incomplete,digest


class FakeMathAI:
    def __init__(self,confirmed=True,confidence=.99):
        self.confirmed=confirmed
        self.confidence=confidence
        self.calls=[]

    def chat(self,system,user,response_format_json=True):
        data=json.loads(user)
        self.calls.append(data)
        notes=data['notes']
        titles={n['title']:n['id'] for n in notes}
        if system==MERGE_SYSTEM:
            return json.dumps(dict(same_concept=self.confirmed,confidence=.99,reason='均为一点处差商极限的定义',covered_ids=[n['id'] for n in notes],aliases=['微商'],content='## 定义\n\n导数是差商的极限。\n\n## 证明\n\n原记录给出的证明要核对。'),ensure_ascii=False)
        groups=[]
        if '导数' in titles and '微商' in titles:
            groups=[dict(members=[titles['导数'],titles['微商']],canonical=titles['导数'],confidence=self.confidence,reason='同一差商极限定义，条件一致')]
        links=[]
        if '泰勒公式' in titles and '导数' in titles:
            links=[dict(source=titles['泰勒公式'],target=titles['导数'],relation='依赖',confidence=.99,reason='系数使用各阶导数')]
        return json.dumps(dict(groups=groups,links=links),ensure_ascii=False)


class MaintenanceTests(unittest.TestCase):
    def setup_vault(self,root):
        folder=Path(root)/'数学笔记'
        folder.mkdir()
        for title,body in [('导数','## 定义\n\n$$f\\prime(a)=\\lim_{h\\to0}\\frac{f(a+h)-f(a)}h$$\n\n### 人工备注\n\n双侧极限必须存在。'),('微商','## 定义\n\n微商也叫导数，是差商极限。\n\n## 证明\n\n另一个证明记录。'),('泰勒公式','## 定理\n\n系数依赖导数，必须有相应可微条件。\n\n$$f(x)=f(a)+f\\prime(a)(x-a)+o(x-a)$$')]:
            (folder/(title+'.md')).write_text(compose_note(dict(title=title,kind='定义' if title!='泰勒公式' else '定理',category='微积分',created='2020-01-01',tags=['数学','人工']), '# '+title+'\n\n'+body),encoding='utf-8')
        (Path(root)/'生活.md').write_text('购物清单\n\n买牛奶',encoding='utf-8')
        return Config(vault_path=root),{p.relative_to(root).as_posix():p.read_bytes() for p in Path(root).rglob('*.md')}

    def test_merge_links_backup_and_exact_undo(self):
        with tempfile.TemporaryDirectory() as root:
            config,before=self.setup_vault(root)
            plan=build_maintenance_plan(config,FakeMathAI())
            self.assertEqual(len(plan.groups),1)
            self.assertEqual(len(plan.links),1)
            self.assertNotIn('生活.md',plan.updates)
            summary=apply_maintenance_plan(plan,config)
            canonical=(Path(root)/'数学笔记/导数.md').read_text(encoding='utf-8')
            props,body=split_frontmatter(canonical)
            self.assertEqual(props['created'],'2020-01-01')
            self.assertIn('双侧极限必须存在。',body)
            self.assertIn('另一个证明记录。',body)
            self.assertIn('[!tip]- 证明',body)
            self.assertIn('[[数学笔记/泰勒公式|泰勒公式]]',body)
            self.assertIn('[[数学笔记/导数|导数]]',(Path(root)/'数学笔记/泰勒公式.md').read_text(encoding='utf-8'))
            self.assertEqual(split_frontmatter((Path(root)/'数学笔记/微商.md').read_text(encoding='utf-8'))[0]['kind'],'重定向')
            manifest=json.loads((Path(summary['backup'])/'manifest.json').read_text(encoding='utf-8'))
            for entry in manifest['files']:
                if entry['path'] in before:
                    self.assertEqual((Path(summary['backup'])/entry['backup']).read_bytes(),before[entry['path']])
            undo_last_maintenance(config)
            for name,raw in before.items():self.assertEqual((Path(root)/name).read_bytes(),raw)
            self.assertFalse((Path(root)/'数学笔记/数学知识索引.md').exists())
            self.assertFalse((Path(root)/'数学笔记/.agent_meta.json').exists())

    def test_repeated_maintenance_does_not_rewrite(self):
        with tempfile.TemporaryDirectory() as root:
            config,_=self.setup_vault(root)
            apply_maintenance_plan(build_maintenance_plan(config,FakeMathAI()),config)
            plan=build_maintenance_plan(config,FakeMathAI())
            self.assertEqual(plan.updates,{})
            self.assertEqual(plan.groups,[])

    def test_uncertain_or_second_check_rejected_stays_separate(self):
        for ai in (FakeMathAI(confirmed=False),FakeMathAI(confidence=.6)):
            with self.subTest(ai=ai),tempfile.TemporaryDirectory() as root:
                config,_=self.setup_vault(root)
                plan=build_maintenance_plan(config,ai)
                self.assertEqual(plan.groups,[])
                apply_maintenance_plan(plan,config)
                self.assertNotEqual(split_frontmatter((Path(root)/'数学笔记/微商.md').read_text(encoding='utf-8'))[0]['kind'],'重定向')

    def test_changed_note_stops_apply_and_changed_after_stops_undo(self):
        with tempfile.TemporaryDirectory() as root:
            config,before=self.setup_vault(root)
            plan=build_maintenance_plan(config,FakeMathAI())
            path=Path(root)/'数学笔记/导数.md'
            path.write_text(path.read_text(encoding='utf-8')+'\n人工后续修改',encoding='utf-8')
            with self.assertRaises(RuntimeError):apply_maintenance_plan(plan,config)
            self.assertEqual((Path(root)/'数学笔记/微商.md').read_bytes(),before['数学笔记/微商.md'])
            apply_maintenance_plan(build_maintenance_plan(config,FakeMathAI()),config)
            path.write_text(path.read_text(encoding='utf-8')+'\n整理后新增',encoding='utf-8')
            with self.assertRaises(RuntimeError):undo_last_maintenance(config)
            self.assertIn('整理后新增',path.read_text(encoding='utf-8'))

    def test_redirect_remains_redirect_on_new_import(self):
        with tempfile.TemporaryDirectory() as root:
            config,_=self.setup_vault(root)
            apply_maintenance_plan(build_maintenance_plan(config,FakeMathAI()),config)
            save_extraction(ExtractionResult(True,.9,[MathConcept('微商',content='新记录：单侧导数要分别讨论。')]),config)
            redirect=Path(root)/'数学笔记/微商.md'
            self.assertEqual(split_frontmatter(redirect.read_text(encoding='utf-8'))[0]['kind'],'重定向')
            props,body=split_frontmatter((Path(root)/'数学笔记/导数.md').read_text(encoding='utf-8'))
            self.assertEqual(props['title'],'导数')
            self.assertIn('单侧导数要分别讨论',body)

    def test_save_adds_existing_reciprocal_links_and_preview_is_readonly(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'数学笔记'
            folder.mkdir()
            old=folder/'导数.md'
            old.write_text(compose_note(dict(title='导数',category='微积分',tags=['数学']),'# 导数\n\n人工备注：可导必连续。'),encoding='utf-8')
            raw=old.read_bytes()
            result=ExtractionResult(True,.9,[MathConcept('泰勒公式',kind='定理',category='微积分',content='## 定理\n\n泰勒系数使用导数。')],source='测试素材')
            config=Config(vault_path=root)
            plan=prepare_import(result,config,ai_client=FakeMathAI())
            self.assertEqual(raw,old.read_bytes())
            self.assertIn('泰勒公式',plan.diff())
            apply_save_plan(plan,config)
            self.assertIn('[[数学笔记/泰勒公式|泰勒公式]]',old.read_text(encoding='utf-8'))
            self.assertIn('人工备注：可导必连续',old.read_text(encoding='utf-8'))
            self.assertIn('[[数学笔记/导数|导数]]',(folder/'泰勒公式.md').read_text(encoding='utf-8'))

    def test_scope_default_excludes_nonmath_and_corrupt_note_is_reported(self):
        with tempfile.TemporaryDirectory() as root:
            config,_=self.setup_vault(root)
            bad=Path(root)/'数学笔记/坏属性.md'
            bad.write_text('---\ntags: [missing\n---\n正文',encoding='utf-8')
            plan=build_maintenance_plan(config,FakeMathAI(),scope='vault')
            self.assertEqual(len(plan.notes),3)
            self.assertTrue(plan.warnings)

    def test_callouts_preserve_formula_and_are_idempotent(self):
        content='# 定理\n\n## 定理\n\n成立的条件。\n\n## 证明\n\n$$\n\\begin{aligned} a&=b\\\\c&=d\\end{aligned}\n$$\n\n### 人工备注\n\n保留。'
        styled=format_math_content(content,'定理')
        self.assertIn('> [!tip]- 证明',styled)
        self.assertIn('### 人工备注',styled)
        self.assertEqual(format_math_content(styled,'定理'),styled)


class TransactionTests(unittest.TestCase):
    def test_failure_restores_all_files_and_meta(self):
        with tempfile.TemporaryDirectory() as root:
            a,b=Path(root)/'a.md',Path(root)/'b.md'
            a.write_bytes(b'old a');b.write_bytes(b'old b')
            txn=FileTransaction(root)
            txn.stage(a,'new a');txn.stage(b,'new b')
            failed=False
            def fail(path,text):
                nonlocal failed
                if Path(path)==b and not failed:
                    failed=True
                    raise OSError('模拟磁盘写入失败')
                return atomic_write(path,text)
            with patch('core.storage.atomic_write',side_effect=fail),self.assertRaises(OSError):txn.commit()
            self.assertEqual(a.read_bytes(),b'old a')
            self.assertEqual(b.read_bytes(),b'old b')

    def test_process_lock_and_expected_absence(self):
        with tempfile.TemporaryDirectory() as root:
            with VaultLock(root):
                with self.assertRaises(RuntimeError):
                    with VaultLock(root):pass
            path=Path(root)/'edited.md'
            path.write_text('created elsewhere',encoding='utf-8')
            with self.assertRaises(RuntimeError):FileTransaction(root).stage(path,'new',expected=None)

    def test_interrupted_journal_recovers_and_cancel_rolls_back(self):
        with tempfile.TemporaryDirectory() as root:
            a,b=Path(root)/'a.md',Path(root)/'b.md'
            a.write_text('old',encoding='utf-8')
            txn=FileTransaction(root)
            txn.stage(a,'new');txn.stage(b,'created')
            def crash(path,text):
                if Path(path)==b:raise KeyboardInterrupt()
                return atomic_write(path,text)
            with patch('core.storage.atomic_write',side_effect=crash),self.assertRaises(KeyboardInterrupt):txn.commit()
            self.assertEqual(a.read_text(encoding='utf-8'),'new')
            self.assertTrue(recover_incomplete(root))
            self.assertEqual(a.read_text(encoding='utf-8'),'old')
            self.assertFalse(b.exists())
            calls=0
            def cancel():
                nonlocal calls
                calls+=1
                return calls>=3
            txn=FileTransaction(root,cancel_check=cancel)
            txn.stage(a,'new');txn.stage(b,'created')
            with self.assertRaises(InterruptedError):txn.commit()
            self.assertEqual(a.read_text(encoding='utf-8'),'old')
            self.assertFalse(b.exists())

    def test_preview_refuses_overwrite_after_edit(self):
        with tempfile.TemporaryDirectory() as root:
            config=Config(vault_path=root)
            result=ExtractionResult(True,.9,[MathConcept('定理',content='有效正文')])
            plan=prepare_save(result,config)
            target=Path(root)/'数学笔记/定理.md'
            target.write_text('人工建立了同名笔记',encoding='utf-8')
            with self.assertRaises(RuntimeError):apply_save_plan(plan,config)
            self.assertEqual(target.read_text(encoding='utf-8'),'人工建立了同名笔记')


class LongInputTests(unittest.TestCase):
    def test_long_conversation_preserves_all_parts_and_cross_segment_links(self):
        conv=parse_text('Assistant: '+'导数的定义与极限。'*250+'\n\n'+'泰勒公式依赖导数。'*250,source='测试对话')
        # Separate valid-size paragraphs without splitting the formula/code syntax.
        conv.messages[0].content='\n\n'.join(['导数的定义与极限。'*50]*6+['泰勒公式依赖导数。'*50]*6)
        chunks=list(conversation_chunks(conv,2000))
        for paragraph in conv.messages[0].content.split('\n\n'):
            self.assertTrue(any(paragraph in chunk.text for chunk,_ in chunks))
        class Fake(FakeMathAI):
            def chat(self,system,user,response_format_json=True):
                if user.startswith('{'):return super().chat(system,user,response_format_json)
                title='泰勒公式' if '泰勒公式' in user else '导数'
                return json.dumps(dict(is_math=True,math_score=.9,concepts=[dict(title=title,content='数学定义与适用条件',source_messages=[1])]))
        result=extract_long_conversation(conv,Fake(),2000)
        self.assertEqual({c.title for c in result.concepts},{'导数','泰勒公式'})
        self.assertTrue(any(e['relation']=='依赖' for e in result.connections))
        self.assertTrue(all(c.source_refs==['测试对话#message:1'] for c in result.concepts))

    def test_unsplittable_formula_explicit_error_and_local_integrals_distinct(self):
        with self.assertRaises(ValueError):list(conversation_chunks(parse_text('$$\n'+'x'*3000+'\n$$'),2000))
        result=extract_local(parse_text('Assistant: 定积分的定义是积分在一个区间上的值 $I=1$。\nAssistant: 不定积分的定义是原函数族 $F+C$。'),.1)
        self.assertEqual({c.title for c in result.concepts},{'定积分','不定积分'})


if __name__=='__main__':unittest.main()
