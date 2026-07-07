"""复核队列(架构 §3.3,范围6)——视图级查询,不建子系统。

进队条件:confidence < 阈值 OR needs_review OR status='unresolved'。
阈值是**租户级配置**,取自当期 config_version.payload.review_threshold(经 active_config),
兜底 settings.review_confidence_threshold。检索一律只查 active/unresolved(removed/superseded 不进队)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text

from app.active_config import current_config
from app.config import get_settings
from app.context import get_current_tenant
from app.db import tenant_session


@dataclass(frozen=True)
class ReviewItem:
    tag_id: int
    asset_id: int
    dimension: str
    value: str
    status: str
    confidence: Optional[float]
    needs_review: bool


def _threshold(session, tenant_id: int) -> float:
    cfg = current_config(session, tenant_id, "tagging")
    if cfg and isinstance(cfg["payload"], dict) and "review_threshold" in cfg["payload"]:
        return float(cfg["payload"]["review_threshold"])
    return float(get_settings().review_confidence_threshold)


def review_queue(dimension: Optional[str] = None) -> list[ReviewItem]:
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        threshold = _threshold(session, tenant_id)
        rows = session.execute(
            text(
                """
                SELECT tag_id, asset_id, dimension, value, status, confidence, needs_review
                FROM tag
                WHERE tenant_id = :t
                  AND status IN ('active','unresolved')
                  AND (status='unresolved' OR needs_review = true
                       OR (confidence IS NOT NULL AND confidence < :th))
                  AND (:dim IS NULL OR dimension = :dim)
                ORDER BY (status='unresolved') DESC, confidence NULLS LAST, tag_id
                """
            ),
            {"t": tenant_id, "th": threshold, "dim": dimension},
        ).all()
    return [
        ReviewItem(
            tag_id=int(r[0]), asset_id=int(r[1]), dimension=r[2], value=r[3],
            status=r[4], confidence=(float(r[5]) if r[5] is not None else None),
            needs_review=bool(r[6]),
        )
        for r in rows
    ]
