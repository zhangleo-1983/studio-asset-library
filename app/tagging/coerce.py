"""模型输出 schema 兜底函数。

模型输出经常不严格守 schema。任何读取模型输出字段的新代码,都要**先过这些兜底函数**,
不能假设输出严格符合输出 schema。
"""
from __future__ import annotations

from typing import Any


def coerce_scalar(value: Any):
    """个别响应会把标量字段包成 {"name": ..., "<type>": ...} 而不是纯字符串,做个兜底摘取。"""
    if isinstance(value, dict):
        return value.get("name") or value.get("theme") or None
    return value


def coerce_str_list(value: Any) -> list:
    """按 schema 应为数组的字段,个别响应会给单个字符串。字符串直接 join 会被拆成单字,
    这里做兜底包装成单元素列表。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def coerce_str(value: Any):
    """单值字段:原样返回(空串/None 由调用方按"无值"处理)。"""
    return value
