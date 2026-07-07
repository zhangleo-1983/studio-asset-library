# balloon-platform 数据模型草案

> 状态:**v3.1(design-freeze-v3 冻结后首次修订)**。修订项:【裁决八】`tag_provenance_by_source`
> 改按维度双向(自由文本维 theme/color_scheme 的 model 标签 vocab_version_id 必为空)——见 §3.5 /
> §5 与 alembic `0003`,裁决记录见 [reviews/](../reviews/)。宪法:[PRINCIPLES.md](../PRINCIPLES.md)。
> 本稿在 v2 基础上按《评审意见 R02》N1–N12 与《裁决记录 R02》裁决四(A-3 冻结)、裁决五(A-6+N1 合并:status 四态 + 反查失败落库)返修;R02 新增/变更处标注 N 编号(如【N1】【N4】),沿用编号(如【C1】【A-3】)保留。
> **核心口径(裁决一 · 方案 A):** 受词表约束的维度(structure/color/scene),`tag.value` 存 **concept_key**(如 `column`/`red`/`wedding`),展示词形经 `vocabulary` 翻译取得;theme 维度保持自由文本。concept_key 命名**已由裁决四批准并冻结**,见 [migration.md](./migration.md) §1.2【A-3 定稿】。
> DDL 用 PostgreSQL 方言书写,表达结构意图,非最终迁移脚本。命名 snake_case,时间戳一律 `timestamptz`(UTC)。

---

## 1. 全表清单

| 表 | 作用 | 只增? |
|---|---|---|
| `tenant` | 租户 | 否 |
| `app_user` | 用户(Web 用户名密码 / 小程序 openid),归属租户 | 否 |
| `asset` | 资产元数据(图片),以 asset_id + 内容 hash 关联对象存储 | 否(软删) |
| `task` | 通用任务表(task_type 开放),一次 AI 操作一行 | 否(状态可变) |
| `tag` | 标签(带完整溯源 + status + role),value 存 concept_key | 否(改值/删标走 tag_correction) |
| `tag_correction` | 标签修正链(只增,含 update/remove/restore) | **是** |
| `vocabulary` | 词表条目(concept_key + labels 多语言留位) | 否 |
| `vocabulary_version` | 词表版本(升级定位/批量重打的依据) | **是**(版本只增) |
| `alias_map` | 输出归一化:别名词形 → concept_key,按维度分区 | 否 |
| `config_version` | 打标/复核等配置版本快照(含 prompt 内容锚) | **是** |
| `event` | 业务事件流水(唯一事件承重墙) | **是** |
| `selection` / `selection_item` | 选图篮(小程序) | 否 |
| `export_job` | 数据导出任务记录 | 否 |

> 运维日志不在此——走标准 logging,不入业务库。【不变量五】

---

## 2. 五不变量合规矩阵(逐表核对)

| 表 | ①tenant_id | ②溯源全字段 | ③资产/标签分离 | ④task_type 开放 | ⑤事件只增/actor/时间戳 |
|---|:--:|:--:|:--:|:--:|:--:|
| tenant | 自身即租户 | — | — | — | — |
| app_user | ✅ | — | — | — | — |
| asset | ✅ | 上传溯源 | ✅ asset_id+hash 关联存储 | — | 上传落 event |
| task | ✅ | run_id/config/token/model | 引用 asset_id 非路径 | ✅ task_type 普通列 | 完成落 event |
| tag | ✅ | ✅ 全字段(§3.5) | ✅ 挂 asset_id | 由 task 承载类型 | 修正落 event |
| tag_correction | ✅ | ✅ kind/原值保留/who/when | ✅ | — | 每条修正落 event |
| vocabulary | ✅ | 版本号 | — | — | 编辑落 event |
| vocabulary_version | ✅ | ✅ 版本即溯源锚点 | — | — | 升级落 event |
| alias_map | ✅ | 来源(人工/回流) | — | — | 变更落 event |
| config_version | ✅ | ✅ 含 prompt sha256 | — | — | 变更落 event |
| event | ✅ | — | — | event_type 开放 | ✅ 只增/actor CHECK/时间戳 |
| selection* | ✅ | — | 引用 asset_id | — | 选图/转发落 event |
| export_job | ✅ | 导出参数快照 | 打包引用 asset_id | — | 导出落 event(sensitive) |

