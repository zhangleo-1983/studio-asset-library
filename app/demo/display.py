"""展示层:concept_key → 中文词形翻译 + 四维视图组装。

对客户永远展示中文词形(经 vocabulary.labels.zh),不吐 concept_key【A-5/Q8】。
自由文本维(theme/color_scheme)与 unresolved 裸词形按原值展示。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.active_config import current_config
from app.demo.recall import UpTag


def _vocab_versions(session: Session, tenant_id: int) -> dict:
    cfg = current_config(session, tenant_id, "tagging")
    return (cfg or {}).get("payload", {}).get("vocab_versions", {}) if cfg else {}


def _zh(session: Session, tenant_id: int, dimension: str, value: str, vv: Optional[int]) -> str:
    """受约束维 concept_key→labels.zh;取不到(自由文本/unresolved)则原值。"""
    if vv is None:
        return value
    row = session.execute(
        text("SELECT labels->>'zh' FROM vocabulary "
             "WHERE tenant_id=:t AND dimension=:d AND vocab_version_id=:v AND concept_key=:c"),
        {"t": tenant_id, "d": dimension, "v": vv, "c": value},
    ).first()
    return row[0] if row and row[0] else value


def asset_up_tags(session: Session, tenant_id: int, asset_id: int) -> list[UpTag]:
    """取某资产的 active 标签,作召回输入。"""
    rows = session.execute(
        text("SELECT dimension, value, role FROM tag "
             "WHERE tenant_id=:t AND asset_id=:a AND status='active'"),
        {"t": tenant_id, "a": asset_id},
    ).all()
    return [UpTag(dimension=r[0], value=r[1], role=r[2]) for r in rows]


def four_dim_view(session: Session, tenant_id: int, up_tags: list[UpTag]) -> dict:
    """把标签集组装成客户可读的四维视图(中文词形)。"""
    vv = _vocab_versions(session, tenant_id)
    view: dict = {"theme": None, "scene": None, "structure": [], "colors": [], "scheme_name": None}
    for t in up_tags:
        if t.dimension == "theme":
            view["theme"] = t.value
        elif t.dimension == "color_scheme":
            view["scheme_name"] = t.value
        elif t.dimension == "scene":
            view["scene"] = _zh(session, tenant_id, "scene", t.value, vv.get("scene"))
        elif t.dimension == "structure":
            view["structure"].append(_zh(session, tenant_id, "structure", t.value, vv.get("structure")))
        elif t.dimension == "color":
            view["colors"].append({
                "zh": _zh(session, tenant_id, "color", t.value, vv.get("color")),
                "role": t.role,
            })
    return view
