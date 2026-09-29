"""initial schema — data-model.md (design-freeze-v3) 全部 DDL 逐表照搬

Revision ID: 0001
Revises:
Create Date: 2026-07-05

逐表照搬 docs/data-model.md §3 的 DDL,不增不减不改名。表名/约束名/索引名与文档 1:1。
建表顺序按外键依赖调整(config_version/vocabulary_version
先于引用它们的 task/tag),仅调顺序、不改 DDL 内容。

本迁移额外承担 migration.md §4 步骤 0 中"固化在建库迁移内"的两件事:
  1) tenant_id=0(平台公共库保留号)种子行;
  2) 对四张只增表 REVOKE UPDATE, DELETE(【加固2/N10】把只增承诺升级为 DDL 级)。
其余租户级种子(示例客户 + 初始用户 + 词表 + 配置 + 各自 event)在参数化脚本 app/seed.py。
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


# ── 应用运行角色:REVOKE 的作用对象 ──────────────────────────────
# 应用连接理应用此角色(回收了改删权限);迁移/种子/测试用 owner 连接不受 REVOKE 限制。
CREATE_APP_ROLE = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_app') THEN
        CREATE ROLE platform_app NOLOGIN;
    END IF;
END
$$;
"""

# ── §3.1 tenant / app_user 【不变量一】────────────────────────────
TENANT = """
CREATE TABLE tenant (
    tenant_id     BIGINT PRIMARY KEY,           -- 0 保留给平台公共库;不用 NULL 承载"无租户"
    slug          TEXT UNIQUE NOT NULL,
    display_name  TEXT NOT NULL,
    industry      TEXT NOT NULL DEFAULT 'generic',
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    timestamptz NOT NULL DEFAULT now()
);
"""

APP_USER = """
CREATE TABLE app_user (
    user_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     BIGINT NOT NULL REFERENCES tenant(tenant_id),
    username      TEXT,                          -- Web 端;租户内唯一
    password_hash TEXT,
    wx_openid     TEXT,                          -- 小程序端【architecture 裁决5:账号体系隔断墙】
    role          TEXT NOT NULL DEFAULT 'operator',  -- operator|reviewer|admin(租户内角色)
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, username),
    UNIQUE (tenant_id, wx_openid)
);
"""

# ── §3.2 asset 【不变量三】────────────────────────────────────────
ASSET = """
CREATE TABLE asset (
    asset_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    content_hash   TEXT NOT NULL,                -- sha256,去重键
    byte_size      BIGINT NOT NULL,
    mime_type      TEXT NOT NULL,
    width          INT,
    height         INT,
    storage_key    TEXT NOT NULL,                -- 由 {tenant_id}/{asset_id}/... 规则推导的缓存,不作业务依赖
    thumb_key      TEXT,                          -- 【Q4】仅当源格式 OSS 图片处理不支持时预生成;否则为空,缩略图实时生成
    original_name  TEXT,                          -- 仅导出展示用,不承载业务
    uploaded_by    BIGINT REFERENCES app_user(user_id),
    uploaded_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at     timestamptz,                   -- 软删;删除落 event
    UNIQUE (tenant_id, content_hash),             -- 同租户内容去重
    UNIQUE (asset_id, tenant_id)                  -- 【加固1】复合唯一,供 tag/task/selection_item 复合外键指向
);
CREATE INDEX asset_tenant_idx ON asset (tenant_id) WHERE deleted_at IS NULL;
"""

# ── §3.7 config_version(先于 task/tag 引用)【不变量二 / Q2】──────
CONFIG_VERSION = """
CREATE TABLE config_version (
    config_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    scope          TEXT NOT NULL,                 -- 'tagging'|'review'|...
    payload        JSONB NOT NULL,
    prompt_version TEXT,                           -- 【Q2】对应的提示词版本号
    prompt_sha256  TEXT,                           -- 【Q2】提示词本体内容 hash,锚定"在什么规则下打的"
    created_by     BIGINT REFERENCES app_user(user_id),
    created_at     timestamptz NOT NULL DEFAULT now()
);
"""

# ── §3.4 vocabulary_version / vocabulary / alias_map 【不变量二、三】─
VOCABULARY_VERSION = """
CREATE TABLE vocabulary_version (
    vocab_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    dimension      TEXT NOT NULL,                 -- 'structure'|'color'|'scene'
    version_no     INT NOT NULL,                  -- 该(租户,维度)下自增
    created_by     BIGINT REFERENCES app_user(user_id),
    created_at     timestamptz NOT NULL DEFAULT now(),
    note           TEXT,
    UNIQUE (tenant_id, dimension, version_no)
);
"""

