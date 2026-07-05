"""测试夹具:建一个干净的测试库并跑 alembic 迁移到 head。

需要本机可连的 PostgreSQL(compose 里是 postgres 服务;本地开发用本机 PG)。
连接串默认 localhost:5432,可用 TEST_ADMIN_URL / TEST_DB 覆盖。
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ADMIN_URL = os.environ.get(
    "TEST_ADMIN_URL", "postgresql+psycopg2://localhost:5432/postgres"
)
TEST_DB = os.environ.get("TEST_DB", "balloon_platform_test")
# 从 ADMIN_URL 派生测试库 URL:沿用同一 host/端口/**凭据**,只换库名。
# 本地默认无凭据(peer/trust);CI 的 postgres service 需 user:pass,经 TEST_ADMIN_URL 带入。
TEST_URL = make_url(ADMIN_URL).set(database=TEST_DB).render_as_string(hide_password=False)


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    # 1) 重建测试库(连到维护库 postgres,autocommit)
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", future=True)
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()

    # 2) 指向测试库并清缓存(config/engine/sessionmaker 都带 lru_cache)
    os.environ["DATABASE_URL"] = TEST_URL
    from app import db
    from app.config import get_settings

    get_settings.cache_clear()
    db.get_engine.cache_clear()
    db._get_sessionmaker.cache_clear()

    # 3) 一条命令建库:alembic upgrade head(逐表 DDL + REVOKE + tenant_id=0)
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    yield

    db.get_engine().dispose()