> 矩阵证明"想到了";每张表**接不接得住**真实操作,见 [scenario-walkthrough.md](./scenario-walkthrough.md) 三场景走查(裁决三要求)。

---

## 3. 核心表 DDL(草案)

### 3.1 tenant / app_user 【不变量一】

```sql
CREATE TABLE tenant (
    tenant_id     BIGINT PRIMARY KEY,           -- 0 保留给平台公共库;不用 NULL 承载"无租户"
    slug          TEXT UNIQUE NOT NULL,
    display_name  TEXT NOT NULL,
    industry      TEXT NOT NULL DEFAULT 'balloon_party',
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    timestamptz NOT NULL DEFAULT now()
);
-- tenant_id=0(平台保留)与首个租户示例客户、初始管理用户,由建库迁移脚本种子写入,见 migration §4 步骤 0【C7】

CREATE TABLE app_user (
    user_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     BIGINT NOT NULL REFERENCES tenant(tenant_id),
    username      TEXT,                          -- Web 端;租户内唯一
    password_hash TEXT,
    wx_openid     TEXT,                          -- 小程序端【arch 裁决5:账号体系隔断墙】
    role          TEXT NOT NULL DEFAULT 'operator',  -- operator|reviewer|admin(租户内角色)
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, username),
    UNIQUE (tenant_id, wx_openid)
);
```

### 3.2 asset — 资产与标签分离的锚点 【不变量三】

```sql
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
```

> **【Q3】软删资产重复上传:** `UNIQUE(tenant_id, content_hash)` 会挡"删了又传同一张图"。定义行为:上传命中的 content_hash 若属**已软删** asset(`deleted_at` 非空)→ 清空 `deleted_at` **恢复**该 asset(不新建行、asset_id 不变),并落"上传/恢复"event;命中未软删的则按普通去重跳过。
> **【加固1】** `UNIQUE(asset_id, tenant_id)` 让下游表用复合外键 `(asset_id, tenant_id)` 指向 asset——"A 租户标签挂 B 租户图"在库层不可能,不变量一从纪律保证升级为结构保证。【不变量一】

### 3.3 task — 通用任务表(task_type 开放)【不变量四】

```sql
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
```

> **【Q6/N7】计费口径:** `failed` 任务与每次重试**真实消耗的 token 全部计入用量统计**(成本是真实发生的)。**【N7】** `task.input_tokens`/`output_tokens` 存**含重试的累计值**(非单次);若将来需要逐次明细,落 `event` payload,不在 task 上加"逐次"列——不留空头承诺。是否就失败/重试**向租户收费**属"计费口径",将来单独定义;本期只保证"用量统计"口径完整、可聚合,二者区分写明。【不变量二】
> **【队列=PG】** 任务队列 = 对 task 表 `SELECT ... FOR UPDATE SKIP LOCKED` 取 `pending` 行,不引 Redis。
> `task_type` 普通列 + `output` JSONB —— 新增任务类型不改表结构。**不建插件/编排框架。**【不变量四"禁止"条款】

### 3.4 vocabulary / vocabulary_version / alias_map — 词表 【不变量二、三】

