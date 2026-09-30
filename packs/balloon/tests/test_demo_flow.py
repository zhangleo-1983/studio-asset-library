"""演示链路(用示例包):素材入库 → 打标 → 上传新图 → 标签召回相似案例 → 导出方案页。

用 ManifestProvider(确定性,不调真实模型)驱动真实的入库/打标/落标签/召回/导出代码。
用独立租户号,不与其它测试争用租户 1。
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.demo as demo_pkg
from app.assets import ingest_asset
from app.context import tenant_context
from app.db import platform_session
from app.packs import get_pack
from app.seed import seed_tenant
from app.tagging.execute import enqueue_tagging_task, run_batch
from app.tagging.knowledge import register_tagging_config

T = 88


def test_upload_recall_and_export(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    monkeypatch.setenv("DEMO_ASSETS_DIR", str(assets))
    monkeypatch.setenv("DEMO_MOCK", "1")
    monkeypatch.setattr(demo_pkg, "DEMO_TENANT", T)

    # 1) 生成演示素材(离线、确定性)
    gen = get_pack().demo_generator_path()
    subprocess.run([sys.executable, str(gen)], env={**os.environ, "DEMO_ASSETS_DIR": str(assets)}, check=True,
                   capture_output=True)
    lib = sorted((assets / "library").glob("*.png"))
    assert len(lib) == 12

    # 2) 入库并打标(确定性 provider)
    from app.demo.mock_provider import ManifestProvider

    seed_tenant(T, "demo_flow", "demo flow")
    register_tagging_config(T)
    with tenant_context(T):
        for p in lib:
            r = ingest_asset(p.read_bytes(), mime_type="image/png", original_ext="png", original_name=p.name)
            enqueue_tagging_task(r.asset_id, run_id="demo_flow")
        run_batch(ManifestProvider.from_file(assets / "library" / "manifest.json"))

    # 3) 上传"新图"(断网兜底样本:同款造型+配色+场景的库内图应排第一)
    import app.demo.server as server

    server = importlib.reload(server)
    client = TestClient(server.create_demo_app())
    sample = (assets / "fallback" / "sample.png").read_bytes()
    body = client.post("/upload", files={"file": ("sample.png", sample, "image/png")}).json()
    assert body["degraded"] is False and body["similar"]

    fields = {f["label"]: f for f in body["tags"]["fields"]}
    assert [i["text"] for i in fields["造型"]["items"]] == ["拱门"]
    assert {i["text"] for i in fields["配色"]["items"]} >= {"红", "金"}

    with platform_session(reason="test:demo-flow-top-hit") as s:
        top = s.execute(text("SELECT original_name FROM asset WHERE asset_id=:a AND tenant_id=:t"),
                        {"a": body["similar"][0], "t": T}).scalar_one()
    assert top == "lib_拱门_红金_婚礼.png"

    # 4) 导出方案页:单文件 HTML,含维度视图与召回案例图
    page = client.get(f"/export/{body['asset_id']}").text
    assert get_pack().ui["plan"]["heading"] in page
    assert "拱门" in page and f"/image/{body['similar'][0]}" in page
