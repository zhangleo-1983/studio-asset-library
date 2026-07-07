"""场景 1「审核员删除一条模型误打的标签」的代码级复现(scenario-walkthrough §场景1)。

纸面走查升级为可执行走查:打标 → 删错标 → correction/event 行断言 → 检索排除 → REMOVED 可分类。
"""
from __future__ import annotations

from sqlalchemy import text

from app import corrections, review
from app.assets import ingest_asset
from app.context import tenant_context
from app.db import platform_session
from app.seed import seed_tenant
from app.tagging.execute import enqueue_tagging_task, run_batch
from app.tagging.knowledge import register_tagging_config
from tests import fixtures as fx

# 模型对同一张图输出 structure=立柱 + 拱门;画面实际只有立柱,"拱门"是幻觉。
HALLUCINATION = {
    **fx.VALID,
    "structure_types": ["立柱", "拱门"],
    "color_scheme": {"primary": ["红"], "accent": [], "scheme_name": "红"},
    "theme": None,
    "scene_guess": "婚礼",
}


def test_scenario1_delete_hallucinated_tag():
    tid = 21
    seed_tenant(tid, "sc21", "场景一租户")
    register_tagging_config(tid)

    with tenant_context(tid):
        r = ingest_asset(fx.make_png_bytes(color=(10, 20, 30)), mime_type="image/png", original_ext="png")
        enqueue_tagging_task(r.asset_id, run_id="init_sc21")
        run_batch(fx.FakeProvider([fx.as_raw_text(HALLUCINATION)]))

        # 基线:structure 两行 active(column 真 + arch 幻觉)
        q_struct = review.review_queue("structure")  # noqa: F841 (触发一次读取,确保可查)

    with platform_session(reason="test:sc1-baseline") as s:
        struct = s.execute(
            text("SELECT tag_id, value, status FROM tag WHERE tenant_id=:t AND asset_id=:a "
                 "AND dimension='structure' ORDER BY value"),
            {"t": tid, "a": r.asset_id},
        ).all()
    by_value = {row[1]: {"tag_id": row[0], "status": row[2]} for row in struct}
    assert by_value["column"]["status"] == "active"
    assert by_value["arch"]["status"] == "active"
    arch_tag_id = by_value["arch"]["tag_id"]

    # 审核员删除幻觉标签 "拱门"(concept_key=arch)
    with tenant_context(tid):
        cid = corrections.remove_tag(arch_tag_id, corrected_by=1, reason="画面无拱门,模型幻觉")

    with platform_session(reason="test:sc1-after") as s:
        # tag 不 DELETE,status='removed',原值/溯源保留,current_correction_id 指向删标修正
        row = s.execute(
            text("SELECT status, value, current_correction_id FROM tag WHERE tag_id=:i"),
            {"i": arch_tag_id},
        ).first()
        assert row[0] == "removed" and row[1] == "arch" and row[2] == cid

        # tag_correction 新增一行 kind='remove'(old=arch, new=NULL, source=human, 带行为人)
        corr = s.execute(
            text("SELECT kind, old_value, new_value, source, corrected_by FROM tag_correction "
                 "WHERE correction_id=:i"),
            {"i": cid},
        ).first()
        assert corr == ("remove", "arch", None, "human", 1)

        # event 新增 correction 行(actor human/1,非敏感)
        ev = s.execute(
            text("SELECT actor_kind, actor_user_id, sensitive, payload FROM event "
                 "WHERE tenant_id=:t AND event_type='correction' AND subject_id=:i "
                 "ORDER BY event_id DESC LIMIT 1"),
            {"t": tid, "i": arch_tag_id},
        ).first()
        assert ev[0] == "human" and ev[1] == 1 and ev[2] is False
        assert ev[3]["kind"] == "remove"

        # 检索排除:找"造型=拱门(arch)"的 active 标签 → 0 行
        hit = s.execute(
            text("SELECT 1 FROM tag WHERE tenant_id=:t AND asset_id=:a "
                 "AND status='active' AND dimension='structure' AND value='arch'"),
            {"t": tid, "a": r.asset_id},
        ).first()
        assert hit is None
        # column 仍在
        still = s.execute(
            text("SELECT 1 FROM tag WHERE tenant_id=:t AND asset_id=:a "
                 "AND status='active' AND dimension='structure' AND value='column'"),
            {"t": tid, "a": r.asset_id},
        ).first()
        assert still is not None

    # sync_corrections 视角:可稳定归类为 REMOVED(读 tag.status='removed',当前 active 无替代)
    with platform_session(reason="test:sc1-removed-class") as s:
        removed = s.execute(
            text("SELECT count(*) FROM tag WHERE tenant_id=:t AND asset_id=:a "
                 "AND dimension='structure' AND status='removed'"),
            {"t": tid, "a": r.asset_id},
        ).scalar_one()
    assert removed == 1  # 【N4】原始值 arch 安然在 tag.value,回流可复现分类