```sql
-- 词表版本:每次编辑生成新版本号,标签溯源引用它;升级后据此定位需重打的标签
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

-- 词表条目:concept_key 稳定不改,labels 承载各语言词形(本期只填 zh),多语言留位
CREATE TABLE vocabulary (
    vocab_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    dimension      TEXT NOT NULL,                 -- structure|color|scene
    concept_key    TEXT NOT NULL,                 -- 稳定概念键(ASCII),如 'column'/'red'/'wedding' —— tag.value 存这个
    labels         JSONB NOT NULL,                -- {"zh":"立柱"};未来 {"zh":"立柱","en":"column"}。翻译在此层,不在数据层【不变量三】
    color_kind     TEXT,                          -- color 维专用:'simple'|'compound'
    active         BOOLEAN NOT NULL DEFAULT true,
    vocab_version_id BIGINT NOT NULL REFERENCES vocabulary_version(vocab_version_id),
    UNIQUE (tenant_id, dimension, concept_key, vocab_version_id)
);
-- 【N9】表达式唯一约束必须用 CREATE UNIQUE INDEX(PG 表内 UNIQUE 约束不支持表达式):
-- 【A-4】labels 的 zh 词形在(租户,维度,同一版本)内唯一,否则模型输出词形→concept_key 反查歧义
CREATE UNIQUE INDEX vocabulary_zh_uq
    ON vocabulary (tenant_id, dimension, vocab_version_id, (labels->>'zh'));

-- 输出归一化:模型输出的中文别名词形 → concept_key。按维度分区,迁移自旧 alias_map.yaml
CREATE TABLE alias_map (
    alias_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    dimension      TEXT NOT NULL,                 -- structure|theme|color|scene
    alias          TEXT NOT NULL,                 -- 别名/变体词形,如 '气球花盒'
    concept_key    TEXT NOT NULL,                 -- 【A-2】指向标准 concept_key,如 'flowerbox'(不再是中文标准词形)
    source         TEXT NOT NULL DEFAULT 'human', -- human|sync_corrections(回流自动追加)
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, dimension, alias)          -- 同维度同别名唯一;冲突/成环由回流写入路径拒绝(旧逻辑保留)
);
```

> **【A-2】** `alias_map` 从"别名→中文标准词形"改为"别名词形→concept_key"。例:`气球花盒 → flowerbox`(不再是 `气球花盒 → 花盒`)。migration §1.3 迁移动作同步改。
> **【A-4】归一化解析链(落库口径):** 模型按 prompt 注入的 zh 词表输出**中文词形** → 先查 `alias_map`(别名→concept_key),未命中再查当期 `vocabulary.labels.zh`(词形→concept_key)→ 命中则 `tag.value` 落 concept_key;**模型原始输出完整保留在 `task.output`**。两处都查不到走【A-6/裁决五】失败路径(status='unresolved',见 §3.5 与 architecture §3.3)。
> **【N12】alias_map 无版本维、concept_key 需存在于当期词表版本:** 概念下线后,老 alias 可能指向已不在当期版本的 concept_key。故**归一化解析**与**回流写入**各补一条校验——`concept_key` 必须存在于当期 `vocabulary_version` 且 `active=true`,否则:解析侧按【A-6】失败路径(unresolved)处理;回流写入侧拒绝并交人工裁决。

### 3.5 tag — 标签溯源完整 + status + role 【不变量二 / C1 / C2 / 裁决二】

