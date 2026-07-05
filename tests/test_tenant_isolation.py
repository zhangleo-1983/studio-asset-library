"""集成测试①:无租户上下文的查询路径必须失败。【加固3 安全网】

应用层 tenant_id 过滤方案的唯一安全网:任何忘设租户上下文的租户侧查询,在到达 DB 前
就被 NoTenantContext 拒绝,而不是静默漏掉租户过滤跨租户返数据。
"""
from __future__ import annotations

import pytest

from app import repository
from app.context import NoTenantContext, tenant_context
from app.db import tenant_session


def test_query_without_tenant_context_is_rejected():
    # 没有任何租户上下文时调用租户侧仓储 → 直接拒绝
    with pytest.raises(NoTenantContext):
        repository.count_vocabulary()


def test_tenant_session_without_context_is_rejected():
    # 连会话都不该建出来
    with pytest.raises(NoTenantContext):
        with tenant_session():
            pass


def test_query_with_tenant_context_succeeds():
    # 有上下文即放行;tenant_id=0(平台保留号,迁移固化)存在、词表为空
    with tenant_context(0):
        assert repository.count_vocabulary() == 0
