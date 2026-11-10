"""Native Obsidian mathematical callouts; preserve content, never invent proofs."""
import re

_HEADINGS = {
    '定义': ('abstract', '定义', ''), '定义与记号': ('abstract', '定义与记号', ''),
    '定理': ('note', '定理', ''), '命题': ('note', '命题', ''), '引理': ('note', '引理', ''),
    '推论': ('note', '推论', ''), '性质': ('note', '性质', ''),
    '证明': ('tip', '证明', '-'), '证明思路': ('tip', '证明思路', '-'),
    'proof': ('tip', '证明', '-'), 'proof sketch': ('tip', '证明思路', '-'),
    '例题': ('example', '例题', '+'), '示例': ('example', '示例', '+'), '例子': ('example', '例子', '+'),
    'examples': ('example', '例题', '+'), 'example': ('example', '例题', '+'),
    '适用条件': ('warning', '适用条件', ''), '条件与限制': ('warning', '条件与限制', ''),
    '注意事项': ('warning', '注意事项', ''), '直观解释': ('info', '直观解释', '+'),
    'definition': ('abstract', '定义', ''), 'theorem': ('note', '定理', ''),
}


def callout(kind, title, content, fold=''):
    lines = [f'> [!{kind}]{fold} {title}']
    lines.extend('> ' + line if line else '>' for line in content.strip().splitlines())
    return '\n'.join(lines)


def format_math_content(content, kind='笔记'):
    content = content.strip()
    if not content:
        return ''
    header = ''
    first_title = re.match(r'\A(# [^\n]+)\n+(.*)\Z', content, re.S)
    if first_title:
        header = first_title.group(1) + '\n\n'
        content = first_title.group(2)
    sections, current, heading = [], [], None
    fenced = None
    has_callout = bool(re.search(r'^>\s*\[!\w+\]', content, re.M))
    def flush():
        if current or heading:
            sections.append((heading, '\n'.join(current).strip()))
        current.clear()
    for line in content.splitlines():
        fence = re.match(r'^\s*(`{3,}|~{3,})', line)
        if fence:
            if fenced is None:
                fenced = fence.group(1)[0]
            elif fence.group(1)[0] == fenced:
                fenced = None
        matched = re.match(r'^(#{2,4})\s+(.+?)\s*#*$', line) if fenced is None else None
        if matched:
            flush()
            heading = (matched.group(1),matched.group(2).strip())
        else:
            current.append(line)
    flush()
    rendered = []
    boxed = has_callout
    for heading, body in sections:
        spec = _HEADINGS.get(heading[1].casefold()) if heading else None
        if heading and spec is None:
            prefix=re.match(r'^(定义|定理|命题|引理|推论|性质|证明|例题|适用条件)(?:[\s：:（(]|\d)',heading[1])
            if prefix:
                base=_HEADINGS.get(prefix.group(1))
                if base:spec=(base[0],heading[1],base[2])
        if spec and body and not re.match(r'^>\s*\[!\w+\]', body):
            rendered.append(callout(*spec[:2], body, fold=spec[2]))
            boxed = True
        elif heading:
            rendered.append(f'{heading[0]} {heading[1]}\n\n{body}')
        elif body:
            rendered.append(body)
    formatted = '\n\n'.join(rendered)
    # With no semantic section headings, keep the original as one statement box.
    if not boxed and kind in ('定义', '定理', '引理', '推论', '性质'):
        formatted = callout('abstract' if kind == '定义' else 'note', kind, formatted)
    return header + formatted
