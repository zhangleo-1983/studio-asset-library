"""人工修正四操作(architecture §3.3【C1】,范围7)。【不变量二、五 · 承重路径】

update / remove / restore 走**修正链**(tag_correction 只增)+ record_event;任何一种都**不覆盖/
不销毁原始值**(原始值 = 最早一行 update 的 old_value;无 update 时 = tag.value【N4】)。
add(补漏标)= 新增 source='human' 行,**不走修正链**,仅落 event【C1 改法3】。

- update:改值(含 unresolved 转正:old=原词形, new=concept_key, status 迁回 active【A-6 闭环】)。
- remove:删错标,status='removed',检索退出、原行/溯源永久保留。
- restore:恢复被删标签,status 迁回 active。
- add:human 补漏标;受约束维记 vocab_version_id【N11】;color 维 role 必填(role_shape)。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.active_config import current_config
from app.context import get_current_tenant
from app.db import tenant_session
from app.events import record_event
from app.tagging.vocab import CONSTRAINED_DIMENSIONS


def _tag_row(session: Session, tenant_id: int, tag_id: int):
    row = session.execute(
        text("SELECT dimension, value, status FROM tag WHERE tag_id=:id AND tenant_id=:t"),
        {"id": tag_id, "t": tenant_id},
    ).first()
    if row is None:
        raise ValueError(f"tag {tag_id} 不存在(租户 {tenant_id})")
    return {"dimension": row[0], "value": row[1], "status": row[2]}


def _insert_correction(
    session: Session, tenant_id: int, tag_id: int, kind: str,
    old_value: Optional[str], new_value: Optional[str], corrected_by: int, reason: Optional[str],
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO tag_correction
                    (tenant_id, tag_id, kind, old_value, new_value, source, corrected_by, reason)
                VALUES (:t, :tag, :kind, :old, :new, 'human', :by, :reason)
                RETURNING correction_id
                """
            ),
            {"t": tenant_id, "tag": tag_id, "kind": kind, "old": old_value,
             "new": new_value, "by": corrected_by, "reason": reason},
        ).scalar_one()
    )


def _event_correction(session, tenant_id, corrected_by, tag_id, payload) -> None:
    record_event(
        session, tenant_id=tenant_id, event_type="correction", actor_kind="human",
        actor_user_id=corrected_by, subject_type="tag", subject_id=tag_id, payload=payload,
    )


def update_tag(tag_id: int, new_value: str, *, corrected_by: int, reason: Optional[str] = None) -> int:
    """改值(含 unresolved 转正)。返回 correction_id。"""
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        cur = _tag_row(session, tenant_id, tag_id)
        cid = _insert_correction(session, tenant_id, tag_id, "update", cur["value"], new_value, corrected_by, reason)
        # 改值 + 迁回 active(unresolved 转正 / active 保持);current_correction_id 指针由唯一写入路径维护【N8】
        session.execute(
            text("UPDATE tag SET value=:v, status='active', current_correction_id=:cid "
                 "WHERE tag_id=:id AND tenant_id=:t"),
            {"v": new_value, "cid": cid, "id": tag_id, "t": tenant_id},
        )
        _event_correction(session, tenant_id, corrected_by, tag_id,
                          {"kind": "update", "dimension": cur["dimension"],
                           "old": cur["value"], "new": new_value})
        return cid


def remove_tag(tag_id: int, *, corrected_by: int, reason: Optional[str] = None) -> int:
    """删错标:status='removed',原值/溯源永久保留。返回 correction_id。"""
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        cur = _tag_row(session, tenant_id, tag_id)
        cid = _insert_correction(session, tenant_id, tag_id, "remove", cur["value"], None, corrected_by, reason)
        session.execute(
            text("UPDATE tag SET status='removed', current_correction_id=:cid "
                 "WHERE tag_id=:id AND tenant_id=:t"),
            {"cid": cid, "id": tag_id, "t": tenant_id},
        )
        _event_correction(session, tenant_id, corrected_by, tag_id,
                          {"kind": "remove", "dimension": cur["dimension"], "value": cur["value"]})
        return cid


def restore_tag(tag_id: int, *, corrected_by: int, reason: Optional[str] = None) -> int:
    """恢复被删标签:status 迁回 active。返回 correction_id。"""
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        cur = _tag_row(session, tenant_id, tag_id)
        cid = _insert_correction(session, tenant_id, tag_id, "restore", None, None, corrected_by, reason)
        session.execute(
            text("UPDATE tag SET status='active', current_correction_id=:cid "
                 "WHERE tag_id=:id AND tenant_id=:t"),
            {"cid": cid, "id": tag_id, "t": tenant_id},
        )
        _event_correction(session, tenant_id, corrected_by, tag_id,
                          {"kind": "restore", "dimension": cur["dimension"]})
        return cid


def add_tag(
    asset_id: int, dimension: str, value: str, *, added_by: int,
    role: Optional[str] = None, vocab_version_id: Optional[int] = None,
) -> int:
    """human 补漏标:新增 source='human' 行,不走修正链,仅落 event。返回 tag_id。

    - color 维 role 必填(role_shape 双向 CHECK);非 color 维 role 必须为空。
    - 受约束维记 vocab_version_id【N11】:未显式给则取当期配置锁定版本(缩小查询②"待归类"桶)。
    """
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        if dimension in CONSTRAINED_DIMENSIONS and vocab_version_id is None:
            cfg = current_config(session, tenant_id, "tagging")
            if cfg:
                vocab_version_id = cfg["payload"].get("vocab_versions", {}).get(dimension)
        # 自由文本维不记 vocab_version_id
        if dimension not in CONSTRAINED_DIMENSIONS:
            vocab_version_id = None

        tag_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO tag
                        (tenant_id, asset_id, dimension, value, role, status, source,
                         vocab_version_id, needs_review)
                    VALUES (:t, :a, :dim, :val, :role, 'active', 'human', :vv, false)
                    RETURNING tag_id
                    """
                ),
                {"t": tenant_id, "a": asset_id, "dim": dimension, "val": value,
                 "role": role, "vv": vocab_version_id},
            ).scalar_one()
        )
        _event_correction(session, tenant_id, added_by, tag_id,
                          {"kind": "add", "dimension": dimension, "value": value, "role": role})
        return tag_id
