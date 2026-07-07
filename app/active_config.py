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


def current_config(session: Session, tenant_id: int, scope: str) -> Optional[dict]:
    """取当期生效配置的完整信息(worker/解析取"在什么规则下打"的唯一入口)。

    返回 {config_version_id, payload(dict), prompt_version, prompt_sha256};未激活则 None。
    """
    row = session.execute(
        text(
            """
            SELECT cv.config_version_id, cv.payload, cv.prompt_version, cv.prompt_sha256
            FROM active_config ac
            JOIN config_version cv ON cv.config_version_id = ac.config_version_id
            WHERE ac.tenant_id = :tid AND ac.scope = :scope
            """
        ),
        {"tid": tenant_id, "scope": scope},
    ).first()
    if row is None:
        return None
    return {
        "config_version_id": int(row[0]),
        "payload": row[1],
        "prompt_version": row[2],
        "prompt_sha256": row[3],
    }


class CrossTenantConfigError(ValueError):
    """生效指针或其锁定的词表版本跨租户引用(不变量一)。"""


def _assert_config_belongs(session: Session, tenant_id: int, config_version_id: int) -> None:
    """config_version 属本租户,且 payload.vocab_versions 每维版本行属本租户且 dimension 正确。"""
    row = session.execute(
        text("SELECT tenant_id, payload FROM config_version WHERE config_version_id=:c"),
        {"c": config_version_id},
    ).first()
    if row is None:
        raise CrossTenantConfigError(f"config_version {config_version_id} 不存在")
    if int(row[0]) != int(tenant_id):
        raise CrossTenantConfigError(
            f"config_version {config_version_id} 属租户 {row[0]},不能被租户 {tenant_id} 激活"
        )
    payload = row[1] if isinstance(row[1], dict) else {}
    for dim, vvid in (payload.get("vocab_versions") or {}).items():
        vv = session.execute(
            text("SELECT tenant_id, dimension FROM vocabulary_version WHERE vocab_version_id=:v"),
            {"v": vvid},
        ).first()
        if vv is None or int(vv[0]) != int(tenant_id) or vv[1] != dim:
            raise CrossTenantConfigError(
                f"payload.vocab_versions[{dim}]={vvid} 归属校验失败"
                f"(应属租户 {tenant_id} 且 dimension={dim})"
            )


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
    # 0) 跨租户防线【P1-3 / 不变量一】:指针目标必须属本租户,payload.vocab_versions 逐维归属正确。
    #    库层另有复合外键兜底(0004);此处应用层早失败,给清楚报错。
    _assert_config_belongs(session, tenant_id, config_version_id)

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
