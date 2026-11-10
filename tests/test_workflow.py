import copy
import json
import tempfile
import unittest
from pathlib import Path
from core.config import Config
from core.demo import demo_result
from core.extractor import MathConcept, _merge_concepts, extract_with_ai
from core.obsidian import VaultManager, save_extraction, split_frontmatter, compose_note, sanitize_filename
from core.parser import parse_text


class WorkflowTests(unittest.TestCase):
    def test_roles_survive_roundtrip(self):
        conv = parse_text('User: 什么是矩阵？\nAssistant: 矩阵是按行列排列的数组。')
        self.assertEqual([(x.role, x.content) for x in conv.messages], [(x.role, x.content) for x in parse_text(conv.text).messages])

    def test_distinct_concepts_stay_distinct(self):
        self.assertEqual(len(_merge_concepts([MathConcept('积分'), MathConcept('定积分'), MathConcept('不定积分')])), 3)

    def test_branch_and_null_time(self):
        def node(role, text, parent, timestamp):
            return dict(parent=parent, message=dict(author=dict(role=role), content=dict(parts=[text]), create_time=timestamp))
        data = dict(mapping={'u': node('user', '定义', None, None), 'old': node('assistant', '旧', 'u', 1), 'new': node('assistant', '新', 'u', None)}, current_node='new')
        self.assertEqual([x.content for x in parse_text(json.dumps([data])).messages], ['定义', '新'])
        data.pop('current_node')
        with self.assertRaises(ValueError):parse_text(json.dumps(data))

    def test_invalid_ai_types_rejected(self):
        class Fake:
            def chat(self, **kwargs):
                return json.dumps(dict(is_math='false', math_score=9, concepts=[]))
        self.assertTrue(extract_with_ai(parse_text('测试内容'), Fake()).error)

    def test_relationships_are_bidirectional_without_blanket_edges(self):
        result = demo_result()
        taylor = next(x for x in result.concepts if x.title == '泰勒公式')
        derivative = next(x for x in result.concepts if x.title == '导数')
        matrix = next(x for x in result.concepts if x.title == '矩阵与行列式')
        self.assertIn('导数', taylor.related)
        self.assertIn('泰勒公式', derivative.related)
        self.assertEqual(matrix.related, [])
        self.assertTrue(any(x['relation'] == '被依赖' for x in derivative.relations))

    def test_save_links_maps_dedup_and_index(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(vault_path=directory)
            result = demo_result()
            counts, notes, map_title = save_extraction(result, config)
            self.assertEqual(counts['created'], 4)
            vm = VaultManager(directory)
            taylor = vm.note_path('泰勒公式').read_text(encoding='utf-8')
            self.assertIn('[[导数]]', taylor)
            self.assertIn('[[麦克劳林公式]]', taylor)
            self.assertIn(f'[[{map_title}]]', taylor)
            self.assertIn('展开系数', taylor)
            before = {p.name: p.stat().st_mtime_ns for p in Path(notes).glob('*.md')}
            counts, _, _ = save_extraction(result, config)
            self.assertEqual(counts['skipped'], 4)
            self.assertEqual(before, {p.name: p.stat().st_mtime_ns for p in Path(notes).glob('*.md')})
            index = vm.index_path.read_text(encoding='utf-8')
            self.assertNotIn('[[数学知识索引]]', index)
            self.assertNotIn(map_title, index)

    def test_old_content_and_formula_structure_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            vm = VaultManager(directory)
            old = compose_note(dict(title='概念', created='2020-01-01', tags=['人工']), '# 概念\n\n人工备注\n\n$$x^2$$')
            new = compose_note(dict(title='概念', created='2026-01-01', tags=['新标签']), '# 概念\n\n新增内容\n\n---\n\n$$\n\\begin{aligned}a&=b\\\\c&=d\\end{aligned}\n$$')
            vm.save_note('概念', old, 'old')
            vm.save_note('概念', new, 'new')
            saved = vm.note_path('概念').read_text(encoding='utf-8')
            props, body = split_frontmatter(saved)
            self.assertIn('人工备注', body)
            self.assertIn('新增内容', body)
            self.assertIn('\\begin{aligned}a&=b\\\\c&=d\\end{aligned}', body)
            self.assertEqual(props['created'], '2020-01-01')
            self.assertEqual(props['tags'], ['人工', '新标签'])
            self.assertEqual(len(list(vm.backup_dir.glob('*.md'))), 1)

    def test_backup_setting_and_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            vm = VaultManager(directory, backup_before_update=False)
            self.assertNotEqual(vm.note_path('A/B'), vm.note_path('A:B'))
            self.assertNotEqual(sanitize_filename('CON'), 'CON')
            vm.save_note('概念', '旧', '1')
            vm.save_note('概念', '新', '2')
            self.assertFalse(vm.backup_dir.exists())
            with self.assertRaises(ValueError):
                VaultManager(directory, '../not-in-vault')

    def test_yaml_and_title_links(self):
        with tempfile.TemporaryDirectory() as directory:
            result = demo_result()
            result.concepts[0].title = 'A/B'
            result.concepts[0].tags = ['含"引号', 'a\\b']
            for c in result.concepts:
                c.related = ['A/B' if x == '导数' else x for x in c.related]
                for relation in c.relations:
                    if relation['target'] == '导数':
                        relation['target'] = 'A/B'
            for edge in result.connections:
                for field in ('source', 'target'):
                    if edge[field] == '导数':
                        edge[field] = 'A/B'
            save_extraction(result, Config(vault_path=directory))
            vm = VaultManager(directory)
            props, _ = split_frontmatter(vm.note_path('A/B').read_text(encoding='utf-8'))
            self.assertIn('含"引号', props['tags'])
            target = vm.note_path('A/B').stem
            self.assertIn(f'[[{target}|A/B]]', vm.note_path('泰勒公式').read_text(encoding='utf-8'))

    def test_mixed_roles_code_and_preamble_survive(self):
        text='导出说明\n\n[user]\n问题\nAssistant: 解释\n```text\nUser: 代码示例\n```\n用户: 后续问题'
        result=parse_text(text)
        self.assertEqual([m.role for m in result.messages],['system','user','assistant','user'])
        self.assertIn('User: 代码示例',result.messages[2].content)

    def test_broken_json_parts_explicitly_rejected(self):
        with self.assertRaises(ValueError):parse_text(json.dumps(dict(mapping={'a':dict(message=dict(author=dict(role='assistant'),content=dict(parts='not a list')))})))

    def test_symbol_case_collision_and_custom_index(self):
        from core.extractor import ExtractionResult
        self.assertEqual(len(_merge_concepts([MathConcept('A'),MathConcept('a')])),2)
        with tempfile.TemporaryDirectory() as directory:
            config=Config(vault_path=directory,index_note_name='我的索引',math_note_style=False)
            result=ExtractionResult(True,.9,[MathConcept('A',content='大写变量'),MathConcept('a',content='小写变量'),MathConcept('我的索引',content='同名数学概念')])
            save_extraction(result,config)
            vm=VaultManager(directory,index_note_name='我的索引')
            self.assertNotEqual(str(vm.note_path('A')).casefold(),str(vm.note_path('a')).casefold())
            self.assertNotEqual(vm.note_path('我的索引'),vm.index_path)
            self.assertEqual(len(list(vm.notes_dir.glob('*.md'))),5)

    def test_threshold_is_shared_and_invalid_boolean_config_rejected(self):
        from core.services import analyze_conversation
        from core.extractor import extract_local
        config=Config(min_math_score=1,use_ai_extraction=False)
        conv=parse_text('矩阵是线性代数里的数组，按照行列排列。')
        self.assertFalse(analyze_conversation(conv,config).is_math)
        with self.assertRaises(ValueError):Config(use_ai_extraction='false').validate()


if __name__ == '__main__':
    unittest.main()
