"""demo 图库种子:**只入 demo_assets/library 合规素材**,并断言"素材数 = 合规库图数,一张不多"。

【P0】永不加载 69 张(C1)或任何非 demo_assets 素材。验收① 在此以代码断言兜底。
provider:DEMO_MOCK=1 或无 DASHSCOPE_API_KEY → ManifestProvider(确定性、零 token);否则真实 Qwen。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.context import tenant_context  # noqa: E402
from app.db import platform_session  # noqa: E402
from app.demo import DEMO_TENANT  # noqa: E402
from app.seed import seed_tenant  # noqa: E402
from app.tagging.execute import enqueue_tagging_task, run_batch  # noqa: E402
from app.tagging.knowledge import register_tagging_config  # noqa: E402

ASSETS = Path(os.environ.get("DEMO_ASSETS_DIR", "demo_assets"))
LIB = ASSETS / "library"


def _provider():
    from app.tagging.provider import ProviderConfigError, get_default_provider

    if os.environ.get("DEMO_MOCK", "").strip() in ("1", "true", "yes"):
        from app.demo.mock_provider import ManifestProvider
        return ManifestProvider.from_file(LIB / "manifest.json")
    try:
        return get_default_provider()
    except ProviderConfigError:
        from app.demo.mock_provider import ManifestProvider
        print("[demo-seed] 无 DASHSCOPE_API_KEY,回退 ManifestProvider(确定性)")
        return ManifestProvider.from_file(LIB / "manifest.json")


def main() -> None:
    pngs = sorted(p for p in LIB.glob("*.png"))
    if not pngs:
        raise SystemExit(f"未找到合规演示素材:先跑 `python scripts/gen_demo_assets.py`({LIB} 为空)")

    seed_tenant(DEMO_TENANT, "demo_tenant_demo", "演示租户")
    register_tagging_config(DEMO_TENANT)

    provider = _provider()
    with tenant_context(DEMO_TENANT):
        for p in pngs:
            from app.assets import ingest_asset
            r = ingest_asset(p.read_bytes(), mime_type="image/png", original_ext="png",
                             original_name=p.name)
            enqueue_tagging_task(r.asset_id, run_id="demo_seed")
        run_batch(provider)

    # 验收① 代码断言:demo 库素材数 == 合规库文件数,一张不多
    with platform_session(reason="demo-seed:verify-count") as s:
        n_assets = s.execute(
            text("SELECT count(*) FROM asset WHERE tenant_id=:t"), {"t": DEMO_TENANT}
        ).scalar_one()
    if n_assets != len(pngs):
        raise SystemExit(f"❌ 验收①失败:demo 资产数 {n_assets} ≠ 合规库图数 {len(pngs)}")
    print(f"✅ demo 图库种子完成:{n_assets} 张(= 合规库 {len(pngs)} 张,一张不多)")


if __name__ == "__main__":
    main()
