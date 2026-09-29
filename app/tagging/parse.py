"""模型原始输出 → 结构化(经兜底函数)。

原始输出**原样保留**给 task.output(调用方负责落库);本模块只负责把它解析为 TaggingOutput,
**先过 coerce 兜底**再构建,绝不假设输出严格守 schema。各维度从原始输出哪个路径取值、
怎么兜底,由当前行业包 taxonomy.json 的 extraction 声明。
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.packs import Pack, get_pack
from app.schemas import TaggingOutput
from app.tagging.coerce import coerce_scalar, coerce_str, coerce_str_list

_COERCE = {"str": coerce_str, "str_list": coerce_str_list, "scalar": coerce_scalar}


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


def _get_path(obj: Any, path: str) -> Any:
    """按 a.b.c 取值;中途遇到非对象即视为无值。"""
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def to_tagging_output(raw_obj: dict[str, Any], pack: Pack | None = None) -> TaggingOutput:
    """把原始 dict 经兜底函数规整为 TaggingOutput。"""
    pack = pack or get_pack()
    values = [_COERCE[x.coerce](_get_path(raw_obj, x.path)) for x in pack.extraction]
    return TaggingOutput(
        image_id=raw_obj.get("image_id"),
        confidence=raw_obj.get("confidence"),
        needs_review=bool(raw_obj.get("needs_review", False)),
        notes=raw_obj.get("notes") or "",
        values=values,
    )
