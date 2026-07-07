"""模型输出 schema 兜底函数(migration §1.5,原样迁自旧项目 src/score.py)。

旧 CLAUDE.md 第 5 条:模型输出经常不严格守 schema。任何读取 Qwen 四维字段的新代码,都要
**先过这两个兜底函数**,不能假设输出严格符合 tagging_output_v2。迁移风险提示据此。
"""
from __future__ import annotations

from typing import Any


def coerce_theme_str(value: Any):
    """个别响应会把 theme 包成 {"name": ..., "theme_type": ...} 而不是纯字符串,做个兜底摘取。"""
    if isinstance(value, dict):
        return value.get("name") or value.get("theme") or None
    return value


def coerce_str_list(value: Any) -> list:
    """color_scheme.primary/accent 按 schema 应为数组,个别响应会给单个字符串
    (例如 "primary": "多巴胺")。字符串直接 join 会被拆成单字,这里做兜底包装成单元素列表。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
