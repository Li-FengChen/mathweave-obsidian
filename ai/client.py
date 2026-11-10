"""AI 客户端：兼容 OpenAI 接口规范的服务（OpenAI/DeepSeek/Moonshot/智谱/Ollama）"""
import time
import random
from typing import Optional, Tuple

from core.config import Config, get_api_key
from core.logger import get_logger

logger = get_logger()


class AIClient:
    """统一封装 OpenAI 兼容接口，支持自动重试"""

    def __init__(self, config: Config, cancel_check=None):
        self.config = config
        self.cancel_check = cancel_check or (lambda: False)
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("请安装 openai 库: pip install openai")

        api_key = get_api_key(self.config.ai_provider)
        if not api_key and self.config.ai_provider != "ollama":
            raise RuntimeError(
                f"未找到 {self.config.ai_provider} 的 API 密钥，"
                f"请在设置中配置"
            )

        if self.config.ai_provider == "ollama" and not api_key:
            api_key = "ollama"

        self._client = OpenAI(
            api_key=api_key,
            base_url=self.config.api_base,
            timeout=60.0,
            max_retries=0,
        )
        logger.info(f"AI 客户端已初始化: provider={self.config.ai_provider}, "
                    f"model={self.config.model}")

    def chat(self, system: str, user: str, response_format_json: bool = False) -> str:
        """发送对话请求，自动重试 3 次"""
        if not self._client:
            raise RuntimeError("AI 客户端未初始化")

        kwargs = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if response_format_json and self.config.ai_json_mode != 'off':
            kwargs["response_format"] = {"type": "json_object"}
        failures = 0
        for request in range(6):
            if self.cancel_check():
                raise RuntimeError("分析已取消")
            try:
                resp = self._client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content
                if resp.choices[0].finish_reason == "length":
                    raise ValueError("生成内容被截断。请提高最大输出长度，或分几次导入较短的对话。")
                if not content:
                    raise ValueError("AI 返回空内容")
                logger.debug(f"AI 响应长度: {len(content)}")
                return content
            except Exception as e:
                if self.cancel_check():
                    raise RuntimeError("分析已取消") from e
                if isinstance(e, ValueError):
                    raise
                status = getattr(e, 'status_code', None)
                body = getattr(e, 'body', {})
                body = body.get('error', body) if isinstance(body, dict) else {}
                param = body.get('param','') if isinstance(body,dict) else ''
                message = str(body.get('message','')).lower() if isinstance(body,dict) else ''
                unsupported = any(x in message for x in ('unsupported','not supported','not support','unknown parameter','unrecognized','不支持'))
                if status == 400 and unsupported:
                    if (param == 'response_format' or 'response_format' in message) and 'response_format' in kwargs and self.config.ai_json_mode == 'auto':
                        kwargs.pop('response_format')
                        logger.info('服务不支持 JSON 输出参数，改用提示词约束并严格解析 JSON。')
                        continue
                    if (param == 'max_tokens' or 'max_tokens' in message) and 'max_tokens' in kwargs:
                        kwargs['max_completion_tokens'] = kwargs.pop('max_tokens')
                        continue
                    if (param == 'temperature' or 'temperature' in message) and 'temperature' in kwargs:
                        kwargs.pop('temperature')
                        continue
                transient = status in (408,409,429) or (isinstance(status,int) and status >= 500) or type(e).__name__ in ('APIConnectionError','APITimeoutError')
                failures += 1
                logger.warning('AI 请求失败：类型=%s，状态=%s，次数=%s',type(e).__name__,status,failures)
                if not transient or failures >= 3:
                    details = {400:'请求参数不受支持，可调整 JSON 输出模式、模型或输出长度。',401:'请检查 API 密钥。',403:'服务拒绝访问，请检查账户权限。',404:'请检查服务地址与模型名称。',429:'请求过多或额度不足，请稍后重试并检查服务额度。'}
                    raise RuntimeError(f'AI 请求失败（{status or type(e).__name__}）。'+details.get(status,'请检查网络和服务状态后重试。')) from None
                wait = min(2 ** failures + random.random(), 10)
                response = getattr(e,'response',None)
                retry_after = getattr(response,'headers',{}).get('retry-after') if response is not None else None
                try:
                    if retry_after is not None: wait = min(max(float(retry_after),0),20)
                except (ValueError,TypeError): pass
                until = time.monotonic()+wait
                while time.monotonic() < until:
                    if self.cancel_check(): raise RuntimeError('分析已取消')
                    time.sleep(min(.1, max(0,until-time.monotonic())))
        raise RuntimeError('服务参数兼容尝试已达上限，请检查模型与 JSON 输出模式。')

    def test_connection(self) -> Tuple[bool, str]:
        """测试连接是否可用"""
        try:
            resp = self.chat(
                system="You are a helpful assistant.",
                user="Hi, respond with just 'ok'.",
            )
            return True, f"连接成功: {resp[:50]}"
        except Exception as e:
            return False, f"连接失败: {e}"