```sql
CREATE TABLE tag (
    tag_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    asset_id       BIGINT NOT NULL,                             -- 挂资产(非路径/文件名)【不变量三】
    task_id        BIGINT REFERENCES task(task_id),             -- 由哪个打标任务产生;human 补标签可空

    dimension      TEXT NOT NULL,                 -- 'theme'|'color'|'structure'|'scene'|'color_scheme'
    -- 【C2/A-1】受词表约束维度(structure/color/scene)存 concept_key(如 'column'/'red');
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
    -- 【C3 + 裁决八】溯源按 source 分级强制;vocab_version_id 再按维度双向收紧:
    --   受约束维(structure/color/scene)model 标签 vocab_version_id 必须非空;
    --   自由文本维(theme/color_scheme)model 标签 vocab_version_id 必须为空(禁止伪造锚点,仿 N2);
    --   其余五项溯源(model_id/prompt_version/config_version_id/run_id/input_hash)对全部 model 标签维持强制。
    CONSTRAINT tag_provenance_by_source CHECK (
        source <> 'model' OR (
            model_id IS NOT NULL AND prompt_version IS NOT NULL AND
            config_version_id IS NOT NULL AND run_id IS NOT NULL AND input_hash IS NOT NULL AND
            CASE
                WHEN dimension IN ('structure','color','scene') THEN vocab_version_id IS NOT NULL
                WHEN dimension IN ('theme','color_scheme')       THEN vocab_version_id IS NULL
                ELSE false
            END
        )
    )
);
CREATE INDEX tag_filter_idx   ON tag (tenant_id, dimension, value) WHERE status = 'active';  -- 检索主力
CREATE INDEX tag_color_role_idx ON tag (tenant_id, value) WHERE dimension='color' AND status='active';
CREATE INDEX tag_asset_idx    ON tag (tenant_id, asset_id);
CREATE INDEX tag_vocabver_idx ON tag (tenant_id, vocab_version_id);  -- 词表升级定位
CREATE INDEX tag_review_idx   ON tag (tenant_id, dimension) WHERE status='unresolved';  -- 复核队列默认含 unresolved
```

> **【C2/A-1】** `value` 存 concept_key(受约束维度)或自由文本(theme/color_scheme)。展示词形一律经 `vocabulary.labels` 翻译;改词形("立柱"→"圆柱")= 纯词表编辑,零标签重写、零重打。
> **【N1/裁决五】status 四态语义:** `active` 参与检索;`removed` 人工删的错标;`superseded` 被重打新版取代的旧标签;`unresolved` 反查失败待人工归类。**检索一律只查 `active`;其余三态原行与溯源永久保留**,是不变量二的完整形态。
> **`superseded` 触发(收敛机制,N1 核心):** 重打批次**人工验收通过后**,系统对同 `(asset_id, dimension)` 且 `vocab_version` 早于本批的 `active` 标签**批量置 `superseded`**,落 `tag_correction`(`kind='supersede'`, `source='model'`)+ event。此前旧标签维持 `active`、与新标签并存(供验收对比);验收通过才收敛。这样重打既不双计(同值)也不让旧错值继续命中(异值)。
> **【A-6/裁决五】unresolved(反查失败落库):** 模型词形在 alias/词表都查不到 → `value` 存**裸原词形**(无 `raw:` 前缀:concept_key 强制 ASCII,中文词形天然不冒充概念键)、`status='unresolved'`、`needs_review=true`,进复核队列。**闭环强制:** 人工补 alias/扩词表后走修正链转正——`kind='update'`(old=原词形, new=concept_key)+ status 迁回 `active`;判为垃圾则 `kind='remove'`。unresolved 不允许滞留,复核队列视图默认包含它。
> **【C1】删错标 / 补漏标:** 删错标 = `status='removed'`(不 DELETE);补漏标 = 新增 `source='human'` 行、模型溯源列可空(CHECK 放行),不走修正链;human 补受约束维标签仍记 `vocab_version_id`【N11】(缩小查询②"待归类"桶)。
> **【裁决二】role + color_scheme:** color 维带 `role`(必选);`scheme_name`(如"红金")落 `dimension='color_scheme'` 自由文本,与 color 单色维互补、不混算。

### 3.6 tag_correction — 修正链(只增,update/remove/restore)【C1 / 不变量二、五】

```sql
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
```

