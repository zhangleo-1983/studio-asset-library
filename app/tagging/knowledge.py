"""知识资产登记(migration §1 收尾):登记含 prompt_sha256 的生产 config_version。

裁决七只增口径:**不 UPDATE 种子那行 config_version**,而是**新增一行**(带 prompt_sha256 与
review_threshold),再经 activate_config 把当期生效指针推到新行;种子行作为历史留档不动。

词表版本:carry-forward 当期生效配置的 payload.vocab_versions(不另起机制,遵裁决七)。
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.active_config import activate_config, current_config
from app.db import platform_session
from app.events import record_event
from app.schemas import output_schema_version
from app.tagging.config_defaults import tagging_config_base
from app.tagging.prompt import prompt_sha256, prompt_version

DEFAULT_REVIEW_THRESHOLD = 0.6


def _insert_config_version(session: Session, tenant_id: int, payload: dict, sha: str) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO config_version
                    (tenant_id, scope, payload, prompt_version, prompt_sha256, created_by)
                VALUES (:t, 'tagging', CAST(:p AS JSONB), :pv, :sha, :by)
                RETURNING config_version_id
                """
            ),
            {
                "t": tenant_id,
                "p": json.dumps(payload, ensure_ascii=False),
                "pv": prompt_version(),
                "sha": sha,
                "by": None,
            },
        ).scalar_one()
    )


def register_tagging_config(
    tenant_id: int,
    *,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    actor_user_id: Optional[int] = None,
) -> int:
    """登记生产打标配置新行 + 推指针。返回新 config_version_id。幂等:若当期已带 prompt_sha256
    且 prompt_version 一致,则视为已登记,直接返回当期 id。"""
    with platform_session(reason=f"knowledge:register_tagging_config:{tenant_id}") as session:
        cur = current_config(session, tenant_id, "tagging")
        if cur is None:
            raise RuntimeError(
                f"租户 {tenant_id} 无当期 tagging 配置;请先跑种子(seed_tenant)。"
            )
        # 幂等:当期已是带 sha 的本版提示词配置
        if cur["prompt_sha256"] == prompt_sha256() and cur["prompt_version"] == prompt_version():
            return cur["config_version_id"]

        # carry-forward 词表版本;补 prompt 内容锚 + review_threshold + output schema 版本
        payload = tagging_config_base()
        payload["vocab_versions"] = cur["payload"].get("vocab_versions", {})
        payload["review_threshold"] = review_threshold
        payload["output_schema_version"] = output_schema_version()

        new_id = _insert_config_version(session, tenant_id, payload, prompt_sha256())

        # 登记事件(config_change,sensitive)+ 推指针(activate_config 内含 config_activate)
        record_event(
            session,
            tenant_id=tenant_id,
            event_type="config_change",
            actor_kind="human" if actor_user_id is not None else "system",
            actor_user_id=actor_user_id,
            subject_type="config_version",
            subject_id=new_id,
            payload={
                "action": "register_tagging_config",
                "prompt_version": prompt_version(),
                "prompt_sha256": prompt_sha256(),
                "review_threshold": review_threshold,
            },
        )
        activate_config(
            session,
            tenant_id=tenant_id,
            scope="tagging",
            config_version_id=new_id,
            actor_kind="human" if actor_user_id is not None else "system",
            actor_user_id=actor_user_id,
        )
        return new_id
