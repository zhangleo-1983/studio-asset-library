"""相似/同款召回:标签重合度计分(纯 SQL,**不引向量检索**——落在禁做红线内)。

计分口径由行业包 pack.json 的 demo.recall 声明:每条 {dimension, role?, weight},
按 (维度, 角色) 命中累计权重;有 role 的维度要求两侧 role 一致。
输入是"上传图的标签集"(在线=DB 实标签;断网兜底=预打标缓存标签),对演示图库候选计分排序。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.packs import get_pack


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
    weights = get_pack().demo.get("recall", [])
    if not weights:
        return []
    # 权重 CASE 由包配置生成:维度/角色以绑定参数传入,不拼进 SQL 文本
    case_parts, params = [], {}
    for i, w in enumerate(weights):
        params[f"wd{i}"], params[f"ww{i}"] = w["dimension"], int(w["weight"])
        role_cond = ""
        if w.get("role"):
            params[f"wr{i}"] = w["role"]
            role_cond = f" AND t.role = :wr{i}"
        case_parts.append(f"WHEN t.dimension = :wd{i}{role_cond} THEN :ww{i}")
    score_sql = "CASE " + " ".join(case_parts) + " ELSE 0 END"
    dims = [t.dimension for t in up_tags]
    vals = [t.value for t in up_tags]
    roles = [t.role for t in up_tags]
    rows = session.execute(
        text(
            f"""
            WITH up(dimension, value, role) AS (
                SELECT * FROM unnest(
                    CAST(:dims AS text[]), CAST(:vals AS text[]), CAST(:roles AS text[])
                )
            )
            SELECT t.asset_id,
                   SUM({score_sql})::int AS score
            FROM tag t
            JOIN up ON up.dimension = t.dimension AND up.value = t.value
                   AND t.role IS NOT DISTINCT FROM up.role
            WHERE t.tenant_id = :tenant
              AND t.status = 'active'
              AND (:excl IS NULL OR t.asset_id <> :excl)
            GROUP BY t.asset_id
            ORDER BY score DESC, t.asset_id
            LIMIT :limit
            """
        ),
        {**params, "dims": dims, "vals": vals, "roles": roles,
         "tenant": tenant_id, "excl": exclude_asset_id, "limit": limit},
    ).all()
    return [RecallHit(asset_id=int(r[0]), score=int(r[1])) for r in rows]