> 只增不改不删:一条 tag 的多次修正 = 多行,按 `corrected_at` 排即完整履历。
> **【N4】原始值完整口径:** 原始值 = 该 tag **最早一行 `update` 的 `old_value`**;**无 `update` 记录时 = `tag.value`**(`remove` / `supersede` 均不改 `value`,故原始值恒可恢复)。走查场景 1(只被 remove 过的标签)据此自洽:其原始值就安然在 `tag.value` 里。修正回流(sync_corrections)的 diff 基准即此。【不变量二、五】
> **补标签不入本表**(它是新增 tag 行,不是对已有 tag 的修正),仅落 event。【C1 改法3】

### 3.7 config_version — 配置版本快照(含 prompt 内容锚)【不变量二 / Q2】

```sql
CREATE TABLE config_version (
    config_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    scope          TEXT NOT NULL,                 -- 'tagging'|'review'|...
    -- 【N3】payload 显式携带各维锁定的词表版本,如:
    --   {model,temperature,few_shot,image_max_edge,review_threshold,
    --    "vocab_versions":{"structure":140,"color":102,"scene":103}}
    payload        JSONB NOT NULL,
    prompt_version TEXT,                           -- 【Q2】对应的提示词版本号
    prompt_sha256  TEXT,                           -- 【Q2】提示词本体内容 hash,锚定"在什么规则下打的"
    created_by     BIGINT REFERENCES app_user(user_id),
    created_at     timestamptz NOT NULL DEFAULT now()
);
```

> **【N3】词表版本绑定点:** worker 注入 prompt 用的词表版本,**取自 `config_version.payload.vocab_versions`,批次创建时锁定、批次内不变**——不读运行时"当前最新版"。否则批次中途一次词表编辑会让同一 `run_id` 的标签溯源到不同版本,污染查询②的定位。`tag.vocab_version_id` 是这次锁定值的落地结果(走查场景 2 "config 引用 vocab_ver=140" 即指此字段)。architecture §3.3 批量执行段同步补一句。
> **【Q2】提示词内容锚 + 双保险纪律:** `prompt_version` 仅是字符串,同版本号下改文件会让溯源失真。故 ① `config_version` 记 `prompt_sha256`(提示词本体内容 hash);② 立纪律:**提示词文件按版本号命名、只增不改**(改内容 = 升版本号),迁移见 migration §1.1。标签经 `config_version_id` 关联到确切的 prompt 内容。
> 生产打标配置(`qwen-vl-max`/无 few-shot/`temperature=0`/`image_max_edge=1568`)为首个 `tagging` scope payload,迁移自旧项目锁定配置。

### 3.8 event — 事件流水(唯一事件承重墙)【不变量五 / C6 / Q7】

```sql
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
-- 【加固2/N10】只增落到 DDL(非注释):迁移脚本对全部"只增"表回收改删权限:
--   REVOKE UPDATE, DELETE ON event, tag_correction, vocabulary_version, config_version FROM <app_role>;
```

> **【C6】** `actor_kind` 去掉默认值 + CHECK:杜绝"human 行为但无行为人"的脏事件——原设计 `DEFAULT 'human'` 把最常见的遗漏方向变成违宪方向,现由 CHECK 兜底。【不变量五 — 带行为人】
> **【Q7】** `sensitive` 由唯一写入函数 `record_event()` 按 `event_type→bool` 集中映射推导(见 architecture §3.6),不散在调用点手填。
> **【N5】平台级跨租户审计事件落 `tenant_id=0`:** 查询③的平台侧聚合(C5)落的 `sensitive=true` 审计事件,因 `event.tenant_id NOT NULL`,统一记到平台保留号 `tenant_id=0`(该号正为此类平台级记录而设)。
> **【加固2/N10】** "权限层回收 UPDATE/DELETE" 写成实际 `REVOKE` 语句进迁移脚本;§1 全表清单里自称"只增"的四张表(event / tag_correction / vocabulary_version / config_version)**一并回收改删权限**,只增承诺全部升级为 DDL 级。审计视图 = `WHERE sensitive`;用量计费 = 从 task/tag 的 token 聚合,均不另建系统。【不变量二、五】

