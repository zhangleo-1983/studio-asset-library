"""参数化租户种子脚本(migration.md §4 步骤 0 + 场景3小注的"租户级重放")。

接受任意 tenant 参数,把"建租户 + 建初始管理用户 + 词表种子(structure/color/scene v1)+
alias 基线 + 生产配置 + 各步 event"写成**可重放**逻辑。示例客户只是首次调用;第二个租户接入
= 以新 tenant 参数重放同一脚本,零业务代码改动(场景 3 的代码级复现)。

纪律:
- 所有 event 一律经 record_event()(不绕过);种子跑在平台侧,actor_kind='system'。
- 平台保留号 tenant_id=0 由建库迁移固化,本脚本拒绝对 0 号重放。
- 幂等:同一 tenant 重复运行不重复插入、不报错(靠 tenant 存在性短路 + 唯一约束保护)。
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import platform_session
from app.events import record_event
from app.seed_data import (
    ALIAS_BASELINE,
    COLOR,
    CONFIG_PAYLOAD_BASE,
    SCENE,
    STRUCTURE,
)

logger = logging.getLogger("balloon.seed")


def _tenant_exists(session: Session, tenant_id: int) -> bool:
    return session.execute(
        text("SELECT 1 FROM tenant WHERE tenant_id = :tid"), {"tid": tenant_id}
    ).first() is not None


def _insert_tenant(session: Session, tenant_id: int, slug: str, display_name: str, industry: str) -> None:
    session.execute(
        text(
            """
            INSERT INTO tenant (tenant_id, slug, display_name, industry, status)
            VALUES (:tid, :slug, :name, :industry, 'active')
            """
        ),
        {"tid": tenant_id, "slug": slug, "name": display_name, "industry": industry},
    )


def _insert_admin(session: Session, tenant_id: int, username: str) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO app_user (tenant_id, username, role, status)
                VALUES (:tid, :username, 'admin', 'active')
                RETURNING user_id
                """
            ),
            {"tid": tenant_id, "username": username},
        ).scalar_one()
    )


def _insert_vocab_version(
    session: Session, tenant_id: int, dimension: str, created_by: int, note: str
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO vocabulary_version
                    (tenant_id, dimension, version_no, created_by, note)
                VALUES (:tid, :dim, 1, :by, :note)
                RETURNING vocab_version_id
                """
            ),
            {"tid": tenant_id, "dim": dimension, "by": created_by, "note": note},
        ).scalar_one()
    )


def _insert_vocab_row(
    session: Session,
    tenant_id: int,
    dimension: str,
    concept_key: str,
    zh: str,
    vocab_version_id: int,
    color_kind: Optional[str] = None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO vocabulary
                (tenant_id, dimension, concept_key, labels, color_kind, active, vocab_version_id)
            VALUES
                (:tid, :dim, :ck, CAST(:labels AS JSONB), :ckind, true, :vv)
            """
        ),
        {
            "tid": tenant_id,
            "dim": dimension,
            "ck": concept_key,
            "labels": json.dumps({"zh": zh}, ensure_ascii=False),
            "ckind": color_kind,
            "vv": vocab_version_id,
        },
    )


def _insert_alias(session: Session, tenant_id: int, dimension: str, alias: str, concept_key: str) -> None:
    session.execute(
        text(
            """
            INSERT INTO alias_map (tenant_id, dimension, alias, concept_key, source)
            VALUES (:tid, :dim, :alias, :ck, 'human')
            """
        ),
        {"tid": tenant_id, "dim": dimension, "alias": alias, "ck": concept_key},
    )


