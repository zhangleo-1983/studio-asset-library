"""租户请求上下文。【不变量一】

租户中间件解析出的 tenant_id 存进 ContextVar,贯穿一次请求内的所有 DB 访问。
缺租户上下文 → get_current_tenant() 直接抛 NoTenantContext(不返回 None、不默认 0)。
这是应用层 tenant_id 过滤方案的安全网【加固3】:任何忘记设上下文的租户侧查询路径
在到达 DB 之前就失败,而不是静默漏掉租户过滤。
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator, Optional

# 默认 None = "无租户上下文";绝不用 0 或任何魔法值承载"无",避免误当平台保留号。
_tenant_id_var: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "balloon_tenant_id", default=None
)


class NoTenantContext(RuntimeError):
    """在没有租户上下文时试图做租户侧 DB 访问。【加固3 安全网】"""


def set_current_tenant(tenant_id: int) -> contextvars.Token:
    """设置当前租户,返回可用于回滚的 token。"""
    if tenant_id is None:
        raise ValueError("tenant_id 不能为 None;无租户请勿设置上下文")
    return _tenant_id_var.set(int(tenant_id))


def reset_current_tenant(token: contextvars.Token) -> None:
    _tenant_id_var.reset(token)


def current_tenant_or_none() -> Optional[int]:
    """只读窥视,不抛异常。中间件/日志用。"""
    return _tenant_id_var.get()


def get_current_tenant() -> int:
    """租户侧 DB 访问的强制入口:无上下文即拒绝。"""
    tenant_id = _tenant_id_var.get()
    if tenant_id is None:
        raise NoTenantContext(
            "当前无租户上下文;所有租户侧 DB 访问必须经租户中间件注入 tenant_id。"
            "跨租户/平台侧访问请显式走 platform_session(reason=...)。"
        )
    return tenant_id


@contextmanager
def tenant_context(tenant_id: int) -> Iterator[int]:
    """以某租户身份执行一段逻辑(测试与 worker 用;API 走中间件)。"""
    token = set_current_tenant(tenant_id)
    try:
        yield tenant_id
    finally:
        reset_current_tenant(token)