### 3.9 selection / export_job

```sql
CREATE TABLE selection (            -- 选图篮
    selection_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    owner_user_id  BIGINT NOT NULL REFERENCES app_user(user_id),
    name           TEXT,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE selection_item (
    selection_id   BIGINT NOT NULL REFERENCES selection(selection_id),
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    asset_id       BIGINT NOT NULL,
    added_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (selection_id, asset_id),
    FOREIGN KEY (asset_id, tenant_id) REFERENCES asset(asset_id, tenant_id)  -- 【加固1】复合外键
);
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
```

### 3.10 active_config — 当前生效配置指针 【OQ-1/裁决七】

```sql
-- 【裁决七 · 方案二(显式生效指针)】(tenant_id, scope) → 当前生效的 config_version。
-- 本表**非只增**:它是"当前状态",可 UPDATE(推指针);履历不落本表,落 event。
CREATE TABLE active_config (
    tenant_id         BIGINT NOT NULL REFERENCES tenant(tenant_id),
    scope             TEXT   NOT NULL,               -- 'tagging'|'review'|...(与 config_version.scope 对齐)
    config_version_id BIGINT NOT NULL REFERENCES config_version(config_version_id),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, scope),                  -- 每(租户,scope)至多一行当前生效
    UNIQUE (config_version_id)                       -- 一个 config_version 至多被一处指向
);
```

> **【OQ-1/裁决七 · 张亮 2026-07-05 书面确认】** 采纳方案二(显式生效指针);方案一(取最新
> `created_at`)、方案三(config_version 加 active 列)否决——前者回滚形态残缺、无法承载未来审批,
> 后者违反 config_version 只增 + REVOKE。
> **推指针 = UPDATE 本表**,且**必经唯一函数**落 event(`event_type='config_activate'`,
> `sensitive=true`,payload 带 `from`/`to` config_version_id)——回滚 = 指针回拨,事件可辨识。
> **当期配置/当期词表版本一律经本表解析**:worker 与【A-4】归一化解析取"当期配置"查 `active_config`,
> **禁止取最新 `created_at`、禁止硬编码**;词表当期版本沿用当期 config 的 `payload.vocab_versions`
> (§3.7【N3】),经本指针解析,不另起机制。
> **本期产品口径:** 保存配置后系统**自动推指针**(效率模式,无审批);"质量模式开关 + 租户内审批流"
> 登记 roadmap 二期候选,**留位方式 = 本指针机制**,触发条件 = 租户提出配置审批需求。
> 落地:DDL 走 alembic `0002`;唯一推指针函数见 architecture §3.6 事件段(与 `record_event` 同一收敛纪律)。

---

## 4. 三个典型查询走查(按方案 A · concept_key 改写)

> 自查口径:以下查询与 [migration.md](./migration.md) §1.2【A-3】的 concept_key 提案一致(`column`/`red`/`gold`/`structure`/`color`)。展示层一律 **API 只返回 `asset_id`**,词形与图 URL 分别经 `vocabulary` 翻译、`StorageBackend` 签发,**不把 concept_key 或 storage_key 吐给前端**【A-5/Q8】。

### 查询①:筛选「配色=红金 且 造型=立柱」的图 【不变量一、三 / A-5 / 裁决二 / Q8】

「红金」= 主色含 red 与 gold。默认按主色(`role='primary'`)。

