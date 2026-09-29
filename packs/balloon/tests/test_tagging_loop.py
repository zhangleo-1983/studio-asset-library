"""打标闭环端到端(mock provider):上传→入库→打标→落 tag→复核→修正。

覆盖:归一化(词表内/别名/词表外 unresolved)、coerce 兜底(theme 对象、裸字符串)、
溯源六项(裁决八按维度)、去重恢复【Q3】、复核队列、四类修正、失败落 task。
"""
from __future__ import annotations

from sqlalchemy import text

from app import corrections, review
from app.assets import ingest_asset, soft_delete_asset
from app.context import tenant_context
from app.db import platform_session, tenant_session
from app.seed import seed_tenant
from app.tagging.execute import enqueue_tagging_task, process_task, run_batch
from app.tagging.knowledge import register_tagging_config
from tests import fixtures as fx

import samples


def _setup_tenant(tid: int, slug: str) -> None:
    seed_tenant(tid, slug, slug)
    register_tagging_config(tid)


def _tags(tid: int, asset_id: int, dimension: str | None = None):
    with platform_session(reason="test:read-tags") as s:
        rows = s.execute(
            text(
                "SELECT dimension, value, role, status, source, vocab_version_id, "
                "model_id, config_version_id, run_id, input_hash "
                "FROM tag WHERE tenant_id=:t AND asset_id=:a "
                "AND (:d IS NULL OR dimension=:d) ORDER BY dimension, value"
            ),
            {"t": tid, "a": asset_id, "d": dimension},
        ).all()
    return rows


def test_happy_path_full_loop():
    tid = 11
    _setup_tenant(tid, "loop11")
    img = fx.make_png_bytes()
    with tenant_context(tid):
        r = ingest_asset(img, mime_type="image/png", original_ext="png", original_name="a.png")
        assert r.outcome == "created"
        # 去重:同图再传 → 跳过
        assert ingest_asset(img, mime_type="image/png", original_ext="png").outcome == "skipped_dup"
        task_id = enqueue_tagging_task(r.asset_id, run_id="run_11")
        n = run_batch(fx.FakeProvider([fx.as_raw_text(samples.VALID, wrap_prose=True)]))
    assert n == 1

    rows = _tags(tid, r.asset_id)
    # 断言各维落库形态
    flat = {(d, v, role, status) for (d, v, role, status, src, vv, *_ ) in rows}
    assert ("structure", "column", None, "active") in flat
    assert ("structure", "arch", None, "active") in flat
    assert ("color", "red", "primary", "active") in flat
    assert ("color", "gold", "primary", "active") in flat
    assert ("color", "white", "accent", "active") in flat
    assert ("scene", "wedding", None, "active") in flat
    assert ("theme", "爱心", None, "active") in flat        # 自由文本,原词形
    assert ("color_scheme", "红金", None, "active") in flat  # 自由文本

    # 溯源(裁决八按维度):受约束维 vocab_version_id 非空,自由文本维为空;其余五项全非空
    for (d, v, role, status, src, vv, model_id, cfg, run_id, ih) in rows:
        assert src == "model"
        assert model_id and cfg and run_id and ih  # 五项
        if d in ("structure", "color", "scene"):
            assert vv is not None
        else:
            assert vv is None

    # task.output 原样保留 + token 累计
    with platform_session(reason="test:task") as s:
        trow = s.execute(
            text("SELECT status, output, input_tokens, output_tokens, model_id FROM task WHERE task_id=:i"),
            {"i": task_id},
        ).first()
    assert trow[0] == "done"
    # 【P2-3】output = {_raw_text(全文), parsed(对象)};parsed 保留原始中文,未被 concept_key 覆盖
    assert trow[1]["parsed"]["structure_types"] == ["立柱", "拱门"]
    assert "_raw_text" in trow[1] and "爱心" in trow[1]["_raw_text"]
    assert trow[2] == 100 and trow[3] == 50 and trow[4] == "qwen-vl-max"


def test_coerce_variants_do_not_break():
    tid = 12
    _setup_tenant(tid, "loop12")
    for i, (variant, expect_theme) in enumerate([(samples.THEME_AS_OBJECT, "爱心"), (samples.BARE_STRINGS, "爱心")]):
        with tenant_context(tid):
            r = ingest_asset(fx.make_png_bytes(color=(1, 2, 100 + i)),  # 每变体一张不同图,避免去重
                             mime_type="image/png", original_ext="png")
            enqueue_tagging_task(r.asset_id, run_id="run_12")
            run_batch(fx.FakeProvider([fx.as_raw_text(variant)]))
        theme = [v for (d, v, *_ ) in _tags(tid, r.asset_id) if d == "theme"]
        assert theme == [expect_theme]
    # BARE_STRINGS 的 structure "立柱" 仍被正常解析为 column
    # (最后一个 asset 是 BARE_STRINGS)
    structs = [v for (d, v, *_ ) in _tags(tid, r.asset_id, "structure")]
    assert structs == ["column"]


