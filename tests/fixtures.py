"""打标测试夹具(与行业无关部分):Fake provider + 造图 + 原始文本包装。

CI 全程用 FakeProvider,不出现任何真实密钥。行业相关的录制样例在各行业包的 tests/samples.py。
"""
from __future__ import annotations

import io
import json

from app.tagging.provider import CallResult, TaggingProvider

def as_raw_text(obj: dict, *, wrap_prose: bool = False) -> str:
    """把样例 dict 变成模型"原始文本"。wrap_prose=True 时外裹解释文字+代码块围栏,考验提取。"""
    j = json.dumps(obj, ensure_ascii=False)
    if wrap_prose:
        return f"好的,分析结果如下:\n```json\n{j}\n```\n以上。"
    return j


class FakeProvider(TaggingProvider):
    """按顺序吐预设原始文本;记录被调用次数。不触碰图片字节、不需要密钥。"""

    def __init__(self, raw_texts: list[str], *, model_id: str = "qwen-vl-max",
                 input_tokens: int = 100, output_tokens: int = 50, retries: int = 0):
        self._texts = list(raw_texts)
        self.model_id = model_id
        self.calls = 0
        self._it, self._ot, self._ret = input_tokens, output_tokens, retries

    def call(self, image_bytes: bytes, prompt_text: str) -> CallResult:
        text = self._texts[min(self.calls, len(self._texts) - 1)]
        self.calls += 1
        return CallResult(text=text, input_tokens=self._it, output_tokens=self._ot,
                          latency_ms=12, retries=self._ret)


class RaisingProvider(TaggingProvider):
    """总是抛异常,模拟重试耗尽后的失败,验证 task 落 failed。"""

    model_id = "qwen-vl-max"

    def call(self, image_bytes: bytes, prompt_text: str) -> CallResult:
        raise RuntimeError("模拟 provider 失败")


def make_png_bytes(color: tuple = (200, 30, 40), size: tuple = (8, 8)) -> bytes:
    """造一张微型 PNG 供 ingest 落盘/算 hash(provider 已 mock,不真解析像素)。"""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()
