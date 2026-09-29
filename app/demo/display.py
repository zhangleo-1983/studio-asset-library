"""展示层:concept_key → 中文词形翻译 + 视图组装。

对外永远展示中文词形(经 vocabulary.labels.zh),不吐 concept_key【A-5/Q8】。
自由文本维与 unresolved 裸词形按原值展示。展示哪些字段、顺序、显示名由行业包 pack.json 的 demo.view 声明。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.active_config import current_config
from app.demo.recall import UpTag
from app.packs import get_pack


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


def dimension_view(session: Session, tenant_id: int, up_tags: list[UpTag]) -> dict:
    """把标签集按行业包的 demo.view 组装成可读视图(中文词形)。

    返回 {"fields": [{"label", "caption", "items": [{"text", "role"}]}]};
    role 是原始角色键,展示名由 UI 文案的 role_labels 映射。
    """
    pack = get_pack()
    vv = _vocab_versions(session, tenant_id)
    fields = []
    for spec in pack.demo.get("view", []):
        dim = spec["dimension"]
        items = []
        for t in up_tags:
            if t.dimension != dim:
                continue
            text_ = _zh(session, tenant_id, dim, t.value, vv.get(dim)) if spec.get("translate") else t.value
            items.append({"text": text_, "role": t.role if spec.get("show_role") else None})
        cap_dim = spec.get("caption_dimension")
        caption = next((t.value for t in up_tags if t.dimension == cap_dim), None) if cap_dim else None
        fields.append({"label": spec["label"], "caption": caption, "items": items})
    return {"fields": fields}
