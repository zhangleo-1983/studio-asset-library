"""tagging_output_v2 —— 打标输出 schema 的 pydantic 落地(migration §1.6)。

与 schema/tagging_output_v2.json(原文迁自旧项目 output_schema.json,title
`balloon_tagging_output_v2`)配套的"双份"。字段完全沿用。

**刻意宽松**:模型输出常不严格守 schema(旧 CLAUDE.md 第 5 条)。本模型是"经兜底函数
coerce 之后"的目标结构;theme_type / scene_guess 保留为自由字符串(不强制 enum),避免模型
漂移出枚举时整条校验失败——枚举语义交给 JSON Schema 留档与归一化解析层处理。
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

TAGGING_OUTPUT_SCHEMA_VERSION = "tagging_output_v2"


class ColorScheme(BaseModel):
    primary: List[str] = Field(default_factory=list)  # 主色(经 coerce_str_list 兜底为数组)
    accent: List[str] = Field(default_factory=list)   # 点缀色
    scheme_name: Optional[str] = None                  # 色系简称,如"红金"


class TaggingOutput(BaseModel):
    image_id: Optional[str] = None
    theme: Optional[str] = None            # 经 coerce_theme_str 兜底为字符串/None
    theme_type: Optional[str] = None       # IP角色|通用元素|无主题(不强制 enum,防漂移)
    color_scheme: ColorScheme = Field(default_factory=ColorScheme)
    structure_types: List[str] = Field(default_factory=list)  # 多选(经 coerce_str_list 兜底)
    scene_guess: Optional[str] = None      # 场景(不强制 enum)
    suggested_filename: Optional[str] = None
    confidence: Optional[float] = None
    needs_review: bool = False
    notes: Optional[str] = ""