VOCABULARY = """
CREATE TABLE vocabulary (
    vocab_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    dimension      TEXT NOT NULL,                 -- structure|color|scene
    concept_key    TEXT NOT NULL,                 -- 稳定概念键(ASCII),如 'shape_a'/'red'/'scene_x' —— tag.value 存这个
    labels         JSONB NOT NULL,                -- {"zh":"<词形>"};未来 {"zh":"<词形>","en":"<word>"}。翻译在此层,不在数据层【不变量三】
    color_kind     TEXT,                          -- color 维专用:'simple'|'compound'
    active         BOOLEAN NOT NULL DEFAULT true,
    vocab_version_id BIGINT NOT NULL REFERENCES vocabulary_version(vocab_version_id),
    UNIQUE (tenant_id, dimension, concept_key, vocab_version_id)
);
-- 【N9】表达式唯一约束必须用 CREATE UNIQUE INDEX(PG 表内 UNIQUE 约束不支持表达式):
-- 【A-4】labels 的 zh 词形在(租户,维度,同一版本)内唯一,否则模型输出词形→concept_key 反查歧义
CREATE UNIQUE INDEX vocabulary_zh_uq
    ON vocabulary (tenant_id, dimension, vocab_version_id, (labels->>'zh'));
"""

ALIAS_MAP = """
CREATE TABLE alias_map (
    alias_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    dimension      TEXT NOT NULL,                 -- structure|theme|color|scene
    alias          TEXT NOT NULL,                 -- 别名/变体词形,如某个变体词形
    concept_key    TEXT NOT NULL,                 -- 【A-2】指向标准 concept_key,如 'shape_c'(不再是中文标准词形)
    source         TEXT NOT NULL DEFAULT 'human', -- human|sync_corrections(回流自动追加)
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, dimension, alias)          -- 同维度同别名唯一;冲突/成环由回流写入路径拒绝(旧逻辑保留)
);
"""

# ── §3.3 task 【不变量四】────────────────────────────────────────
TASK = """
CREATE TABLE task (
    task_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    task_type      TEXT NOT NULL,                 -- 本期仅 'tagging';未来 bom_extract/audit 直接加值,不改表
    asset_id       BIGINT NOT NULL,               -- 输入资产(引用非路径)【Q5:统一用 asset_id,不用 input_ref】
    run_id         TEXT NOT NULL,                 -- 批次号,批量/断点续跑键
    status         TEXT NOT NULL DEFAULT 'pending', -- pending|running|done|failed|needs_review
    config_version_id BIGINT REFERENCES config_version(config_version_id),
    output         JSONB,                         -- 按 task_type 各自定义的结构化输出(tagging=四维标签原始 JSON,含模型原样输出)
    output_schema_version TEXT,                   -- 'tagging_output_v2'
    model_id       TEXT,                          -- 'qwen-vl-max'(含版本)
    input_tokens   INT,                           -- 【N7】含重试的累计值(非单次)
    output_tokens  INT,                           -- 【N7】含重试的累计值(非单次)
    latency_ms     INT,
    retry_count    INT NOT NULL DEFAULT 0,        -- 【Q6】重试次数
    error          TEXT,
    created_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz,
    FOREIGN KEY (asset_id, tenant_id) REFERENCES asset(asset_id, tenant_id)  -- 【加固1】复合外键
);
CREATE INDEX task_tenant_type_idx ON task (tenant_id, task_type, status);
CREATE INDEX task_run_idx ON task (tenant_id, run_id);
"""

