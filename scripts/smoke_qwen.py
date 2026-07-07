"""真实 Qwen 冒烟(本地 .env,需 DASHSCOPE_API_KEY)。

对一张真实图跑完整闭环,打印可写进交付报告的三项:输入图 content_hash / run_id / 落库 tag 数。
CI **不** 跑本脚本(CI 全程 mock、无密钥)。

用法:
    export DASHSCOPE_API_KEY=...   # 或写进 .env
    export DATABASE_URL=postgresql+psycopg2://localhost:5432/balloon_platform
    python scripts/smoke_qwen.py --image /path/to/balloon.jpg --tenant 1
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.assets import ingest_asset  # noqa: E402
from app.context import tenant_context  # noqa: E402
from app.db import platform_session  # noqa: E402
from app.seed import seed_tenant  # noqa: E402
from app.tagging.execute import enqueue_tagging_task, run_batch  # noqa: E402
from app.tagging.knowledge import register_tagging_config  # noqa: E402
from app.tagging.provider import get_default_provider  # noqa: E402
from sqlalchemy import text  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--tenant", type=int, default=1)
    ap.add_argument("--slug", default="demo_tenant")
    args = ap.parse_args()

    ext = os.path.splitext(args.image)[1].lstrip(".").lower() or "jpg"
    content = open(args.image, "rb").read()

    seed_tenant(args.tenant, args.slug, args.slug)
    register_tagging_config(args.tenant)

    run_id = "smoke_" + os.path.basename(args.image)
    with tenant_context(args.tenant):
        r = ingest_asset(content, mime_type=f"image/{ext}", original_ext=ext,
                         original_name=os.path.basename(args.image))
        enqueue_tagging_task(r.asset_id, run_id=run_id)
        run_batch(get_default_provider())
        with platform_session(reason="smoke:count") as s:
            n = s.execute(
                text("SELECT count(*) FROM tag WHERE tenant_id=:t AND asset_id=:a"),
                {"t": args.tenant, "a": r.asset_id},
            ).scalar_one()

    print("=== 冒烟结果(写进交付报告)===")
    print(f"content_hash = {r.content_hash}")
    print(f"run_id       = {run_id}")
    print(f"asset_id     = {r.asset_id}")
    print(f"落库 tag 数  = {n}")


if __name__ == "__main__":
    main()
