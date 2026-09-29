"""行业包专属的录制模型输出样例(含"不守 schema"变体)。

样例必须覆盖模型输出的常见漂移:标量被包成对象、列表字段是裸字符串、词表外词形、JSON 外裹解释文字。
"""
from __future__ import annotations

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