def _insert_config_version(
    session: Session,
    tenant_id: int,
    created_by: int,
    payload: dict,
    prompt_version: str,
    prompt_sha256: Optional[str],
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO config_version
                    (tenant_id, scope, payload, prompt_version, prompt_sha256, created_by)
                VALUES
                    (:tid, 'tagging', CAST(:payload AS JSONB), :pv, :psha, :by)
                RETURNING config_version_id
                """
            ),
            {
                "tid": tenant_id,
                "payload": json.dumps(payload, ensure_ascii=False),
                "pv": prompt_version,
                "psha": prompt_sha256,
                "by": created_by,
            },
        ).scalar_one()
    )


def seed_tenant(
    tenant_id: int,
    slug: str,
    display_name: str,
    *,
    admin_username: Optional[str] = None,
    industry: str = "balloon_party",
    prompt_version: str = "tagging_v2",
    prompt_sha256: Optional[str] = None,
    note: str = "migrated from balloon-tagging-eval",
) -> bool:
    """为一个租户播种全部基线数据。返回 True=本次实际播种,False=已存在跳过(幂等)。

    prompt_sha256 骨架期可为 None。**注意 config_version 是只增表(迁移已 REVOKE UPDATE)**:
    提示词迁入时**不回填本行**,而是**新增一行 config_version**(带 prompt_sha256),由"当前
    生效配置"选取规则指向新行;本种子行作为历史留档永不 UPDATE。参见 docs/open-questions.md。
    """
    if tenant_id == 0:
        raise ValueError("tenant_id=0 是平台保留号,由建库迁移固化,不通过本脚本播种。")

    admin_username = admin_username or f"admin@{slug}"

    with platform_session(reason=f"seed:tenant:{tenant_id}") as session:
        if _tenant_exists(session, tenant_id):
            logger.info("租户 %s 已存在,种子跳过(幂等)。", tenant_id)
            return False

        # 1) 租户
        _insert_tenant(session, tenant_id, slug, display_name, industry)
        # 2) 初始管理用户(词表 created_by 引用它,故先于词表)【C7 依赖倒挂】
        admin_id = _insert_admin(session, tenant_id, admin_username)

        # 3) 词表种子:三维各建 version_no=1,再灌 concept_key 行
        vv_structure = _insert_vocab_version(session, tenant_id, "structure", admin_id, note)
        for ck, zh in STRUCTURE:
            _insert_vocab_row(session, tenant_id, "structure", ck, zh, vv_structure)

        vv_color = _insert_vocab_version(session, tenant_id, "color", admin_id, note)
        for ck, zh, ckind in COLOR:
            _insert_vocab_row(session, tenant_id, "color", ck, zh, vv_color, color_kind=ckind)

        vv_scene = _insert_vocab_version(session, tenant_id, "scene", admin_id, note)
        for ck, zh in SCENE:
            _insert_vocab_row(session, tenant_id, "scene", ck, zh, vv_scene)

        # 4) alias 基线
        for dim, alias, ck in ALIAS_BASELINE:
            _insert_alias(session, tenant_id, dim, alias, ck)

        # 5) 生产配置:payload 锁定本租户三维词表版本 id【N3】
        payload = copy.deepcopy(CONFIG_PAYLOAD_BASE)
        payload["vocab_versions"] = {
            "structure": vv_structure,
            "color": vv_color,
            "scene": vv_scene,
        }
        config_id = _insert_config_version(
            session, tenant_id, admin_id, payload, prompt_version, prompt_sha256
        )

        # 6) 各步 event(经 record_event 唯一写入路径;平台侧种子 actor_kind='system')
        record_event(
            session, tenant_id=tenant_id, event_type="tenant_created",
            actor_kind="system", subject_type="tenant", subject_id=tenant_id,
            payload={"slug": slug, "display_name": display_name},
        )
        record_event(
            session, tenant_id=tenant_id, event_type="user_created",
            actor_kind="system", subject_type="app_user", subject_id=admin_id,
            payload={"username": admin_username, "role": "admin"},
        )
        # 词表种子 = 配置/词表变更,敏感【config_change → sensitive】
        record_event(
            session, tenant_id=tenant_id, event_type="config_change",
            actor_kind="system", subject_type="vocabulary", subject_id=None,
            payload={
                "action": "seed_vocabulary",
                "vocab_versions": {"structure": vv_structure, "color": vv_color, "scene": vv_scene},
            },
        )
        record_event(
            session, tenant_id=tenant_id, event_type="config_change",
            actor_kind="system", subject_type="config_version", subject_id=config_id,
            payload={"action": "seed_config", "scope": "tagging", "prompt_version": prompt_version},
        )

        logger.info("租户 %s(%s)种子完成:user=%s config=%s。", tenant_id, slug, admin_id, config_id)
        return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="balloon-platform 参数化租户种子(可重放)")
    parser.add_argument("--tenant-id", type=int, required=True, help="租户号(0 保留,禁用)")
    parser.add_argument("--slug", required=True, help="租户 slug,如 demo_tenant")
    parser.add_argument("--display-name", required=True, help="展示名,如 示例客户")
    parser.add_argument("--admin-username", default=None, help="初始管理用户名;默认 admin@<slug>")
    parser.add_argument("--industry", default="balloon_party")
    parser.add_argument("--prompt-version", default="tagging_v2")
    parser.add_argument("--prompt-sha256", default=None, help="提示词内容 hash;骨架期可空")
    args = parser.parse_args()

    seeded = seed_tenant(
        args.tenant_id,
        args.slug,
        args.display_name,
        admin_username=args.admin_username,
        industry=args.industry,
        prompt_version=args.prompt_version,
        prompt_sha256=args.prompt_sha256,
    )
    print("SEEDED" if seeded else "SKIPPED(already exists)")


if __name__ == "__main__":
    main()
