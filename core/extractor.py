"""数学内容识别与提取

两层策略：
1. 本地启发式评分：快速过滤掉非数学对话，避免浪费 AI 配额
2. AI 深度提取：调用 LLM 以知识点为单位合并组织笔记
"""
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from core.logger import get_logger
from core.parser import Conversation

logger = get_logger()


# ============ 数据结构 ============

VALID_KINDS = {"定义", "定理", "推论", "引理", "性质", "方法", "例题", "笔记"}

# kind 优先级：越靠前越具体
_KIND_PRIORITY = ["定理", "定义", "推论", "引理", "性质", "方法", "例题", "笔记"]


@dataclass
class MathConcept:
    """一条数学笔记：同一个知识点的所有角度内容合并在一起"""
    title: str
    kind: str = "笔记"
    category: str = "未分类"
    content: str = ""
    related: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    relations: List[dict] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    link_targets: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    is_math: bool = False
    math_score: float = 0.0
    concepts: List[MathConcept] = field(default_factory=list)
    summary: str = ""
    error: Optional[str] = None
    connections: List[dict] = field(default_factory=list)
    source: str = ""
    warnings: List[str] = field(default_factory=list)
    import_id: str = field(default_factory=lambda: uuid.uuid4().hex)


# ============ 第一层：本地启发式数学评分 ============

_LATEX_PATTERNS = [
    re.compile(r"\$\$.+?\$\$", re.DOTALL),
    re.compile(r"(?<!\$)\$(?!\$).+?(?<!\$)\$(?!\$)", re.DOTALL),
    re.compile(r"\\\[.+?\\\]", re.DOTALL),
    re.compile(r"\\\(.+?\\\)", re.DOTALL),
    re.compile(r"\\begin\{(equation|align|gather|matrix|cases|pmatrix|bmatrix)\}.*?\\end\{\1\}", re.DOTALL),
]

_MATH_KEYWORDS = [
    "定理", "引理", "推论", "证明", "求导", "积分", "极限", "微分", "级数",
    "矩阵", "行列式", "特征值", "特征向量", "向量", "线性无关", "线性相关",
    "概率", "期望", "方差", "分布", "随机变量", "贝叶斯", "条件概率",
    "函数", "连续", "可导", "收敛", "发散", "无穷", "方程", "不等式",
    "集合", "映射", "群", "环", "域", "拓扑", "度量空间",
    "三角函数", "对数", "指数", "多项式", "因式分解", "泰勒", "傅里叶",
    "拉普拉斯", "欧拉", "柯西", "黎曼", "勒贝格", "定义", "性质",
    "theorem", "lemma", "proof", "derivative", "integral", "limit",
    "matrix", "determinant", "eigenvalue", "eigenvector", "vector",
    "probability", "expectation", "variance", "distribution", "bayes",
    "function", "continuous", "differentiable", "converge", "diverge",
    "equation", "inequality", "polynomial", "taylor", "fourier",
    "calculus", "algebra", "geometry", "topology", "trigonometry",
    "definition", "corollary", "proposition",
]

_MATH_SYMBOLS = re.compile(
    r"[∂∇∫∮∑∏√∞±≤≥≠≈∈∉⊂⊆∪∩∀∃→←↔⇒⇔αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ]"
)

_NON_MATH_KEYWORDS = [
    "天气", "新闻", "小说", "电影", "菜谱", "股票", "游戏", "明星",
    "旅游", "美食", "聊天", "心情", "笑话", "翻译", "天气预报",
]

_MATH_TERMS = [
    "泰勒公式", "泰勒定理", "麦克劳林公式", "洛必达法则", "拉格朗日中值定理", "柯西中值定理",
    "特征值", "特征向量", "行列式", "矩阵", "线性无关", "线性相关",
    "极限", "导数", "微分", "积分", "定积分", "不定积分", "级数",
    "收敛", "发散", "连续", "可导", "无穷", "方程", "不等式",
    "概率", "期望", "方差", "分布", "随机变量", "贝叶斯",
    "三角函数", "对数", "指数", "多项式", "因式分解",
    "傅里叶变换", "拉普拉斯变换", "黎曼积分", "勒贝格积分",
]


