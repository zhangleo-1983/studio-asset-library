"""打标输出的结构化落地(与行业包的 output_schema.json 配套)。

**刻意宽松**:模型输出常不严格守 schema。本模型只承载各行业包共有的字段(image_id /
confidence / needs_review / notes)与"经兜底函数 coerce 之后"的各维度取值(fields:
{extraction 序号 → 取值});维度如何从原始输出里取值由行业包 taxonomy.json 的 extraction 决定。
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.packs import get_pack


def output_schema_version() -> str:
    """当前行业包声明的输出 schema 版本(落 task.output_schema_version)。"""
    return get_pack().output_schema_version


class TaggingOutput(BaseModel):
    image_id: Optional[str] = None
    confidence: Optional[float] = None
    needs_review: bool = False
    notes: Optional[str] = ""
    # 与 pack.extraction 一一对应:单值项为 str|None,列表项为 List[str](已过 coerce)
    values: List[Any] = Field(default_factory=list)