# ── §3.5 tag 【不变量二 / C1 / C2 / 裁决二】──────────────────────
TAG = """
CREATE TABLE tag (
    tag_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    asset_id       BIGINT NOT NULL,                             -- 挂资产(非路径/文件名)【不变量三】
    task_id        BIGINT REFERENCES task(task_id),             -- 由哪个打标任务产生;human 补标签可空

    dimension      TEXT NOT NULL,                 -- 'theme'|'color'|'structure'|'scene'|'color_scheme'
    -- 【C2/A-1】受词表约束维度(structure/color/scene)存 concept_key(如 'red');
    --           theme 与 color_scheme 维为自由文本(模型自由生成,不受词表约束);
    --           【A-6/裁决五】unresolved 标签的 value 例外存"裸原词形"(反查失败,待人工归类)
    value          TEXT NOT NULL,
    role           TEXT,                          -- 【裁决二/N2】仅 color 维取 'primary'|'accent';其余维必须为空(双向 CHECK)
    -- 【N1/裁决五】status 四值枚举 + 值域 CHECK
    status         TEXT NOT NULL DEFAULT 'active',                -- 'active'|'removed'|'superseded'|'unresolved'

    -- ── 溯源五问 ────────────────────────────────
    source         TEXT NOT NULL,                 -- 'model'|'human'
    model_id       TEXT,                          -- 'qwen-vl-max'(含版本)
    prompt_version TEXT,                           -- 提示词版本(内容锚见 config_version,Q2)
    vocab_version_id BIGINT REFERENCES vocabulary_version(vocab_version_id),  -- 【N11】human 补受约束维标签也记(审核员选自某版词表 UI)
    config_version_id BIGINT REFERENCES config_version(config_version_id),
    run_id         TEXT,
    input_hash     TEXT,                           -- = asset.content_hash 快照
    input_tokens   INT,
    output_tokens  INT,
    confidence     NUMERIC(4,3),
    needs_review   BOOLEAN NOT NULL DEFAULT false,
    current_correction_id BIGINT,                  -- 【N8】最新修正指针;不设 DB 外键(与 tag_correction 环形),由应用层唯一写入路径维护;如需强约束可改 DEFERRABLE FK
    created_at     timestamptz NOT NULL DEFAULT now(),

    FOREIGN KEY (asset_id, tenant_id) REFERENCES asset(asset_id, tenant_id),  -- 【加固1】复合外键

    -- 【N6】承重枚举值域 CHECK
    CONSTRAINT tag_status_vals CHECK (status IN ('active','removed','superseded','unresolved')),
    CONSTRAINT tag_source_vals CHECK (source IN ('model','human')),
    -- 【N2】role 双向收紧:color 维必选 primary/accent,非 color 维必须为空——杜绝 role=NULL 的 color 标签在默认主色检索下隐身
    CONSTRAINT tag_role_shape CHECK (
        (dimension = 'color'  AND role IN ('primary','accent')) OR
        (dimension <> 'color' AND role IS NULL)
    ),
    -- 【C3】溯源按 source 分级强制:model 来源必须溯源齐全;human 补标签天然无模型溯源
    CONSTRAINT tag_provenance_by_source CHECK (
        source <> 'model' OR (
            model_id IS NOT NULL AND prompt_version IS NOT NULL AND
            vocab_version_id IS NOT NULL AND config_version_id IS NOT NULL AND
            run_id IS NOT NULL AND input_hash IS NOT NULL
        )
    )
);
CREATE INDEX tag_filter_idx   ON tag (tenant_id, dimension, value) WHERE status = 'active';  -- 检索主力
CREATE INDEX tag_color_role_idx ON tag (tenant_id, value) WHERE dimension='color' AND status='active';
CREATE INDEX tag_asset_idx    ON tag (tenant_id, asset_id);
CREATE INDEX tag_vocabver_idx ON tag (tenant_id, vocab_version_id);  -- 词表升级定位
CREATE INDEX tag_review_idx   ON tag (tenant_id, dimension) WHERE status='unresolved';  -- 复核队列默认含 unresolved
"""

# ── §3.6 tag_correction 【C1 / 不变量二、五】────────────────────
TAG_CORRECTION = """
CREATE TABLE tag_correction (
    correction_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    tag_id         BIGINT NOT NULL REFERENCES tag(tag_id),
    kind           TEXT NOT NULL,                 -- 【C1/裁决五】'update'|'remove'|'restore'|'supersede'
    old_value      TEXT,                          -- update/remove 非空;restore/supersede 可空(见 CHECK)
    new_value      TEXT,                          -- update 非空;remove/restore/supersede 为空
    source         TEXT NOT NULL DEFAULT 'human', -- human|model(重打/supersede)
    corrected_by   BIGINT REFERENCES app_user(user_id),
    corrected_at   timestamptz NOT NULL DEFAULT now(),
    reason         TEXT,
    -- 【N6】kind 值域
    CONSTRAINT correction_kind_vals CHECK (kind IN ('update','remove','restore','supersede')),
    -- 【C1/N4】按 kind 约束值:改值两值齐全;删标强制记删除时当前值(old 非空)、无新值;恢复/取代不改 value(两值皆空)
    CONSTRAINT correction_shape CHECK (
        (kind='update'    AND old_value IS NOT NULL AND new_value IS NOT NULL) OR
        (kind='remove'    AND old_value IS NOT NULL AND new_value IS NULL) OR
        (kind='restore'   AND old_value IS NULL AND new_value IS NULL) OR
        (kind='supersede' AND old_value IS NULL AND new_value IS NULL)
    ),
    -- 【R02 核销尾巴】与 event 的 C6 同构:human 修正必须有行为人,修正链自证 who,不靠 event 表担保
    CONSTRAINT correction_actor_present CHECK (
        source <> 'human' OR corrected_by IS NOT NULL
    )
);
CREATE INDEX tag_correction_tag_idx ON tag_correction (tenant_id, tag_id, corrected_at);
"""

