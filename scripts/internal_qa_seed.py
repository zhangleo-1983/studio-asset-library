"""内部打标质量目测集(69 张 C1)—— **与 demo 完全隔离**。

红线(备忘录 v1.1 §八 + 评审 P0):C1 疑似示例客户系素材,对外禁用。本脚本:
  · 强制独立库(DATABASE_URL 必须含 'internal_qa',否则拒跑)——**永不写 demo 实例**;
  · 图片留在 <LOCAL_IMAGE_DIR> 原地,产物永不入仓(demo_assets/ 只装合规素材);
  · 仅供内部打标准确率目测,结果不得对外展示/传播。
用法:
  createdb balloon_internal_qa
  DATABASE_URL=postgresql+psycopg2://localhost:5432/balloon_internal_qa \
    python scripts/internal_qa_seed.py --dir <LOCAL_IMAGE_DIR>
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    db = os.environ.get("DATABASE_URL", "")
    if "internal_qa" not in db:
        raise SystemExit(
            "拒绝执行:DATABASE_URL 必须指向独立的 internal_qa 库(红线:C1 永不进 demo 实例)。\n"
            "例:DATABASE_URL=postgresql+psycopg2://localhost:5432/balloon_internal_qa"
        )
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="内部图目录(如 <LOCAL_IMAGE_DIR>),留原地不入仓")
    ap.add_argument("--limit", type=int, default=0, help="限量,0=全部")
    args = ap.parse_args()

    from app.context import tenant_context
    from app.seed import seed_tenant
    from app.tagging.execute import enqueue_tagging_task, run_batch
    from app.tagging.knowledge import register_tagging_config
    from app.tagging.provider import get_default_provider  # 真实 Qwen,目测准确率必须真打

    root = Path(os.path.expanduser(args.dir))
    imgs = sorted(p for p in root.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if args.limit:
        imgs = imgs[: args.limit]
    print(f"[internal-qa] {len(imgs)} 张 → 独立库({db.rsplit('/', 1)[-1]}),真实 Qwen 打标")

    seed_tenant(1, "internal_qa", "内部QA")
    register_tagging_config(1)
    with tenant_context(1):
        from app.assets import ingest_asset
        for p in imgs:
            ext = p.suffix.lstrip(".").lower()
            r = ingest_asset(p.read_bytes(), mime_type=f"image/{ext}", original_ext=ext, original_name=p.name)
            enqueue_tagging_task(r.asset_id, run_id="internal_qa")
        run_batch(get_default_provider())
    print("[internal-qa] 完成。仅供内部目测;结果与图片均不得对外展示/传播/入仓。")


if __name__ == "__main__":
    main()
