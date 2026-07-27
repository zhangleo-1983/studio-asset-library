"""相似/同款召回:标签重合度计分(纯 SQL,**不引向量检索**——落在禁做红线内)。

计分口径(可调,hardcode):
  structure 同款硬命中 = 3 / 项;color primary 交集 = 2 / 项;scene = 1;theme = 1。
输入是"上传图的标签集"(在线=DB 实标签;断网兜底=预打标缓存标签),对演示图库候选计分排序。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class UpTag:
    dimension: str
    value: str
    role: Optional[str] = None


@dataclass(frozen=True)
class RecallHit:
    asset_id: int
    score: int


def recall_similar(
    session: Session,
    tenant_id: int,
    up_tags: list[UpTag],
    *,
    exclude_asset_id: Optional[int] = None,
    limit: int = 6,
) -> list[RecallHit]:
    if not up_tags:
        return []
    dims = [t.dimension for t in up_tags]
    vals = [t.value for t in up_tags]
    roles = [t.role for t in up_tags]
    rows = session.execute(
        text(
            """
            WITH up(dimension, value, role) AS (
                SELECT * FROM unnest(
                    CAST(:dims AS text[]), CAST(:vals AS text[]), CAST(:roles AS text[])
                )
            )
            SELECT t.asset_id,
                   SUM(CASE
                        WHEN t.dimension='structure' THEN 3
                        WHEN t.dimension='color' AND t.role='primary' THEN 2
                        WHEN t.dimension='color' THEN 1
                        WHEN t.dimension='scene' THEN 1
                        WHEN t.dimension='theme' THEN 1
                        ELSE 0 END)::int AS score
            FROM tag t
            JOIN up ON up.dimension = t.dimension AND up.value = t.value
                   AND (t.dimension <> 'color' OR t.role = up.role)
            WHERE t.tenant_id = :tenant
              AND t.status = 'active'
              AND (:excl IS NULL OR t.asset_id <> :excl)
            GROUP BY t.asset_id
            ORDER BY score DESC, t.asset_id
            LIMIT :limit
            """
        ),
        {"dims": dims, "vals": vals, "roles": roles,
         "tenant": tenant_id, "excl": exclude_asset_id, "limit": limit},
    ).all()
    return [RecallHit(asset_id=int(r[0]), score=int(r[1])) for r in rows]
