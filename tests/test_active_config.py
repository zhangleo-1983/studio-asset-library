"""active_config 指针机制测试。【OQ-1/裁决七】

- 种子后指针指向被种子的 config_version,且落了 config_activate(sensitive=true)事件;
- activate_config 推指针:UPDATE 指针 + from/to 事件;幂等重推不重复落事件;
- current_config_version_id 是"当期配置"的唯一读取口径。
"""
from __future__ import annotations

from sqlalchemy import text

from app.active_config import activate_config, current_config_version_id
from app.db import platform_session
from app.seed import seed_tenant

# 专用租户号,避开其它测试的 1/2,消除跨文件顺序依赖
T = 7


def _events(session, tenant_id, event_type):
    return session.execute(
        text(
            "SELECT event_id, sensitive, payload FROM event "
            "WHERE tenant_id=:t AND event_type=:et ORDER BY event_id"
        ),
        {"t": tenant_id, "et": event_type},
    ).all()


def test_seed_auto_activates_pointer():
    assert seed_tenant(T, "ptr", "指针租户") is True

    with platform_session(reason="test:active_config") as session:
        # 种子已把当期 tagging 配置激活
        cvid = current_config_version_id(session, T, "tagging")
        assert cvid is not None
        # 指针指向的正是该租户 tagging 的 config_version
        seeded = session.execute(
            text("SELECT config_version_id FROM config_version WHERE tenant_id=:t AND scope='tagging'"),
            {"t": T},
        ).scalar_one()
        assert cvid == seeded

        # 落了一条 config_activate 且 sensitive=true,payload from=None→to=cvid
        acts = _events(session, T, "config_activate")
        assert len(acts) == 1
        assert acts[0].sensitive is True
        assert acts[0].payload == {"scope": "tagging", "from": None, "to": cvid}


def test_activate_is_idempotent_and_records_from_to():
    # 造第二个 tagging 配置行(只增),把指针推过去
    with platform_session(reason="test:repoint") as session:
        old = current_config_version_id(session, T, "tagging")
        new_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO config_version (tenant_id, scope, payload, prompt_version, created_by)
                    VALUES (:t, 'tagging', CAST('{}' AS JSONB), 'tagging_v3', NULL)
                    RETURNING config_version_id
                    """
                ),
                {"t": T},
            ).scalar_one()
        )
        activate_config(session, tenant_id=T, scope="tagging", config_version_id=new_id, actor_kind="system")

    with platform_session(reason="test:verify-repoint") as session:
        assert current_config_version_id(session, T, "tagging") == new_id
        acts = _events(session, T, "config_activate")
        assert len(acts) == 2  # 种子 1 条 + 本次 1 条
        assert acts[-1].payload == {"scope": "tagging", "from": old, "to": new_id}

    # 幂等:再推同一版本,不 UPDATE、不落新事件
    with platform_session(reason="test:idempotent") as session:
        activate_config(session, tenant_id=T, scope="tagging", config_version_id=new_id, actor_kind="system")
    with platform_session(reason="test:verify-idempotent") as session:
        assert len(_events(session, T, "config_activate")) == 2
