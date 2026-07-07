"""打标测试夹具:录制的模型输出样例(含"不守 schema"变体)+ Fake provider + 造图。

CI 全程用 FakeProvider,不出现任何真实密钥。样例必须覆盖旧 CLAUDE.md 第 5 条的漂移:
theme 被包成对象、structure_types/primary 是裸字符串、词表外词形、JSON 外裹解释文字。
"""
from __future__ import annotations

import io
import json

from app.tagging.provider import CallResult, TaggingProvider

# ── 正常输出:结构/配色/场景/主题/配色名俱全,词表内 ────────────────
VALID = {
    "image_id": "sample",
    "theme": "爱心",
    "theme_type": "通用元素",
    "color_scheme": {"primary": ["红", "金"], "accent": ["白"], "scheme_name": "红金"},
    "structure_types": ["立柱", "拱门"],
    "scene_guess": "婚礼",
    "suggested_filename": "爱心主题红金配色婚礼立柱",
    "confidence": 0.95,
    "needs_review": False,
    "notes": "",
}

# ── 变体1:theme 被包成对象(应被 coerce_theme_str 摘成 "爱心")────────
THEME_AS_OBJECT = {
    **VALID,
    "theme": {"name": "爱心", "theme_type": "通用元素"},
}

# ── 变体2:structure_types / primary 是裸字符串(应被 coerce_str_list 包成数组)──
BARE_STRINGS = {
    **VALID,
    "color_scheme": {"primary": "多巴胺", "accent": [], "scheme_name": "多巴胺"},
    "structure_types": "立柱",
}

# ── 变体3:词表外造型(背景墙)→ 归一化反查失败 → unresolved ──────────
OUT_OF_VOCAB = {
    **VALID,
    "structure_types": ["背景墙"],
    "confidence": 0.4,
    "needs_review": True,
}

# ── 变体4:别名命中(气球花盒 → flowerbox)+ 低置信度 ────────────────
ALIAS_HIT = {
    **VALID,
    "structure_types": ["气球花盒"],
    "confidence": 0.5,
}


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