```sql
-- 参数::tenant;造型 concept_key='column';主色含 'red' 与 'gold'
SELECT a.asset_id                                   -- 【Q8】只出 asset_id,不出 storage_key
FROM asset a
WHERE a.tenant_id = :tenant AND a.deleted_at IS NULL
  AND EXISTS (SELECT 1 FROM tag t WHERE t.tenant_id=a.tenant_id AND t.asset_id=a.asset_id
              AND t.status='active' AND t.dimension='structure' AND t.value='column')
  AND EXISTS (SELECT 1 FROM tag t WHERE t.tenant_id=a.tenant_id AND t.asset_id=a.asset_id
              AND t.status='active' AND t.dimension='color' AND t.role='primary' AND t.value='red')
  AND EXISTS (SELECT 1 FROM tag t WHERE t.tenant_id=a.tenant_id AND t.asset_id=a.asset_id
              AND t.status='active' AND t.dimension='color' AND t.role='primary' AND t.value='gold');
-- 【裁决二】"含点缀色"开关 = 去掉两处 role='primary' 谓词(放宽到全部 color 标签)
-- 【A-5】展示层:对返回的 asset_id 批量 JOIN vocabulary 取 labels->>'zh' 得中文词形;
--        图 URL 由 StorageBackend.presign/thumbnail_url 签发。concept_key 不出 API。
```

- 走 `tag_filter_idx (tenant_id, dimension, value) WHERE status='active'`;每个 EXISTS 一次索引探测。
- `status='active'` 排除人工删除的错标【C1】;`role='primary'` 落实默认主色口径【裁决二】。
- `tenant_id` 全程带,跨租户不可能命中。【不变量一】命中 `asset_id` → 展示层签发 URL,不碰文件名/目录。【不变量三】

### 查询②:词表升级后,找出需重打的标签 【不变量二 / C4】

structure 维从 v(旧)升级到新版本。需重打 = "该维度、用早于新版本的词表版本打的、资产未软删的 active 标签"。

```sql
-- 参数::tenant, :dimension='structure', :new_vocab_version_id
-- 主命中集
SELECT DISTINCT t.asset_id
FROM tag t
JOIN asset a
  ON a.asset_id = t.asset_id AND a.tenant_id = t.tenant_id
 AND a.deleted_at IS NULL                                          -- 【C4-3】排除软删资产,不烧 token
LEFT JOIN vocabulary_version vv                                    -- 【C4-2】LEFT JOIN,不静默漏 NULL
  ON vv.vocab_version_id = t.vocab_version_id
 AND vv.tenant_id = :tenant AND vv.dimension = :dimension          -- 【C4-1】限定同租户同维度
WHERE t.tenant_id = :tenant AND t.dimension = :dimension AND t.status='active'
  AND vv.version_no < (SELECT version_no FROM vocabulary_version
                       WHERE vocab_version_id = :new_vocab_version_id
                         AND tenant_id = :tenant AND dimension = :dimension);

-- 【C4-2】单独输出"待人工归类"清单:vocab_version_id IS NULL 的标签(human 补的/历史脏数据),
--          这些最需要进复核,绝不能被 INNER JOIN 静默吞掉
SELECT DISTINCT t.asset_id
FROM tag t
JOIN asset a ON a.asset_id=t.asset_id AND a.tenant_id=t.tenant_id AND a.deleted_at IS NULL
WHERE t.tenant_id=:tenant AND t.dimension=:dimension AND t.status='active'
  AND t.vocab_version_id IS NULL;
```

- 【C4-1】补 `vv.tenant_id`/`vv.dimension` 谓词:`version_no` 按(租户,维度)独立自增,跨维度比大小无意义,不能靠"恰好指向同维度"的无约束假设。
- 主命中集 asset_id → 生成新 task(`task_type='tagging'`,新 config/vocab 版本)批量重打;**老标签保留不覆盖**(历史可追),证据见 scenario 场景 2。【不变量二】

### 查询③:某租户本月 token 用量 【不变量一、二、五 / C5 / Q6】

计费 = 溯源 token 按租户/时间聚合,不另建计量系统。

```sql
-- 租户侧(常规路径):必须带 tenant 谓词。租户中间件强制注入,租户侧 API 永远发不出无 tenant 谓词的查询
SELECT date_trunc('day', created_at) AS day,
       count(*)              AS n_calls,
       sum(input_tokens)     AS in_tok,
       sum(output_tokens)    AS out_tok
FROM task
WHERE tenant_id = :tenant
  AND task_type = 'tagging'
  AND created_at >= :start AND created_at < :end
GROUP BY 1 ORDER BY 1;
```