# ── §3.8 event 【不变量五 / C6 / Q7】────────────────────────────
EVENT = """
CREATE TABLE event (
    event_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),   -- 带 tenant
    event_type     TEXT NOT NULL,   -- upload|tagging_done|correction|selection|export|config_change|delete|...(开放)
    actor_user_id  BIGINT REFERENCES app_user(user_id),            -- 带行为人
    actor_kind     TEXT NOT NULL,                                  -- 【C6】去 default,human|system
    occurred_at    timestamptz NOT NULL DEFAULT now(),             -- 带时间戳
    sensitive      BOOLEAN NOT NULL DEFAULT false,                 -- 由写入函数按 event_type 集中推导,非调用方手填【Q7】
    subject_type   TEXT,            -- 'asset'|'tag'|'vocabulary'|...
    subject_id     BIGINT,
    payload        JSONB,
    -- 【C6】human 行为必须有行为人;system 行为(打标完成等)允许无 user
    CONSTRAINT event_actor_present CHECK (
        (actor_kind='human' AND actor_user_id IS NOT NULL) OR actor_kind='system'
    )
);
CREATE INDEX event_tenant_time_idx ON event (tenant_id, occurred_at);
CREATE INDEX event_audit_idx ON event (tenant_id, occurred_at) WHERE sensitive;
"""

# ── §3.9 selection / selection_item / export_job ─────────────────
SELECTION = """
CREATE TABLE selection (            -- 选图篮
    selection_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    owner_user_id  BIGINT NOT NULL REFERENCES app_user(user_id),
    name           TEXT,
    created_at     timestamptz NOT NULL DEFAULT now()
);
"""

SELECTION_ITEM = """
CREATE TABLE selection_item (
    selection_id   BIGINT NOT NULL REFERENCES selection(selection_id),
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    asset_id       BIGINT NOT NULL,
    added_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (selection_id, asset_id),
    FOREIGN KEY (asset_id, tenant_id) REFERENCES asset(asset_id, tenant_id)  -- 【加固1】复合外键
);
"""

EXPORT_JOB = """
CREATE TABLE export_job (
    export_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    requested_by   BIGINT REFERENCES app_user(user_id),
    kind           TEXT NOT NULL,                 -- 'tag_json'|'tag_csv'|'asset_zip'
    params         JSONB,
    status         TEXT NOT NULL DEFAULT 'pending',
    result_key     TEXT,
    created_at     timestamptz NOT NULL DEFAULT now()
);
"""

# ── 【加固2/N10】四张只增表回收 UPDATE/DELETE(升级为 DDL 级)────────
# 先 GRANT 基础 CRUD 给 app_role,再对只增表 REVOKE,使"只增"成为真实授权状态。
GRANT_APP_ROLE = """
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO platform_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO platform_app;
"""

REVOKE_APPEND_ONLY = """
REVOKE UPDATE, DELETE ON event, tag_correction, vocabulary_version, config_version FROM platform_app;
"""

# ── migration §4 步骤 0:tenant_id=0 平台保留号,固化在建库迁移内 ───
# 只固化保留号的存在(平台级、无业务 actor);租户级种子(示例客户 + 用户 + 词表 + 配置 +
# 各自 event)走参数化脚本 app/seed.py,事件一律经 record_event 写入,不在此绕过。
SEED_PLATFORM_TENANT = """
INSERT INTO tenant (tenant_id, slug, display_name, industry, status)
VALUES (0, 'platform', '平台公共库', 'platform', 'active')
ON CONFLICT (tenant_id) DO NOTHING;
"""

# 建表顺序(FK 依赖):被引用者在前。
_CREATE_ORDER = [
    ("tenant", TENANT),
    ("app_user", APP_USER),
    ("asset", ASSET),
    ("config_version", CONFIG_VERSION),
    ("vocabulary_version", VOCABULARY_VERSION),
    ("vocabulary", VOCABULARY),
    ("alias_map", ALIAS_MAP),
    ("task", TASK),
    ("tag", TAG),
    ("tag_correction", TAG_CORRECTION),
    ("event", EVENT),
    ("selection", SELECTION),
    ("selection_item", SELECTION_ITEM),
    ("export_job", EXPORT_JOB),
]

# 删表顺序 = 建表逆序。
_DROP_ORDER = [name for name, _ in reversed(_CREATE_ORDER)]


def upgrade() -> None:
    op.execute(CREATE_APP_ROLE)
    for _name, ddl in _CREATE_ORDER:
        op.execute(ddl)
    op.execute(GRANT_APP_ROLE)
    op.execute(REVOKE_APPEND_ONLY)
    op.execute(SEED_PLATFORM_TENANT)


def downgrade() -> None:
    for name in _DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {name} CASCADE;")
    # platform_app 角色不随迁移删除(可能被其它库/授权共享);如需清理由运维手动 DROP ROLE。
