"""tag_provenance_by_source 改按维度双向 【裁决八】

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-07

设计冻结后首次修订(基线 design-freeze-v3 → v3.1)。动因:model 产出的 theme/color_scheme 是
自由文本维(不受词表约束),原 CHECK 要求所有 model 标签 vocab_version_id 非空,二者冲突。
裁决八:按维度双向收紧(仿 N2 role 双向)——
  · 受约束维(structure/color/scene)的 model 标签:vocab_version_id 必须非空;
  · 自由文本维(theme/color_scheme)的 model 标签:vocab_version_id 必须为空(禁止伪造锚点);
  · 其余五项溯源(model_id/prompt_version/config_version_id/run_id/input_hash)对全部 model 标签维持强制。
data-model §3.5 同步修订并标注【裁决八】。
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


_NEW = """
ALTER TABLE tag DROP CONSTRAINT tag_provenance_by_source;
ALTER TABLE tag ADD CONSTRAINT tag_provenance_by_source CHECK (
    source <> 'model' OR (
        model_id IS NOT NULL AND prompt_version IS NOT NULL AND
        config_version_id IS NOT NULL AND run_id IS NOT NULL AND input_hash IS NOT NULL AND
        CASE
            WHEN dimension IN ('structure','color','scene') THEN vocab_version_id IS NOT NULL
            WHEN dimension IN ('theme','color_scheme')       THEN vocab_version_id IS NULL
            ELSE false
        END
    )
);
"""

_OLD = """
ALTER TABLE tag DROP CONSTRAINT tag_provenance_by_source;
ALTER TABLE tag ADD CONSTRAINT tag_provenance_by_source CHECK (
    source <> 'model' OR (
        model_id IS NOT NULL AND prompt_version IS NOT NULL AND
        vocab_version_id IS NOT NULL AND config_version_id IS NOT NULL AND
        run_id IS NOT NULL AND input_hash IS NOT NULL
    )
);
"""


def upgrade() -> None:
    op.execute(_NEW)


def downgrade() -> None:
    op.execute(_OLD)
