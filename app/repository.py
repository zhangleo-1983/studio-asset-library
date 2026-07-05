"""租户侧数据访问示例(骨架)。

这里不是打标业务逻辑,只是"所有 DB 访问必须经租户上下文"的落地示范:每个函数都走
tenant_session()(缺租户上下文即 NoTenantContext),并用 get_current_tenant() 拼 WHERE。
打标闭环的真实仓储在后续阶段实现。
"""
from __future__ import annotations

from sqlalchemy import text

from app.context import get_current_tenant
from app.db import tenant_session


def count_vocabulary() -> int:
    """当前租户可见的词表条目数。租户过滤由上下文强制注入。"""
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        return int(
            session.execute(
                text("SELECT count(*) FROM vocabulary WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            ).scalar_one()
        )


def list_concept_keys(dimension: str) -> list[str]:
    """当前租户某维度的 concept_key 列表(按 concept_key 排序)。"""
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        rows = session.execute(
            text(
                """
                SELECT concept_key FROM vocabulary
                WHERE tenant_id = :tid AND dimension = :dim
                ORDER BY concept_key
                """
            ),
            {"tid": tenant_id, "dim": dimension},
        ).scalars().all()
        return list(rows)
