"""R03 返修守卫测试(P2-7):人工路径闸门 / 状态机 / 跨租户指针 / ParseError 保全。"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import corrections
from app.active_config import CrossTenantConfigError, activate_config, current_config
from app.assets import ingest_asset
from app.context import tenant_context
from app.corrections import CorrectionError
from app.db import platform_session, tenant_session
from app.seed import seed_tenant
from app.tagging.execute import enqueue_tagging_task, run_batch
from app.tagging.knowledge import register_tagging_config
from tests import fixtures as fx

import samples


def _tag_one(tid: int, slug: str) -> tuple[int, dict[str, int]]:
    """建租户、打一张(VALID)、返回 asset_id 与 {value: tag_id}。"""
    seed_tenant(tid, slug, slug)
    register_tagging_config(tid)
    with tenant_context(tid):
        r = ingest_asset(fx.make_png_bytes(color=(tid % 256, 1, 2)), mime_type="image/png", original_ext="png")
        enqueue_tagging_task(r.asset_id, run_id=f"run_{tid}")
        run_batch(fx.FakeProvider([fx.as_raw_text(samples.VALID)]))
    with platform_session(reason="test:map") as s:
        rows = s.execute(
            text("SELECT value, tag_id FROM tag WHERE tenant_id=:t AND asset_id=:a"),
            {"t": tid, "a": r.asset_id},
        ).all()
    return r.asset_id, {row[0]: int(row[1]) for row in rows}


# ── P1-1 归一化闸门 ──────────────────────────────────────────────
def test_update_rejects_illegal_concept_key():
    _, m = _tag_one(31, "g31")
    with tenant_context(31):
        with pytest.raises(CorrectionError):
            corrections.update_tag(m["column"], "flowerbux", corrected_by=1)  # 拼错,不在册


def test_add_rejects_illegal_concept_and_missing_role():
    asset_id, _ = _tag_one(32, "g32")
    with tenant_context(32):
        with pytest.raises(CorrectionError):  # 词表外概念键
            corrections.add_tag(asset_id, "structure", "backdropp", added_by=1)
        with pytest.raises(CorrectionError):  # color 维缺 role
            corrections.add_tag(asset_id, "color", "red", added_by=1)
        # 合法补标:color + role 通过
        assert corrections.add_tag(asset_id, "color", "red", added_by=1, role="accent") > 0


# ── P1-2 状态机守卫 ──────────────────────────────────────────────
def test_state_machine_guards():
    _, m = _tag_one(33, "g33")
    with tenant_context(33):
        # remove 后 update 应拒绝(不隐式复活)
        corrections.remove_tag(m["arch"], corrected_by=1)
        with pytest.raises(CorrectionError):
            corrections.update_tag(m["arch"], "column", corrected_by=1)
        # restore 只允许 removed:对 active 标签 restore 应拒绝
        with pytest.raises(CorrectionError):
            corrections.restore_tag(m["column"], corrected_by=1)
        # removed 可 restore
        assert corrections.restore_tag(m["arch"], corrected_by=1) > 0


# ── P1-3 跨租户生效指针 ──────────────────────────────────────────
def test_activate_config_rejects_cross_tenant_config():
    seed_tenant(41, "g41", "g41")
    seed_tenant(42, "g42", "g42")
    with platform_session(reason="test:xtenant-cfg") as s:
        cfg_b = current_config(s, 42, "tagging")["config_version_id"]
        # 把租户 42 的配置激活到租户 41 → 应用层拒绝
        with pytest.raises(CrossTenantConfigError):
            activate_config(s, tenant_id=41, scope="tagging", config_version_id=cfg_b, actor_kind="system")


def test_activate_config_rejects_cross_tenant_vocab_versions():
    seed_tenant(43, "g43", "g43")
    seed_tenant(44, "g44", "g44")
    with platform_session(reason="test:xtenant-vocab") as s:
        # 租户 44 的 structure 版本号
        vv_b = s.execute(
            text("SELECT vocab_version_id FROM vocabulary_version WHERE tenant_id=44 AND dimension='structure'")
        ).scalar_one()
        # 给租户 43 造一个 payload 指向租户 44 版本的配置行
        bad_cfg = int(s.execute(
            text("INSERT INTO config_version (tenant_id, scope, payload, prompt_version) "
                 "VALUES (43,'tagging', CAST(:p AS JSONB),'tagging_v2') RETURNING config_version_id"),
            {"p": json.dumps({"vocab_versions": {"structure": vv_b}})},
        ).scalar_one())
        with pytest.raises(CrossTenantConfigError):
            activate_config(s, tenant_id=43, scope="tagging", config_version_id=bad_cfg, actor_kind="system")


def test_db_composite_fk_blocks_cross_tenant_pointer():
    seed_tenant(45, "g45", "g45")
    seed_tenant(46, "g46", "g46")
    with platform_session(reason="test:db-fk-read") as s:
        cfg_b = current_config(s, 46, "tagging")["config_version_id"]
    # 直接 INSERT 绕过应用层 → 复合外键(0004)在库层拦截。整个会话包在 raises 内,
    # 让异常经 platform_session.__exit__ 正常回滚(不在 aborted 事务上再 commit)。
    with pytest.raises(IntegrityError):
        with platform_session(reason="test:db-fk") as s:
            s.execute(
                text("INSERT INTO active_config (tenant_id, scope, config_version_id) "
                     "VALUES (45,'other',:c)"),
                {"c": cfg_b},
            )


# ── ParseError 分支:原始全文保全 ────────────────────────────────
def test_parse_error_preserves_raw_text_and_marks_failed():
    seed_tenant(47, "g47", "g47")
    register_tagging_config(47)
    with tenant_context(47):
        r = ingest_asset(fx.make_png_bytes(color=(47, 47, 47)), mime_type="image/png", original_ext="png")
        task_id = enqueue_tagging_task(r.asset_id, run_id="run_47")
        run_batch(fx.FakeProvider(["这不是 JSON,只是模型的一段废话"]))
    with platform_session(reason="test:parse-fail") as s:
        row = s.execute(
            text("SELECT status, output FROM task WHERE task_id=:i"), {"i": task_id}
        ).first()
    assert row[0] == "failed"
    assert row[1]["_raw_text"] == "这不是 JSON,只是模型的一段废话"  # 原文保全,未静默丢
