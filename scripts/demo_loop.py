"""一键打标闭环演示(mock provider,无需真实密钥)。

对一张现造样例图,完整跑通:上传→入库→打标(mock)→落 tag→复核队列可查→修正闭环。
用法:先 alembic upgrade head,再 `python scripts/demo_loop.py`(见 Makefile `demo` 目标)。
真实 Qwen 冒烟见 scripts/smoke_qwen.py。
"""
from __future__ import annotations

import io
import json
import os
import sys

# 允许从仓库根直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import corrections, review  # noqa: E402
from app.assets import ingest_asset  # noqa: E402
from app.context import tenant_context  # noqa: E402
from app.seed import seed_tenant  # noqa: E402
from app.tagging.execute import enqueue_tagging_task, run_batch  # noqa: E402
from app.tagging.knowledge import register_tagging_config  # noqa: E402
from app.tagging.provider import CallResult, TaggingProvider  # noqa: E402

DEMO_TENANT = int(os.environ.get("DEMO_TENANT_ID", "99"))

CANNED_OUTPUT = {
    "image_id": "demo",
    "theme": "爱心",
    "theme_type": "通用元素",
    "color_scheme": {"primary": ["红", "金"], "accent": ["白"], "scheme_name": "红金"},
    "structure_types": ["立柱", "气球花盒", "背景墙"],  # 立柱=词表内;气球花盒=别名;背景墙=词表外→unresolved
    "scene_guess": "婚礼",
    "suggested_filename": "爱心主题红金配色婚礼立柱",
    "confidence": 0.55,
    "needs_review": False,
    "notes": "",
}


class DemoProvider(TaggingProvider):
    model_id = "qwen-vl-max"

    def call(self, image_bytes: bytes, prompt_text: str) -> CallResult:
        return CallResult(text=json.dumps(CANNED_OUTPUT, ensure_ascii=False),
                          input_tokens=120, output_tokens=60, latency_ms=10, retries=0)


def _png(color) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(buf, format="PNG")
    return buf.getvalue()


def main() -> None:
    print(f"== 打标闭环演示(tenant={DEMO_TENANT},mock provider)==")
    seed_tenant(DEMO_TENANT, f"demo{DEMO_TENANT}", "演示租户")
    cfg_id = register_tagging_config(DEMO_TENANT)
    print(f"[知识] 当期 tagging 配置 config_version_id={cfg_id}(含 prompt_sha256)")

    color = tuple(os.urandom(3))  # 每次运行一张新图,避免去重跳过
    with tenant_context(DEMO_TENANT):
        r = ingest_asset(_png(color), mime_type="image/png", original_ext="png", original_name="demo.png")
        print(f"[入库] asset_id={r.asset_id} outcome={r.outcome} hash={r.content_hash[:12]}…")

        task_id = enqueue_tagging_task(r.asset_id, run_id="demo_run")
        n = run_batch(DemoProvider())
        print(f"[打标] task_id={task_id} 处理 {n} 条任务")

        print("[落 tag] 复核队列(confidence<阈值 / needs_review / unresolved):")
        for it in review.review_queue():
            print(f"    - tag={it.tag_id} {it.dimension}={it.value} status={it.status} conf={it.confidence}")

        # 修正闭环:把 unresolved 的"背景墙"人工归类(此处示范转正为已有 concept_key)
        unresolved = [i for i in review.review_queue("structure") if i.status == "unresolved"]
        if unresolved:
            cid = corrections.update_tag(unresolved[0].tag_id, "column", corrected_by=1, reason="演示:归类为立柱")
            print(f"[修正] unresolved tag={unresolved[0].tag_id} → column(correction_id={cid},status 迁回 active)")

    print("== 闭环完成:上传→入库→打标→落 tag→复核→修正 全绿 ==")


if __name__ == "__main__":
    main()