def test_out_of_vocab_becomes_unresolved_and_enters_review():
    tid = 13
    _setup_tenant(tid, "loop13")
    with tenant_context(tid):
        r = ingest_asset(fx.make_png_bytes(color=(9, 9, 9)), mime_type="image/png", original_ext="png")
        enqueue_tagging_task(r.asset_id, run_id="run_13")
        run_batch(fx.FakeProvider([fx.as_raw_text(samples.OUT_OF_VOCAB)]))
        q = review.review_queue(dimension="structure")
    struct = _tags(tid, r.asset_id, "structure")
    assert ("structure", "背景墙", None, "unresolved") in {(d, v, role, st) for (d, v, role, st, *_ ) in struct}
    # 复核队列默认含 unresolved
    assert any(item.value == "背景墙" and item.status == "unresolved" for item in q)


def test_alias_hit_resolves_to_concept_key():
    tid = 14
    _setup_tenant(tid, "loop14")
    with tenant_context(tid):
        r = ingest_asset(fx.make_png_bytes(color=(7, 7, 7)), mime_type="image/png", original_ext="png")
        enqueue_tagging_task(r.asset_id, run_id="run_14")
        run_batch(fx.FakeProvider([fx.as_raw_text(samples.ALIAS_HIT)]))
    structs = {v for (d, v, *_ ) in _tags(tid, r.asset_id, "structure")}
    assert "flowerbox" in structs  # 气球花盒 → flowerbox(经 alias_map)


def test_provider_failure_marks_task_failed():
    tid = 15
    _setup_tenant(tid, "loop15")
    with tenant_context(tid):
        r = ingest_asset(fx.make_png_bytes(color=(3, 3, 3)), mime_type="image/png", original_ext="png")
        task_id = enqueue_tagging_task(r.asset_id, run_id="run_15")
        run_batch(fx.RaisingProvider())
    with platform_session(reason="test:failed") as s:
        st = s.execute(text("SELECT status, retry_count FROM task WHERE task_id=:i"), {"i": task_id}).first()
    assert st[0] == "failed" and st[1] >= 1


def test_dedup_restore_after_soft_delete():
    tid = 16
    _setup_tenant(tid, "loop16")
    img = fx.make_png_bytes(color=(5, 6, 7))
    with tenant_context(tid):
        r1 = ingest_asset(img, mime_type="image/png", original_ext="png")
        soft_delete_asset(r1.asset_id, deleted_by=1)
        r2 = ingest_asset(img, mime_type="image/png", original_ext="png")  # 命中软删 → 恢复
    assert r2.asset_id == r1.asset_id and r2.outcome == "restored"


def test_manual_corrections_add_update_remove_restore():
    tid = 17
    _setup_tenant(tid, "loop17")
    with tenant_context(tid):
        r = ingest_asset(fx.make_png_bytes(color=(2, 4, 6)), mime_type="image/png", original_ext="png")
        enqueue_tagging_task(r.asset_id, run_id="run_17")
        run_batch(fx.FakeProvider([fx.as_raw_text(samples.OUT_OF_VOCAB)]))
        # update:unresolved 背景墙 → 转正(此处沿用现有 concept_key column 作示例)
        unresolved = [i for i in review.review_queue("structure") if i.status == "unresolved"][0]
        corrections.update_tag(unresolved.tag_id, "column", corrected_by=1, reason="归类为立柱")
        # add:human 补一个 color 主色(role 必填)
        color_tag = corrections.add_tag(r.asset_id, "color", "red", added_by=1, role="primary")
        # remove + restore
        corrections.remove_tag(color_tag, corrected_by=1, reason="补错了")
        corrections.restore_tag(color_tag, corrected_by=1)

    with platform_session(reason="test:corrections") as s:
        # unresolved 已转 active、值为 column
        st = s.execute(text("SELECT status, value FROM tag WHERE tag_id=:i"), {"i": unresolved.tag_id}).first()
        assert st[0] == "active" and st[1] == "column"
        # 修正链留痕:update 一条 + remove/restore 各一条
        kinds = s.execute(
            text("SELECT kind FROM tag_correction WHERE tenant_id=:t ORDER BY correction_id"),
            {"t": tid},
        ).scalars().all()
        assert "update" in kinds and "remove" in kinds and "restore" in kinds
        # human 补的受约束维标签记了 vocab_version_id【N11】
        vv = s.execute(text("SELECT vocab_version_id FROM tag WHERE tag_id=:i"), {"i": color_tag}).scalar_one()
        assert vv is not None
