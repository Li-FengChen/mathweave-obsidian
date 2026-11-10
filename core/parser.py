"""对话内容解析：从多种格式提取 user/assistant 消息对"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from core.logger import get_logger

logger = get_logger()


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str


@dataclass
class Conversation:
    messages: List[Message] = field(default_factory=list)
    source: str = ""  # 来源描述

    @property
    def text(self) -> str:
        return "\n\n".join(f"[{m.role}]\n{m.content}" for m in self.messages)


# ============ 各平台对话导出格式识别 ============

def parse_text(text: str, source: str = "paste") -> Conversation:
    """尝试自动识别格式，失败则按纯文本处理"""
    if not text.strip():
        return Conversation(source=source)

    # 1. 尝试 JSON（ChatGPT 导出 / API 格式）
    conv = _try_parse_json(text, source)
    if conv and conv.messages:
        return conv

    # 2. 尝试 Markdown 格式（带 User:/Assistant: 或 用户:/AI: 等标记）
    conv = _try_parse_marked(text, source)
    if conv and conv.messages:
        return conv

    # 3. 兜底：整段作为单条 assistant 消息
    return Conversation(
        messages=[Message(role="assistant", content=text.strip())],
        source=source,
    )


def parse_file(file_path: str) -> Conversation:
    """支持 .txt / .md / .json"""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    raw = p.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "utf-16" if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else "utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeError:
            continue
    if text is None:
        raise ValueError("无法识别文本编码，请另存为 UTF-8 后再导入。")
    return parse_text(text, source=str(p))


def _try_parse_json(text: str, source: str) -> Optional[Conversation]:
    """解析 ChatGPT 导出的 JSON 或 OpenAI messages 数组"""
    text = text.strip()
    if not (text.startswith("{") or text.startswith("[")):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    messages: List[Message] = []

    # 形式 A: [{"role": "user", "content": "..."}, ...]
    if isinstance(data, list) and data and isinstance(data[0], dict):
        if "mapping" in data[0]:
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    parsed = _try_parse_json(json.dumps(item, ensure_ascii=False), source)
                    if parsed:
                        messages.extend(parsed.messages)
            return Conversation(messages=messages, source=source)
        if "role" in data[0] and "content" in data[0]:
            for item in data:
                if not isinstance(item, dict):
                    continue
                role = item.get("role", "user")
                content = item.get("content", "")
                if isinstance(content, list):  # 多模态
                    content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                if content:
                    messages.append(Message(role=role, content=str(content)))
            return Conversation(messages=messages, source=source)

    # 形式 B: ChatGPT 导出 {"mapping": {...}}
    if isinstance(data, dict) and "mapping" in data:
        nodes = data["mapping"]
        if not isinstance(nodes, dict):
            raise ValueError("对话 mapping 必须是对象。")
        selected = data.get("current_node")
        if selected is not None and (not isinstance(selected,str) or selected not in nodes):
            raise ValueError('current_node 没有指向有效分支节点，请重新导出对话。')
        if selected is None:
            children={}
            for node in nodes.values():
                parent=node.get('parent') if isinstance(node,dict) else None
                if isinstance(parent,str) and parent in nodes:children[parent]=children.get(parent,0)+1
            if any(count>1 for count in children.values()):
                raise ValueError('该对话存在多个答案分支，但没有 current_node。请导出选定分支，避免把旧答案与新答案混合。')
        ordered_ids = []
        seen = set()
        while selected in nodes and selected not in seen:
            seen.add(selected)
            ordered_ids.append(selected)
            node = nodes[selected]
            selected = node.get("parent") if isinstance(node, dict) else None
            if selected is not None and (not isinstance(selected,str) or selected not in nodes):
                raise ValueError('导出分支的父节点缺失或格式错误，请重新导出。')
        ordered_ids.reverse()
        branch_nodes = [(nid, nodes[nid]) for nid in ordered_ids] if ordered_ids else list(nodes.items())
        items = []
        for nid, node in branch_nodes:
            if not isinstance(node, dict):
                continue
            msg = node.get("message")
            if not isinstance(msg, dict):
                continue
            author_obj = msg.get("author") or {}
            author = author_obj.get("role", "") if isinstance(author_obj, dict) else ""
            content_obj = msg.get("content", {})
            if not isinstance(content_obj, dict):
                continue
            parts = content_obj.get("parts", [])
            if not isinstance(parts,list):
                raise ValueError('对话消息的 parts 必须是列表；请重新导出 JSON。')
            text_part = "\n".join(p for p in parts if isinstance(p, str))
            if text_part and author in ("user", "assistant", "system"):
                timestamp = msg.get("create_time")
                items.append((timestamp if isinstance(timestamp, (int, float)) else 0, Message(role=author, content=text_part)))
        if not ordered_ids:
            items.sort(key=lambda x: x[0])
        messages = [m for _, m in items]
        return Conversation(messages=messages, source=source)

    # 形式 C: {"messages": [...]}
    if isinstance(data, dict) and "messages" in data:
        if not isinstance(data['messages'],list):raise ValueError('JSON messages 字段必须是消息列表。')
        return _try_parse_json(json.dumps(data["messages"]), source)

    return None


# 匹配中文/英文常见角色标记
_ROLE_PATTERN = re.compile(
    r"^(?:#{1,6}\s*)?(?:\*\*)?"
    r"(User|Assistant|System|ChatGPT|GPT|AI|Claude|用户|提问者|问|答|助手|系统|人类)"
    r"(?:\*\*)?\s*[:：]\s*",
    re.IGNORECASE | re.MULTILINE,
)

_BRACKET_ROLE_PATTERN = re.compile(r"^\[(user|assistant|system)\]\s*\n", re.IGNORECASE | re.MULTILINE)

_ROLE_MAP = {
    "user": "user", "提问者": "user", "用户": "user", "问": "user", "人类": "user",
    "assistant": "assistant", "chatgpt": "assistant", "gpt": "assistant", "ai": "assistant",
    "claude": "assistant", "答": "assistant", "助手": "assistant",
    "system": "system", "系统": "system",
}


def _try_parse_marked(text: str, source: str) -> Optional[Conversation]:
    """解析带角色标记的文本"""
    fenced_ranges=[]
    open_fence=None
    offset=0
    start=0
    for line in text.splitlines(keepends=True):
        marker=re.match(r'^\s*(`{3,}|~{3,})',line)
        if marker:
            char=marker.group(1)[0]
            if open_fence is None:open_fence=char;start=offset
            elif open_fence==char:
                fenced_ranges.append((start,offset+len(line)));open_fence=None
        offset+=len(line)
    if open_fence:fenced_ranges.append((start,len(text)))
    matches = sorted(list(_ROLE_PATTERN.finditer(text))+list(_BRACKET_ROLE_PATTERN.finditer(text)),key=lambda m:m.start())
    matches=[m for m in matches if not any(a<=m.start()<b for a,b in fenced_ranges)]
    if not matches:
        return None

    messages: List[Message] = []
    if text[:matches[0].start()].strip():
        messages.append(Message('system',text[:matches[0].start()].strip()))
    for i, m in enumerate(matches):
        role_raw = m.group(1).lower()
        role = _ROLE_MAP.get(role_raw, "user")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            messages.append(Message(role=role, content=content))
    return Conversation(messages=messages, source=source) if messages else None
