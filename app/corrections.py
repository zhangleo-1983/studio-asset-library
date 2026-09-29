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
from app.tagging import vocab
from app.packs import get_pack


class CorrectionError(ValueError):
    """人工修正被闸门/状态机守卫拒绝(非法概念键、非法状态迁移、role 不合法等)。"""


def _tag_row(session: Session, tenant_id: int, tag_id: int):
    row = session.execute(
        text("SELECT dimension, value, status FROM tag WHERE tag_id=:id AND tenant_id=:t"),
        {"id": tag_id, "t": tenant_id},
    ).first()
    if row is None:
        raise ValueError(f"tag {tag_id} 不存在(租户 {tenant_id})")
    return {"dimension": row[0], "value": row[1], "status": row[2]}


def _current_vocab_version(session: Session, tenant_id: int, dimension: str) -> int:
    """当期配置锁定的某维词表版本;取不到即拒绝(不猜、不取最新)【裁决七】。"""
    cfg = current_config(session, tenant_id, "tagging")
    vv = (cfg or {}).get("payload", {}).get("vocab_versions", {}).get(dimension) if cfg else None
    if vv is None:
        raise CorrectionError(f"租户 {tenant_id} 当期配置未锁定 {dimension} 维词表版本,无法校验概念键")
    return int(vv)


def _assert_concept_active(session: Session, tenant_id: int, dimension: str, value: str) -> None:
    """受约束维:目标值必须是当期版本在册且 active 的 concept_key(P1-1,同模型侧 N12 闸门)。"""
    if dimension not in get_pack().constrained_dimensions:
        return
    vv = _current_vocab_version(session, tenant_id, dimension)
    if not vocab.concept_key_is_active(session, tenant_id, dimension, vv, value):
        raise CorrectionError(
            f"'{value}' 不是 {dimension} 维当期版本(v_id={vv})在册的 concept_key;"
            f"应先扩词表/补 alias 再转正,不得直接落非法概念键"
        )


def _assert_role_shape(dimension: str, role: Optional[str]) -> None:
    """role 双向早失败(P1-1,与 events.py 早失败风格一致,不靠 DB CHECK 兜)。"""
    roles = get_pack().roles_for(dimension)
    if roles:
        if role not in roles:
            raise CorrectionError(f"{dimension} 维必须指定 role ∈ {set(roles)}")
    elif role is not None:
        raise CorrectionError(f"{dimension} 维不得带 role(role_shape 双向)")


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
    """改值(含 unresolved 转正)。返回 correction_id。

    守卫:①状态机——仅 active|unresolved 可 update(P1-2);②闸门——受约束维目标值须当期在册(P1-1)。
    """
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        cur = _tag_row(session, tenant_id, tag_id)
        if cur["status"] not in ("active", "unresolved"):
            raise CorrectionError(
                f"update 仅允许 active|unresolved 标签;当前 status={cur['status']}"
                "(removed 请用 restore;superseded 复活需单独提设计)"
            )
        _assert_concept_active(session, tenant_id, cur["dimension"], new_value)
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
    """恢复被删标签:status 迁回 active。返回 correction_id。

    守卫:仅 removed 可 restore(P1-2)——superseded 不给隐式复活通道,active 不空转。
    """
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        cur = _tag_row(session, tenant_id, tag_id)
        if cur["status"] != "removed":
            raise CorrectionError(
                f"restore 仅允许 removed 标签;当前 status={cur['status']}"
                "(superseded 复活需单独提设计)"
            )
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

    - 带 roles 的维度 role 必填(role_shape 双向 CHECK);其余维 role 必须为空。
    - 受约束维记 vocab_version_id【N11】:未显式给则取当期配置锁定版本(缩小查询②"待归类"桶)。
    """
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        _assert_role_shape(dimension, role)  # P1-1:role 双向早失败
        if dimension in get_pack().constrained_dimensions:
            # N11:记 vocab_version_id;未显式给则取当期配置锁定版本
            if vocab_version_id is None:
                vocab_version_id = _current_vocab_version(session, tenant_id, dimension)
            # P1-1:补漏标的值也必须是该版本在册的合法 concept_key(不得裸落非法键)
            if not vocab.concept_key_is_active(session, tenant_id, dimension, vocab_version_id, value):
                raise CorrectionError(
                    f"'{value}' 不是 {dimension} 维版本 v_id={vocab_version_id} 在册的 concept_key"
                )
        else:
            vocab_version_id = None  # 自由文本维不记

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
