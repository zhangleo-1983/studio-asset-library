"""active_config 生效指针跨租户复合外键 【R03 P1-3】

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07

R03 P1-3:activate_config 的单列外键拦不住"把本租户指针推到别租户配置"。仿【加固1】把纪律
保证升级为结构保证——config_version 加 UNIQUE(config_version_id, tenant_id),active_config 的
config_version 外键改复合 (config_version_id, tenant_id),库层杜绝跨租户生效指针。
应用层另有 activate_config 早失败校验(含 payload.vocab_versions 逐维归属)。
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


UP = """
ALTER TABLE config_version ADD CONSTRAINT config_version_id_tenant_uq
    UNIQUE (config_version_id, tenant_id);
ALTER TABLE active_config DROP CONSTRAINT active_config_config_version_id_fkey;
ALTER TABLE active_config ADD CONSTRAINT active_config_config_version_tenant_fkey
    FOREIGN KEY (config_version_id, tenant_id)
    REFERENCES config_version (config_version_id, tenant_id);
"""

DOWN = """
ALTER TABLE active_config DROP CONSTRAINT active_config_config_version_tenant_fkey;
ALTER TABLE active_config ADD CONSTRAINT active_config_config_version_id_fkey
    FOREIGN KEY (config_version_id) REFERENCES config_version (config_version_id);
ALTER TABLE config_version DROP CONSTRAINT config_version_id_tenant_uq;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
