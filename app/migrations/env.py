"""Alembic 运行环境。连接串从 app.config 读取(单一真源)。

本项目迁移用原始 SQL(op.execute)逐表照搬 data-model.md 的 DDL,不用 autogenerate、
不挂 ORM MetaData —— 迁移即设计文档的 1:1 落地,避免 ORM 反射改名/漂移。
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings

config = context.config

# 用 app.config 的连接串覆盖 alembic.ini(后者不写死 URL)。
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # 无 ORM 元数据:全部走原始 SQL


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