def quick_math_score(text: str) -> float:
    """快速评估文本的数学相关度 (0~1)"""
    if not text or len(text) < 10:
        return 0.0

    score = 0.0
    n = len(text)

    latex_count = sum(len(p.findall(text)) for p in _LATEX_PATTERNS)
    score += min(latex_count * 0.15, 0.5)

    text_lower = text.lower()
    kw_count = sum(1 for kw in _MATH_KEYWORDS if kw in text_lower)
    score += min(kw_count * 0.04, 0.4)

    sym_count = len(_MATH_SYMBOLS.findall(text))
    score += min(sym_count * 0.02, 0.2)

    neg_count = sum(1 for kw in _NON_MATH_KEYWORDS if kw in text_lower)
    score -= neg_count * 0.1

    if n > 5000 and latex_count == 0 and kw_count < 5:
        score *= 0.5

    return max(0.0, min(1.0, score))


# ============ 合并逻辑：同一知识点多条记录合并为一篇笔记 ============

def _kind_priority(kind: str) -> int:
    """kind 优先级值（越小越具体）"""
    try:
        return _KIND_PRIORITY.index(kind)
    except ValueError:
        return 99


def _normalize_title(title: str) -> str:
    """规范化标题，用于判断是否为同一知识点"""
    # 去除常见前后缀
    t = re.sub(r"^(什么是|如何理解|解释|介绍)", "", title)
    t = re.sub(r"[?？\s]+$", "", t)
    return t.strip()


def _titles_match(t1: str, t2: str) -> bool:
    """判断两个标题是否指向同一知识点"""
    n1 = _normalize_title(t1)
    n2 = _normalize_title(t2)
    return bool(n1 and n2 and n1 == n2)


def _merge_concepts(concepts: List[MathConcept]) -> List[MathConcept]:
    """按标题相似度合并同一知识点的多条记录"""
    merged: List[MathConcept] = []
    for c in concepts:
        found = False
        for base in merged:
            if _titles_match(base.title, c.title):
                # 保留更简短的标题
                if len(c.title) < len(base.title):
                    base.title = c.title
                # 保留更具体的 kind
                if _kind_priority(c.kind) < _kind_priority(base.kind):
                    base.kind = c.kind
                # 合并 content
                if c.content and c.content not in base.content:
                    base.content += "\n\n---\n\n" + c.content
                # 合并标签和关联
                base.related = list(dict.fromkeys(base.related + c.related))
                base.tags = list(dict.fromkeys(base.tags + c.tags))
                base.relations.extend(r for r in c.relations if r not in base.relations)
                base.source_refs = list(dict.fromkeys(base.source_refs + c.source_refs))
                found = True
                break
        if not found:
            merged.append(c)
    return merged


_INVERSE_RELATIONS = {"依赖": "被依赖", "推广": "被推广", "应用": "被应用", "特例": "包含特例", "等价": "等价", "对比": "对比", "相关": "相关", "提及": "被提及"}
_INVERSE_RELATIONS.update({v: k for k, v in list(_INVERSE_RELATIONS.items())})


def connect_concepts(concepts: List[MathConcept], connections=None) -> List[dict]:
    """Preserve explicit relationships without connecting every co-occurring topic."""
    by_title = {_normalize_title(c.title): c for c in concepts}
    edges = []
    seen = set()
    supplied = list(connections or [])
    for c in concepts:
        supplied.extend({"source": c.title, "target": r.get("target", ""), "relation": r.get("relation", "相关"), "reason": r.get("reason", "")} for r in c.relations if isinstance(r, dict))
        supplied.extend({"source": c.title, "target": r, "relation": "相关", "reason": "对话中标记的相关概念"} for r in c.related if not any(x.get("target") == r for x in c.relations))
    for edge in supplied:
        if not isinstance(edge, dict):
            continue
        source = by_title.get(_normalize_title(_safe_str(edge.get("source"))))
        target_name = _safe_str(edge.get("target"))
        target = by_title.get(_normalize_title(target_name))
        if not source or not target_name or (target and target is source):
            continue
        target_name = target.title if target else target_name
        relation = _safe_str(edge.get("relation"), "相关")
        if relation not in _INVERSE_RELATIONS:
            relation = "相关"
        reason = _safe_str(edge.get("reason"))
        key = (source.title, target_name, relation)
        reverse_key = (target_name, source.title, _INVERSE_RELATIONS[relation])
        if key in seen or reverse_key in seen:
            continue
        if relation == "相关" and any({x["source"], x["target"]} == {source.title, target_name} for x in edges):
            continue
        seen.add(key)
        record = {"source": source.title, "target": target_name, "relation": relation, "reason": reason}
        edges.append(record)
    for c in concepts:
        c.relations = []
        # Keep external related targets; canonicalize internal targets below.
        c.related = list(dict.fromkeys(r for r in c.related if _normalize_title(r) not in by_title))
    for edge in edges:
        source = by_title[_normalize_title(edge["source"])]
        target = by_title.get(_normalize_title(edge["target"]))
        source.relations.append({"target": edge["target"], "relation": edge["relation"], "reason": edge["reason"]})
        source.related = list(dict.fromkeys(source.related + [edge["target"]]))
        if target:
            target.relations.append({"target": source.title, "relation": _INVERSE_RELATIONS[edge["relation"]], "reason": edge["reason"]})
            target.related = list(dict.fromkeys(target.related + [source.title]))
    return edges


