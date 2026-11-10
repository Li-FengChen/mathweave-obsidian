"""Small transparent quality fixtures; --live sends only these public examples."""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.config import Config
from core.parser import parse_text
from core.services import analyze_conversation
from core.maintenance import build_maintenance_plan,apply_maintenance_plan
from core.obsidian import compose_note,split_frontmatter
from ai.client import AIClient


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',help='使用已配置 AI 服务，仅发送公开测试样例')
    parser.add_argument('--output',default=str(ROOT/'.qa'/'math-quality-report.json'))
    parser.add_argument('--case',help='只复查指定样例 id')
    args=parser.parse_args()
    fixtures=json.loads((ROOT/'tests/fixtures/math_quality.json').read_text(encoding='utf-8'))
    if args.case:fixtures=[f for f in fixtures if f['id']==args.case]
    if not args.live:
        print(f'已准备 {len(fixtures)} 个公开数学样例。添加 --live 才连接 AI 服务。')
        return
    config=Config.load()
    config.use_ai_extraction=True
    config.max_tokens=max(4096,min(config.max_tokens,8192))
    client=AIClient(config)
    cases=[]
    for fixture in fixtures:
        print('核对样例：'+fixture['id'],flush=True)
        result=analyze_conversation(parse_text(fixture['text'],'质量样例:'+fixture['id']),config,ai_client=client)
        matches=[]
        for aliases in fixture['concepts']:
            matches.append([c for c in result.concepts if any(c.title.startswith(a) or a in c.title for a in aliases)])
        # A containing title must not count as two independently preserved concepts.
        if fixture['id']=='distinct_integrals':
            matches[0]=[c for c in matches[0] if '不定积分' not in c.title]
        checks={'classification':result.is_math==fixture['is_math'], 'concepts':all(matches) if matches else not result.concepts}
        for a,b in fixture.get('separate',[]):
            checks['separate']=bool(matches[a] and matches[b] and not {id(c) for c in matches[a]}&{id(c) for c in matches[b]})
        for a,b,relation in fixture.get('edges',[]):
            source={c.title for c in matches[a]};target={c.title for c in matches[b]}
            checks['edge:'+relation]=any(e['source'] in source and e['target'] in target and e['relation']==relation for e in result.connections)
        body='\n'.join(c.content for c in result.concepts)
        for word in fixture.get('must_include',[]):
            checks['contains:'+word]=word in body or (word=='非零' and bool(re.search(r'\\(?:ne|neq)\s*0|≠\s*0',body)))
        cases.append(dict(id=fixture['id'],passed=all(checks.values()),checks=checks,titles=[c.title for c in result.concepts],contents=[c.content for c in result.concepts],connections=result.connections,source_refs=[c.source_refs for c in result.concepts]))
    # Full-text merge + link maintenance on an isolated vault.
    with tempfile.TemporaryDirectory() as root:
        folder=Path(root)/'数学笔记'
        folder.mkdir()
        examples=[('导数','## 定义\n\n函数 f 在 a 点的导数是差商极限存在时的值。微商是导数的别称。\n\n$$f\'(a)=\\lim_{h\\to0}\\frac{f(a+h)-f(a)}{h}$$\n\n人工备注：需要双侧极限存在。'),('微商','## 定义\n\n微商就是导数：函数 f 在 a 点差商的双侧极限存在时，称此值为该点微商。\n\n人工备注：端点的单侧导数应另行说明。'),('泰勒公式','## 定理\n\n泰勒公式的系数由展开点各阶导数决定，所以依赖导数概念。需保留适用的可微条件和余项。'),('定积分','## 定义\n\n定积分求区间上的累积量，是一个数。'),('不定积分','## 定义\n\n不定积分是原函数族 F+C。不要与定积分合并。')]
        for title,body in examples:
            (folder/(title+'.md')).write_text(compose_note(dict(title=title,kind='定义',category='微积分',tags=['数学']), '# '+title+'\n\n'+body),encoding='utf-8')
        config.vault_path=root
        if not args.case or args.case=='live_maintenance':print('核对真实 AI 笔记库整理…',flush=True)
        plan=build_maintenance_plan(config,client,progress=print) if not args.case or args.case=='live_maintenance' else None
        if plan is None:
            report=dict(model=config.model,provider=config.ai_provider,fixture_count=len(cases),passed=sum(c['passed'] for c in cases),cases=cases,limitations='小样本人工检查参考；不代表任意笔记库准确率。')
            Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report,ensure_ascii=False),flush=True)
            return 0 if all(c['passed'] for c in cases) else 1
        summary=apply_maintenance_plan(plan,config)
        texts={p.stem:p.read_text(encoding='utf-8') for p in folder.glob('*.md')}
        canonical=next((texts[Path(g['canonical']).stem] for g in plan.groups if set(Path(p).stem for p in g['members'])=={'导数','微商'}),'')
        checks=dict(duplicate_merged=bool(canonical),originals_retained='需要双侧极限存在' in canonical and '端点的单侧导数应另行说明' in canonical,integrals_separate=all(split_frontmatter(texts[t])[0].get('kind')!='重定向' for t in ('定积分','不定积分')),reciprocal_links=bool(plan.links),backup=bool(plan.backup_path))
        cases.append(dict(id='live_maintenance',passed=all(checks.values()),checks=checks,summary={k:v for k,v in summary.items() if k!='backup'},groups=plan.groups,links=plan.links))
    report=dict(model=config.model,provider=config.ai_provider,fixture_count=len(cases),passed=sum(c['passed'] for c in cases),cases=cases,limitations='仅为小规模公开样例与文本规则核对；不代表数学证明正确率或任意笔记库的合并准确率。')
    path=Path(args.output).resolve()
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],total=len(cases),report=str(path)),ensure_ascii=False),flush=True)
    return 0 if report['passed']==len(cases) else 1

if __name__=='__main__':sys.exit(main() or 0)
