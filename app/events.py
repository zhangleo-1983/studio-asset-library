"""唯一事件写入函数 + event_type→sensitive 集中映射。【不变量五 / Q7 / C6】

纪律:**所有** event 写入必须走 record_event();禁止任何调用点直接 INSERT event。
- sensitive 不由调用方手填,由本模块的集中映射按 event_type 推导【Q7】。
- actor 约束在此提前校验,与 data-model §3.8 的 event_actor_present CHECK 同构(早失败,
  给出清楚报错,而非等 DB 抛约束)【C6】。
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# ── event_type → sensitive 集中映射 ────────────────────────────
# 敏感 = 导出全库 / 删除 / 配置(含词表)变更;这三类进审计视图(WHERE sensitive)。
# correction(含 supersede 子类)→ false;其余默认 false。
_SENSITIVE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "export",         # 数据导出
        "delete",         # 删除
        "config_change",  # 配置/词表变更
    }
)


def is_sensitive(event_type: str) -> bool:
    """事件是否进审计视图。唯一判定点,调用方不得自行判断。"""
    return event_type in _SENSITIVE_EVENT_TYPES


def record_event(
    session: Session,
    *,
    tenant_id: int,
    event_type: str,
    actor_kind: str,
    actor_user_id: Optional[int] = None,
    subject_type: Optional[str] = None,
    subject_id: Optional[int] = None,
    payload: Optional[dict[str, Any]] = None,
) -> int:
    """写一条事件,返回 event_id。事件表的唯一入口。

    - actor_kind: 'human' | 'system'。human 必须带 actor_user_id(与 CHECK 同构,早失败)。
    - sensitive: 忽略任何外部传入,一律由 event_type 集中推导【Q7】。
    - tenant_id: 显式传入;平台级跨租户审计事件传 0(平台保留号)【N5】。
    """
    if actor_kind not in ("human", "system"):
        raise ValueError(f"actor_kind 只能是 'human'|'system',收到 {actor_kind!r}")
    if actor_kind == "human" and actor_user_id is None:
        raise ValueError("human 行为必须带 actor_user_id(不变量五:带行为人)【C6】")

    sensitive = is_sensitive(event_type)

    import json

    row = session.execute(
        text(
            """
            INSERT INTO event
                (tenant_id, event_type, actor_user_id, actor_kind,
                 sensitive, subject_type, subject_id, payload)
            VALUES
                (:tenant_id, :event_type, :actor_user_id, :actor_kind,
                 :sensitive, :subject_type, :subject_id, CAST(:payload AS JSONB))
            RETURNING event_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "event_type": event_type,
            "actor_user_id": actor_user_id,
            "actor_kind": actor_kind,
            "sensitive": sensitive,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "payload": None if payload is None else json.dumps(payload, ensure_ascii=False),
        },
    ).scalar_one()
    return int(row)