# ============ 第二层：AI 深度提取 ============

def extract_with_ai(conversation: Conversation, ai_client, max_chars=None, progress=None) -> ExtractionResult:
    limit = max_chars or getattr(getattr(ai_client, 'config', None), 'input_chunk_chars', 16000)
    if len(conversation.text) > limit:
        from core.services import extract_long_conversation
        return extract_long_conversation(conversation, ai_client, limit, progress)
    return _extract_one(conversation, ai_client)


def _extract_one(conversation: Conversation, ai_client) -> ExtractionResult:
    """调用 AI 提取知识点，按 title 合并"""
    from ai.prompts import EXTRACTION_SYSTEM, build_extraction_prompt

    result = ExtractionResult(source=conversation.source)
    response = ""
    try:
        prompt = build_extraction_prompt('\n\n'.join(f'[message:{i}][{m.role}]\n{m.content}' for i,m in enumerate(conversation.messages,1)))
        response = ai_client.chat(
            system=EXTRACTION_SYSTEM,
            user=prompt,
            response_format_json=True,
        )
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)
        if not isinstance(data, dict) or not isinstance(data.get("is_math"), bool):
            raise ValueError("AI 结果必须包含布尔值 is_math。请重试或更换模型。")
        score = data.get("math_score", 0)
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ValueError("AI 返回的数学相关度不在 0–1 范围。")
        if not isinstance(data.get("concepts", []), list):
            raise ValueError("AI concepts 必须是列表。")
        if len(data.get('concepts',[]))>250:
            raise ValueError('单段返回超过 250 个知识点，请缩小每段输入长度后重试。')
        result.is_math = data["is_math"]
        result.math_score = float(score)
        result.summary = _safe_str(data.get("summary"))
        if not result.is_math:
            return result

        raw_concepts: List[MathConcept] = []
        for c in data.get("concepts", []):
            if not isinstance(c, dict) or not isinstance(c.get("title"), str) or not isinstance(c.get("content"), str):
                raise ValueError("AI 返回的知识点字段不完整，请重新分析。")
            if not c["title"].strip() or not c["content"].strip():
                continue
            kind = _safe_str(c.get("kind"), "笔记")
            if kind not in VALID_KINDS:
                kind = "笔记"
            raw_concepts.append(MathConcept(
                title=_safe_str(c.get("title"), "未命名"),
                kind=kind,
                category=_safe_str(c.get("category"), "未分类"),
                content=_safe_str(c.get("content")),
                related=_safe_list(c.get("related")),
                tags=_safe_list(c.get("tags")),
                relations=[r for r in c.get("relations", []) if isinstance(r, dict)] if isinstance(c.get("relations", []), list) else [],
                source_refs=[f"{conversation.source}#message:{i}" for i in c.get('source_messages', []) if isinstance(i,int) and not isinstance(i,bool) and 1 <= i <= len(conversation.messages)] if isinstance(c.get('source_messages',[]),list) else [],
            ))

        # 按 title 合并同一知识点
        result.concepts = _merge_concepts(raw_concepts)
        for concept in result.concepts:
            if not concept.source_refs:
                concept.source_refs = [conversation.source or '粘贴对话']
        result.connections = connect_concepts(result.concepts, data.get("connections") if isinstance(data.get("connections"), list) else [])
        logger.info(f"AI 提取完成: is_math={result.is_math}, "
                    f"score={result.math_score:.2f}, concepts={len(result.concepts)}")
        return result
    except json.JSONDecodeError as e:
        logger.error(f"AI 返回 JSON 解析失败: {e}")
        result.error = f"AI 返回格式错误: {e}"
        return result
    except Exception as e:
        logger.error(f"AI 提取失败: {e}")
        result.error = str(e)
        return result


