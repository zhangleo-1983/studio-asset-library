"""active_config — 当前生效配置指针 【OQ-1/裁决七】

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-05

裁决七(方案二·显式生效指针)落地:新增 active_config 小表。照搬 data-model §3.10 DDL。
本表**非只增**(是"当前状态",可 UPDATE 推指针;履历落 event),故对 app_role 授予含 UPDATE 的
权限、**不** REVOKE——与四张只增表相反。
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


ACTIVE_CONFIG = """
CREATE TABLE active_config (
    tenant_id         BIGINT NOT NULL REFERENCES tenant(tenant_id),
    scope             TEXT   NOT NULL,               -- 'tagging'|'review'|...(与 config_version.scope 对齐)
    config_version_id BIGINT NOT NULL REFERENCES config_version(config_version_id),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, scope),                  -- 每(租户,scope)至多一行当前生效
    UNIQUE (config_version_id)                       -- 一个 config_version 至多被一处指向
);
"""

# 非只增表:授予含 UPDATE(推指针 = UPDATE),不 REVOKE。0001 的 GRANT ON ALL TABLES 不覆盖
# 本次新表,故这里单独 GRANT。
GRANT_ACTIVE_CONFIG = """
GRANT SELECT, INSERT, UPDATE ON active_config TO balloon_app;
"""


def upgrade() -> None:
    op.execute(ACTIVE_CONFIG)
    op.execute(GRANT_ACTIVE_CONFIG)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS active_config CASCADE;")
