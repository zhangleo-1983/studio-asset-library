"""模型原始输出 → 结构化(经兜底函数)。

原始输出**原样保留**给 task.output(调用方负责落库);本模块只负责把它解析为 TaggingOutput,
**先过 coerce 兜底**(migration §1.5)再构建,绝不假设输出严格守 schema。
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.schemas import ColorScheme, TaggingOutput
from app.tagging.coerce import coerce_str_list, coerce_theme_str


class ParseError(Exception):
    """模型输出连 JSON 都不是。"""


def extract_json_obj(raw_text: str) -> dict:
    """从模型文本中取出 JSON 对象(容忍前后包裹的解释性文字/代码块围栏)。"""
    try:
        obj = json.loads(raw_text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception as e:
            raise ParseError(f"提取到疑似 JSON 但解析失败:{e}") from e
    raise ParseError("模型输出中未找到 JSON 对象")


def to_tagging_output(raw_obj: dict[str, Any]) -> TaggingOutput:
    """把原始 dict 经兜底函数规整为 TaggingOutput。"""
    cs = raw_obj.get("color_scheme") or {}
    if not isinstance(cs, dict):
        cs = {}
    color = ColorScheme(
        primary=coerce_str_list(cs.get("primary")),
        accent=coerce_str_list(cs.get("accent")),
        scheme_name=cs.get("scheme_name"),
    )
    return TaggingOutput(
        image_id=raw_obj.get("image_id"),
        theme=coerce_theme_str(raw_obj.get("theme")),
        theme_type=raw_obj.get("theme_type"),
        color_scheme=color,
        structure_types=coerce_str_list(raw_obj.get("structure_types")),
        scene_guess=raw_obj.get("scene_guess"),
        suggested_filename=raw_obj.get("suggested_filename"),
        confidence=raw_obj.get("confidence"),
        needs_review=bool(raw_obj.get("needs_review", False)),
        notes=raw_obj.get("notes") or "",
    )