def extract_local(conversation: Conversation, min_math_score: float = 0.1) -> ExtractionResult:
    """本地兜底提取：按消息分割，按 title 合并"""
    result = ExtractionResult(source=conversation.source)
    messages = conversation.messages

    if not messages:
        result.math_score = quick_math_score(conversation.text)
        result.is_math = result.math_score >= min_math_score
        return result

    max_score = 0.0
    for msg in messages:
        max_score = max(max_score, quick_math_score(msg.content))

    result.math_score = max_score
    result.is_math = max_score >= min_math_score

    if not result.is_math:
        return result

    concepts: List[MathConcept] = []
    current_concept: Optional[MathConcept] = None

    for message_index, msg in enumerate(messages, 1):
        text = msg.content.strip()
        if not text:
            continue

        para_score = quick_math_score(text)
        if para_score < 0.05:
            continue

        lines = text.splitlines()
        title = _extract_title(lines[0]) if lines else "数学片段"

        if current_concept is None or para_score > 0.08:
            if current_concept is not None:
                concepts.append(current_concept)
            current_concept = MathConcept(
                title=title,
                kind=_guess_kind(text),
                category="未分类",
                content=text,
                tags=["本地提取"],
                source_refs=[f'{conversation.source}#message:{message_index}'],
            )
        else:
            if current_concept:
                current_concept.content += "\n\n---\n\n" + text
                current_concept.source_refs.append(f'{conversation.source}#message:{message_index}')

    if current_concept is not None:
        concepts.append(current_concept)

    # 按 title 合并同一知识点
    result.concepts = _merge_concepts(concepts)
    mentions = []
    for c in result.concepts:
        for target in result.concepts:
            if c is not target and target.title in c.content:
                mentions.append({"source": c.title, "target": target.title, "relation": "提及", "reason": "正文明确提及该知识点；具体数学关系待确认"})
    result.connections = connect_concepts(result.concepts, mentions)
    result.summary = f"本地提取到 {len(result.concepts)} 条笔记"
    return result


def _safe_str(val, default: str = "") -> str:
    if val is None:
        return default
    return str(val).strip()


def _safe_list(val) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if x is not None and str(x).strip()]
    if isinstance(val, str):
        return [val.strip()] if val.strip() else []
    return []


def _guess_kind(text: str) -> str:
    """本地模式下粗略猜测笔记类型"""
    head = text[:200]
    if re.search(r"(定理|theorem)", head, re.IGNORECASE):
        return "定理"
    if re.search(r"(定义|definition|是指|称为)", head, re.IGNORECASE):
        return "定义"
    if re.search(r"(推论|corollary)", head, re.IGNORECASE):
        return "推论"
    if re.search(r"(引理|lemma)", head, re.IGNORECASE):
        return "引理"
    if re.search(r"(例|例如|example|求|计算|证明)", head, re.IGNORECASE):
        return "例题"
    return "笔记"


def _extract_title(line: str) -> str:
    """从段落首行提取可能的标题"""
    line = line.strip()
    line = re.sub(r"^[\s#*\-]+", "", line)

    # 模式1: "什么是XX" -> XX
    m = re.search(r"什么是[「『\"']?([^?？\s「』\"']{2,12})[」』\"']?", line)
    if m:
        return m.group(1)

    # 模式2: "XX是什么" -> XX
    m = re.search(r"([\u4e00-\u9fa5]{2,8})是[什么]*[?？]", line)
    if m:
        return m.group(1)

    # 模式3: "如何计算XX" / "怎么求XX" -> XX
    m = re.search(r"(?:如何|怎么|怎样|怎么求|如何求|怎样求|怎么计算|如何计算)([\u4e00-\u9fa5]{2,8})", line)
    if m:
        return m.group(1)

    # 模式4: 包含问号，提取最后的核心名词短语
    if "?" in line or "？" in line:
        line_clean = re.sub(r"(是|的|为|在|对|和|与|及)?[\u4e00-\u9fa5]{0,4}[?？]$", "", line).strip()
        keywords = re.findall(r"[\u4e00-\u9fa5]{2,8}", line_clean)
        if keywords:
            return keywords[-1]

    # 模式5: 提取第一个数学术语
    for term in sorted(_MATH_TERMS,key=len,reverse=True):
        if term in line:
            return term

    # 模式6: "XXX是..."定义句式，提取主语
    m = re.search(r"^([\u4e00-\u9fa5]{2,6})(?:[A-Z\u4e00-\u9fa5]{0,3}(?:是|为|定义|表示|指|概念|方法|定理|公式))", line)
    if m:
        return m.group(1)

    if len(line) > 20:
        line = line[:20] + "..."
    return line if line else "数学片段"
