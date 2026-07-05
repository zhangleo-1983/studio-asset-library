"""当前生效配置指针(active_config)的唯一读写路径。【OQ-1/裁决七】

方案二(显式生效指针):`(tenant_id, scope) → 当前生效 config_version`。
- 读:`current_config_version_id()` —— worker 与【A-4】归一化解析取"当期配置"一律经此,
      **禁止取最新 created_at、禁止硬编码**。
- 写:`activate_config()` —— 唯一推指针函数。UPDATE 指针 + 必落 `config_activate` 事件
      (sensitive=true,payload 带 from/to)。回滚 = 再调一次把指针拨回旧值,事件可辨识。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.events import record_event


def current_config_version_id(session: Session, tenant_id: int, scope: str) -> Optional[int]:
    """取某(租户,scope)当前生效的 config_version_id;未激活则 None。"""
    row = session.execute(
        text(
            "SELECT config_version_id FROM active_config "
            "WHERE tenant_id = :tid AND scope = :scope"
        ),
        {"tid": tenant_id, "scope": scope},
    ).first()
    return None if row is None else int(row[0])


def activate_config(
    session: Session,
    *,
    tenant_id: int,
    scope: str,
    config_version_id: int,
    actor_kind: str,
    actor_user_id: Optional[int] = None,
) -> int:
    """把(租户,scope)的当前生效配置推到 config_version_id。返回被激活的 config_version_id。

    唯一推指针入口:UPSERT active_config + 落 config_activate 事件(from/to 进 payload)。
    """
    # 1) 读旧指针(用于 from/to 与回滚辨识)
    from_id = current_config_version_id(session, tenant_id, scope)

    if from_id == config_version_id:
        # 幂等:已指向同一版本,不重复 UPDATE、不重复落事件。
        return config_version_id

    # 2) UPSERT 指针(本表非只增,可 UPDATE)
    session.execute(
        text(
            """
            INSERT INTO active_config (tenant_id, scope, config_version_id, updated_at)
            VALUES (:tid, :scope, :cvid, now())
            ON CONFLICT (tenant_id, scope)
            DO UPDATE SET config_version_id = EXCLUDED.config_version_id, updated_at = now()
            """
        ),
        {"tid": tenant_id, "scope": scope, "cvid": config_version_id},
    )

    # 3) 必落事件(sensitive=true,由 record_event 按 event_type 集中推导)
    record_event(
        session,
        tenant_id=tenant_id,
        event_type="config_activate",
        actor_kind=actor_kind,
        actor_user_id=actor_user_id,
        subject_type="config_version",
        subject_id=config_version_id,
        payload={"scope": scope, "from": from_id, "to": config_version_id},
    )
    return config_version_id
