"""FastAPI 应用入口(api)。

与 worker 同镜像、不同入口(见 docker-compose)。本期只挂租户中间件 + 健康检查,
不实现任何打标/两端业务路由(隔断墙,授权粗糙但本阶段一行不写)。
"""
from __future__ import annotations

from fastapi import FastAPI

from app.context import current_tenant_or_none
from app.middleware import TenantMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="balloon-platform", version="0.1.0")
    app.add_middleware(TenantMiddleware)

    @app.get("/healthz")
    def healthz() -> dict:
        # 公共路由:无需租户上下文。
        return {"status": "ok"}

    @app.get("/whoami")
    def whoami() -> dict:
        # 诊断用:回显当前解析到的租户(可能为 None = 无上下文)。
        return {"tenant_id": current_tenant_or_none()}

    return app


app = create_app()
