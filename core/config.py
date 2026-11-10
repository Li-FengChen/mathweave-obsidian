"""配置管理：用户配置 + API密钥安全存储

密钥通过 keyring 库存入操作系统密钥链（Windows Credential Manager /
macOS Keychain / Linux Secret Service），不落盘明文。
"""
import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

from core.logger import get_logger

logger = get_logger()

APP_NAME = "MathObsidianAgent"
CONFIG_DIR = Path(os.environ.get("MATH_OBSIDIAN_HOME", str(Path.home() / ".math_obsidian_agent")))
CONFIG_FILE = CONFIG_DIR / "config.json"
KEYRING_SERVICE = "math_obsidian_agent"


@dataclass
class Config:
    # Obsidian 仓库
    vault_path: str = ""
    notes_subfolder: str = "数学笔记"
    index_note_name: str = "数学知识索引"

    # AI 服务
    ai_provider: str = "openai"  # openai | deepseek | moonshot | custom | ollama
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.2

    # 处理选项
    use_ai_extraction: bool = True
    min_math_score: float = 0.3  # 低于此分数视为非数学内容
    auto_link_notes: bool = True
    backup_before_update: bool = True
    input_chunk_chars: int = 16000
    ai_json_mode: str = "auto"
    math_note_style: bool = True
    link_existing_on_save: bool = True
    maintenance_scope: str = "math"
    maintenance_min_confidence: float = 0.94
    maintenance_max_notes: int = 1000

    def save(self):
        self.validate()
        from core.storage import atomic_write
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        atomic_write(CONFIG_FILE, json.dumps(asdict(self), ensure_ascii=False, indent=2))
        logger.info(f"配置已保存到 {CONFIG_FILE}")

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                config = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
                config.validate()
                return config
            except Exception as e:
                logger.error(f"加载配置失败: {e}，使用默认配置")
        return cls()

    def validate(self):
        import math
        if any(not isinstance(getattr(self,name),str) for name in ('ai_provider','api_base','model')):
            raise ValueError('AI 服务商、地址与模型名称必须是文本。')
        if not isinstance(self.vault_path, str) or not isinstance(self.notes_subfolder, str):
            raise ValueError('仓库路径与笔记子目录必须是文本。')
        if not isinstance(self.index_note_name, str) or not self.index_note_name.strip():
            raise ValueError('索引名称不能为空。')
        if isinstance(self.min_math_score, bool) or not isinstance(self.min_math_score, (int, float)) or not math.isfinite(self.min_math_score) or not 0 <= self.min_math_score <= 1:
            raise ValueError('数学相关度阈值必须在 0–1 之间。')
        if not isinstance(self.input_chunk_chars, int) or not 2000 <= self.input_chunk_chars <= 60000:
            raise ValueError('每段输入长度必须在 2000–60000 字符之间。')
        if not isinstance(self.max_tokens, int) or not 512 <= self.max_tokens <= 65536:
            raise ValueError('最大输出长度必须在 512–65536 之间。')
        if isinstance(self.temperature,bool) or not isinstance(self.temperature, (int, float)) or not 0 <= self.temperature <= 2:
            raise ValueError('生成温度必须在 0–2 之间。')
        if self.ai_json_mode not in ('auto', 'force', 'off') or self.maintenance_scope not in ('math', 'vault'):
            raise ValueError('不支持的 AI 输出模式或整理范围。')
        if not isinstance(self.maintenance_min_confidence,(int,float)) or isinstance(self.maintenance_min_confidence,bool) or not 0.5 <= self.maintenance_min_confidence <= 1 or type(self.maintenance_max_notes) is not int or not 1 <= self.maintenance_max_notes <= 10000:
            raise ValueError('整理置信度或笔记数量设置不合法。')
        for name in ('use_ai_extraction','auto_link_notes','backup_before_update','math_note_style','link_existing_on_save'):
            if not isinstance(getattr(self,name), bool):
                raise ValueError(f'配置 {name} 必须是布尔值。')


# ============ API 密钥安全存储 ============

def set_api_key(api_key: str, provider: str = "openai") -> bool:
    """将API密钥存入系统密钥链"""
    if not KEYRING_AVAILABLE:
        logger.warning("keyring库不可用，密钥未保存；可通过环境变量提供密钥")
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, f"{provider}_api_key", api_key)
        logger.info(f"API密钥已存入系统密钥链 (provider={provider})")
        return True
    except Exception as e:
        logger.error("密钥存储失败 (%s)", type(e).__name__)
        return False


@dataclass(frozen=True)
class ApiKeyInfo:
    value: Optional[str] = field(default=None, repr=False)
    source: str = "none"
    has_environment_key: bool = False
    read_failed: bool = False


def get_api_key_info(provider: str = "openai") -> ApiKeyInfo:
    """Read the effective key and its source without exposing it in diagnostics."""
    environment_key = os.environ.get(f"{provider.upper()}_API_KEY")
    read_failed = False
    if KEYRING_AVAILABLE:
        try:
            key = keyring.get_password(KEYRING_SERVICE, f"{provider}_api_key")
            if key:
                return ApiKeyInfo(key, "keyring", bool(environment_key))
        except Exception as err:
            logger.error("密钥读取失败 (%s)", type(err).__name__)
            read_failed = True
    return ApiKeyInfo(environment_key, "environment" if environment_key else "none",
                      bool(environment_key), read_failed)


def get_api_key(provider: str = "openai") -> Optional[str]:
    """从系统密钥链读取 API 密钥，兼容环境变量。"""
    return get_api_key_info(provider).value


def delete_api_key(provider: str = "openai") -> bool:
    if not KEYRING_AVAILABLE:
        return False
    try:
        if keyring.get_password(KEYRING_SERVICE, f"{provider}_api_key") is None:
            return True
        keyring.delete_password(KEYRING_SERVICE, f"{provider}_api_key")
        logger.info("API密钥已从系统密钥链删除 (provider=%s)", provider)
        return True
    except Exception as err:
        logger.error("密钥删除失败 (%s)", type(err).__name__)
        return False


# 各服务商默认 API base
PROVIDER_PRESETS = {
    "openai":    {"api_base": "https://api.openai.com/v1",         "model": "gpt-4o-mini"},
    "deepseek":  {"api_base": "https://api.deepseek.com/v1",       "model": "deepseek-chat"},
    "moonshot":  {"api_base": "https://api.moonshot.cn/v1",        "model": "moonshot-v1-8k"},
    "zhipu":     {"api_base": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "ollama":    {"api_base": "http://localhost:11434/v1",         "model": "qwen2.5:7b"},
    "custom":    {"api_base": "",                                   "model": ""},
}
