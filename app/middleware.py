"""租户中间件(骨架)。【不变量一】

职责:从请求解析出 tenant_id,注入请求上下文,请求结束后清理。
本期只立骨架 —— tenant_id 来源用占位:Web 端应取自登录会话所属租户,小程序端取自
绑定租户;这里先从 `X-Tenant-Id` 头读取(账号体系属隔断墙,后续替换)。

不在中间件里"拒绝无租户请求":拒绝的承重点在 DB 层(tenant_session → NoTenantContext),
这样健康检查等公共路由可无租户放行,而任何租户侧数据访问缺上下文必然失败【加固3】。
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.context import reset_current_tenant, set_current_tenant


class TenantMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str = "X-Tenant-Id") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        raw = request.headers.get(self.header_name)
        token = None
        if raw is not None and raw.strip():
            try:
                token = set_current_tenant(int(raw))
            except ValueError:
                # 非法 tenant 头:不设上下文,交由下游 DB 层拒绝(不静默默认)。
                token = None
        try:
            return await call_next(request)
        finally:
            if token is not None:
                reset_current_tenant(token)
