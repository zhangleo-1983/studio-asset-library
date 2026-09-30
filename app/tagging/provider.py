"""打标引擎调用封装(迁自旧 src/providers.py,抽象为可 mock 接口)。

- TaggingProvider:抽象接口,call(image_bytes, prompt_text) -> CallResult。测试注入 Fake 实现,
  CI 全程 mock、不出现任何真实密钥。
- QwenVLProvider:OpenAI 兼容实现,内部处理指数退避重试与 token/耗时统计(原样迁移)。
  发送前长边压缩为 JPEG data URI(控成本)。密钥只从环境变量取。
"""
from __future__ import annotations

import abc
import base64
import io
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CallResult:
    text: str                 # 模型原始文本响应(不解析)
    input_tokens: int
    output_tokens: int
    latency_ms: int
    retries: int


class TaggingProvider(abc.ABC):
    model_id: str
    # 调用来源标识,随任务落 task.output._provider,用于区分真实调用与 mock(冒烟测试据此断言)
    provider_id: str = "unknown"

    @abc.abstractmethod
    def call(self, image_bytes: bytes, prompt_text: str) -> CallResult:
        """发送 图片+文本,返回原始文本响应与用量。失败在实现内按退避重试,耗尽后抛异常。"""


class ProviderConfigError(Exception):
    pass


class ProviderCallError(Exception):
    """一次调用在重试耗尽后仍失败。"""


def _encode_image_data_uri(image_bytes: bytes, max_edge: int = 1568) -> str:
    """按长边压缩后编码为 base64 data URI,统一转 JPEG(迁自旧 encode_image_data_uri,改吃 bytes)。"""
    from PIL import Image

    try:
        import pillow_heif

        pillow_heif.register_heif_opener()  # 让 PIL 能读 iPhone .HEIC
    except ImportError:
        pass

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    scale = max_edge / max(w, h)
    if scale < 1:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


class QwenVLProvider(TaggingProvider):
    provider_id = "qwen"

    def __init__(
        self,
        *,
        model_id: str,
        base_url: str,
        api_key: str,
        max_retries: int = 3,
        temperature: float = 0,
        image_max_edge: int = 1568,
    ) -> None:
        if not api_key:
            raise ProviderConfigError("DASHSCOPE_API_KEY 未设置,无法初始化 QwenVLProvider")
        from openai import OpenAI

        self.model_id = model_id
        self.max_retries = max_retries
        self.temperature = temperature
        self.image_max_edge = image_max_edge
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def call(self, image_bytes: bytes, prompt_text: str) -> CallResult:
        data_uri = _encode_image_data_uri(image_bytes, self.image_max_edge)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ]
        last_err: Optional[Exception] = None
        start = time.monotonic()
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model_id, messages=messages, temperature=self.temperature
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                text = resp.choices[0].message.content or ""
                usage = resp.usage
                return CallResult(
                    text=text,
                    input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                    output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
                    latency_ms=latency_ms,
                    retries=attempt,
                )
            except Exception as e:  # 统一重试,耗尽后交调用方
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                continue
        raise ProviderCallError(f"Qwen 调用失败,已重试 {self.max_retries} 次:{last_err}")


def get_default_provider() -> TaggingProvider:
    """从配置/环境构建生产 provider(真实 Qwen 冒烟用;CI/测试不走这里,注入 Fake)。"""
    from app.config import get_settings

    s = get_settings()
    return QwenVLProvider(
        model_id="qwen-vl-max",
        base_url=s.qwen_base_url,
        api_key=s.dashscope_api_key,
        image_max_edge=1568,
        temperature=0,
    )
