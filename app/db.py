"""数据库引擎与会话。

两条取会话的路径,泾渭分明:

- tenant_session():  租户侧唯一入口。进门先 get_current_tenant() —— 缺租户上下文
                     直接拒绝【加固3】。所有 API/仓储层的租户数据访问只走这条。
- platform_session(reason): 平台侧/运维脚本入口,独立于租户中间件,用于跨租户聚合
                     (查询③ C5)与建租户种子(migration §4 步骤 0)等无单一租户归属的
                     操作。宪法要求"跨租户访问必须显式声明"——故强制传 reason。

会话内额外 set_config('app.tenant_id', ...) 为将来 RLS 留位(本期不启用)。
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.context import get_current_tenant


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url, future=True, pool_pre_ping=True)


@lru_cache
def _get_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), future=True, expire_on_commit=False)


@contextmanager
def tenant_session() -> Iterator[Session]:
    """租户侧会话:缺租户上下文即 NoTenantContext,连接都不建。"""
    tenant_id = get_current_tenant()  # ← 安全网:无上下文在此抛出【加固3】
    session: Session = _get_sessionmaker()()
    # RLS 留位:会话级注入当前租户(本期不建 RLS 策略,仅埋点)。
    session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def platform_session(reason: str) -> Iterator[Session]:
    """平台侧会话:显式声明用途(reason),绕过租户中间件。

    仅限:建租户种子、跨租户平台聚合等无单一租户归属的操作。调用点自证授权。

    【裁决九】跨租户访问口径二分(见 architecture §3.1):
    ① 只读基础设施扫描(worker 轮询 pending、健康检查):reason 声明即可、日志留痕,不落 event;
    ② 数据性跨租户聚合/导出(查询③计量等,触碰业务数据并对外产出):必须落 sensitive 事件
       (tenant_id=0),一次调用一条。拿不准按 ②。
    """
    if not reason or not reason.strip():
        raise ValueError("platform_session 必须显式声明 reason(宪法:跨租户访问显式声明)")
    session: Session = _get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
