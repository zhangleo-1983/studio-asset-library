"""demo 单页 web 服务(销售样板间)。5 端点,hardcode tenant=1,无鉴权。

链路:上传客户图 → AI 拆四维标签 → 演示图库召回同款 → 一键导出方案页。
断网兜底【验收④】:DEMO_FORCE_OFFLINE=1 或真实调用失败 → 用预打标缓存的样本结果继续演示,
不 dead-air;返回 degraded=true,前端标"演示缓存模式"。

复用平台既有函数:app.assets.ingest_asset / app.tagging.execute.process_task / normalize / active_config。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.context import tenant_context
from app.db import tenant_session
from app.demo import DEMO_TENANT
from app.demo.display import asset_up_tags, four_dim_view
from app.demo.export import render_plan_page
from app.demo.mock_provider import ManifestProvider
from app.demo.recall import UpTag, recall_similar
from app.storage import get_storage_backend

_STATIC = Path(__file__).resolve().parent / "static"
_DEMO_ASSETS = Path(os.environ.get("DEMO_ASSETS_DIR", "demo_assets"))
_FALLBACK = _DEMO_ASSETS / "fallback"


def _offline() -> bool:
    return os.environ.get("DEMO_FORCE_OFFLINE", "").strip() in ("1", "true", "yes")


def _live_provider():
    """上传图的实时打标 provider。DEMO_MOCK=1 → ManifestProvider(确定性、零 token,
    含 library+fallback 两份 manifest);否则真实 Qwen;无密钥则 None(触发兜底)。"""
    if os.environ.get("DEMO_MOCK", "").strip() in ("1", "true", "yes"):
        import json as _json

        from app.demo.mock_provider import ManifestProvider
        merged: dict = {}
        for mf in (_DEMO_ASSETS / "library" / "manifest.json",
                   _FALLBACK / "manifest.json"):
            if mf.exists():
                merged.update(_json.loads(mf.read_text(encoding="utf-8")))
        return ManifestProvider(merged)
    from app.tagging.provider import ProviderConfigError, get_default_provider

    try:
        return get_default_provider()
    except ProviderConfigError:
        return None


def _fallback_tags() -> list[UpTag]:
    """预打标缓存:兜底样本的四维标签(断网时用)。"""
    manifest = json.loads((_FALLBACK / "fallback_tags.json").read_text(encoding="utf-8"))
    return [UpTag(dimension=t["dimension"], value=t["value"], role=t.get("role")) for t in manifest]


def create_demo_app() -> FastAPI:
    app = FastAPI(title="接单响应神器 · demo", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (_STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/image/{asset_id}")
    def image(asset_id: int):
        with tenant_context(DEMO_TENANT), tenant_session() as s:
            row = s.execute(
                _sql("SELECT storage_key, mime_type FROM asset WHERE asset_id=:a AND tenant_id=:t"),
                {"a": asset_id, "t": DEMO_TENANT},
            ).first()
        if row is None:
            return Response(status_code=404)
        ext = row[0].rsplit(".", 1)[-1] if "." in row[0] else "png"
        obj = get_storage_backend().get(DEMO_TENANT, asset_id, original_ext=ext)
        return Response(content=obj.content, media_type=row[1] or "image/png")

    @app.post("/upload")
    async def upload(file: UploadFile):
        content = await file.read()
        ext = (file.filename or "x.png").rsplit(".", 1)[-1].lower()
        degraded = False
        with tenant_context(DEMO_TENANT):
            from app.assets import ingest_asset
            r = ingest_asset(content, mime_type=file.content_type or "image/png", original_ext=ext,
                             original_name=file.filename)
            # 已在库(去重/恢复)且已有标签:直接复用,不重打(避免重复标签;客户重发库内图也稳)
            existing = []
            if r.outcome != "created":
                with tenant_session() as s0:
                    existing = asset_up_tags(s0, DEMO_TENANT, r.asset_id)
            provider = None if _offline() else _live_provider()
            if existing:
                up = existing
            elif provider is None:
                degraded = True  # 断网兜底:不 live 打标,用预打标缓存标签
                up = _fallback_tags()
            else:
                from app.tagging.execute import TaggingFailure, enqueue_tagging_task, process_task
                task_id = enqueue_tagging_task(r.asset_id, run_id="demo_upload")
                try:
                    with tenant_session() as s2:
                        # 认领并同步处理(demo 不起 worker)
                        s2.execute(_sql("UPDATE task SET status='running' WHERE task_id=:i AND tenant_id=:t"),
                                   {"i": task_id, "t": DEMO_TENANT})
                        process_task(s2, task_id, provider)
                    with tenant_session() as s3:
                        up = asset_up_tags(s3, DEMO_TENANT, r.asset_id)
                except (TaggingFailure, Exception):
                    degraded = True  # 实时失败也走兜底
                    up = _fallback_tags()
            with tenant_session() as s4:
                view = four_dim_view(s4, DEMO_TENANT, up)
                hits = recall_similar(s4, DEMO_TENANT, up, exclude_asset_id=r.asset_id, limit=6)
        return JSONResponse({
            "asset_id": r.asset_id,
            "degraded": degraded,
            "tags": view,
            "similar": [h.asset_id for h in hits],
        })

    @app.get("/similar/{asset_id}")
    def similar(asset_id: int, limit: int = 6):
        with tenant_context(DEMO_TENANT), tenant_session() as s:
            up = asset_up_tags(s, DEMO_TENANT, asset_id)
            hits = recall_similar(s, DEMO_TENANT, up, exclude_asset_id=asset_id, limit=limit)
        return JSONResponse({"similar": [h.asset_id for h in hits]})

    @app.get("/export/{asset_id}", response_class=HTMLResponse)
    def export(asset_id: int, similar: Optional[str] = None):
        with tenant_context(DEMO_TENANT), tenant_session() as s:
            up = asset_up_tags(s, DEMO_TENANT, asset_id)
            view = four_dim_view(s, DEMO_TENANT, up)
            if similar:
                sim_ids = [int(x) for x in similar.split(",") if x.strip().isdigit()]
            else:
                sim_ids = [h.asset_id for h in recall_similar(s, DEMO_TENANT, up, exclude_asset_id=asset_id)]
        return render_plan_page(uploaded_asset_id=asset_id, view=view, similar_asset_ids=sim_ids)

    return app


def _sql(q: str):
    from sqlalchemy import text
    return text(q)


app = create_demo_app()