- **【Q6】** failed 任务与重试消耗的 token **全部计入用量统计**(成本真实发生);是否据此向租户收费属"计费口径",将来单独定义。用量统计 ≠ 计费口径,文档明确区分。
- **【C5】平台级跨租户聚合**(去 tenant 谓词、`GROUP BY tenant_id`)是**跨租户访问**,宪法要求"显式声明 + 留审计"。因此:此类查询**禁止经租户侧 API**,须走**独立于租户中间件的"平台侧入口"**,且调用时落 `sensitive=true` 审计事件。文档级不写成"顺手去掉 tenant 过滤",防止蔓延成代码级随意。【不变量一】

---

## 5. 索引与约束小结

- 每张业务表首列 `tenant_id` 且入组合索引首位——租户过滤是所有查询前缀。【不变量一】
- 去重:`asset (tenant_id, content_hash)` 唯一;**【加固1】** `asset (asset_id, tenant_id)` 唯一 + 下游 `(asset_id, tenant_id)` 复合外键,跨租户挂图库层不可能。
- **【C3 + 裁决八】溯源强制用 CHECK 分级,不用列级 NOT NULL:** `tag_provenance_by_source` —— `source='model'` 的标签五项溯源(model_id/prompt_version/config_version_id/run_id/input_hash)第一天强制非空;`vocab_version_id` 按维度双向:受约束维(structure/color/scene)必非空、自由文本维(theme/color_scheme)必为空(禁止给自由文本维伪造词表锚点,仿 N2 role 双向)。`source='human'` 补的标签天然无模型溯源,CHECK 按 source 放行。DDL 变更走 alembic `0003`(设计冻结后首次修订,基线 v3→v3.1)。**删除原 §6"migrated 放宽"条款**:按 migration §2.3/§3.4,评测 run 产物不入生产库、存量图用生产配置重打溯源写全,根本不存在"会入库的溯源不全迁移标签",放宽对象不存在。
- **【C6】** `event` actor CHECK;**【加固2】** `event` 迁移脚本 `REVOKE UPDATE, DELETE`。
- **【C1】** `tag.status` + `tag_correction.kind` + CHECK 承载改值/删标/补标/恢复四类操作,原始值永不销毁。

## 6. 裁决落定(原 §6 待裁决点,已按裁决记录关闭)

| 原裁决点 | 裁决结果(已执行) |
|---|---|
| 「红金」落库粒度 | 【裁决二】红/金作为 color 维 concept_key 存(带 role);`scheme_name`"红金"落**独立维度 `color_scheme`** 自由文本,不混入 color,避免污染单色统计与筛选 |
| 溯源 NOT NULL 时机 | 【C3】删 migrated 放宽,改 CHECK 按 source 分级,第一天强制 |
| RLS vs 应用层 | 【加固3】留位不启用 + 补集成测试:**无租户上下文的查询路径必须失败**(应用层过滤方案的唯一安全网),见 [migration.md](./migration.md) §4 / architecture §3.1 |
| 多值维度多行 vs 数组 | 同意多行(GIN 单值索引 + 修正链挂载 + status/role 逐值可控),理由成立 |
| Q1 主色/辅色 | 【裁决二】保留,`tag.role` 承载,默认检索按 `role='primary'` |
| tag.value 语义 | 【C2/方案A】受词表约束维度存 concept_key,theme/color_scheme 自由文本 |

> **【加固3】RLS 配套测试(纪律)**:即便本期用应用层 `tenant_id` 过滤,也须有一条集成测试断言"缺租户上下文 → 查询失败/被拒",作为不变量一的安全网;RLS 结构留位、暂不启用。
