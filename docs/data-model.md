# balloon-platform 数据模型草案

> 状态:**设计草案,待技术合伙人评审**。评审通过前不建表、不写迁移。
> 宪法:[PRINCIPLES.md](../PRINCIPLES.md)。每张表逐条核对五个不变量,见 §2 的合规矩阵。
> DDL 用 PostgreSQL 方言书写,仅表达结构意图,非最终迁移脚本。命名统一 snake_case,时间戳一律 `timestamptz`(UTC)。

---

## 1. 全表清单

| 表 | 作用 | 只增? |
|---|---|---|
| `tenant` | 租户 | 否 |
| `app_user` | 用户(Web 用户名密码 / 小程序 openid),归属租户 | 否 |
| `asset` | 资产元数据(图片),以 asset_id + 内容 hash 关联对象存储 | 否(可软删) |
| `task` | 通用任务表(task_type 开放),一次 AI 操作一行 | 否(状态可变) |
| `tag` | 标签(每条带完整溯源 + 修正链头) | 否(修正走 tag_correction) |
| `tag_correction` | 标签修正链(只增,人工修正不覆盖原值) | **是** |
| `vocabulary` | 词表条目(structure/colors…),概念级、预留多语言 | 否 |
| `vocabulary_version` | 词表版本(升级定位/批量重打的依据) | **是**(版本只增) |
| `alias_map` | 输出归一化:别名 → 标准值,按字段分区 | 否 |
| `config_version` | 打标/复核等配置的版本快照(溯源引用) | **是** |
| `event` | 业务事件流水(唯一事件承重墙) | **是** |
| `selection` / `selection_item` | 选图篮(小程序),选图/转发行为的载体 | 否 |
| `export_job` | 数据导出任务记录 | 否 |

> 运维日志(报错/延迟)**不在此**——走标准 logging,不入业务库。【不变量五】

---

## 2. 五不变量合规矩阵(逐表核对)

| 表 | ①tenant_id | ②溯源全字段 | ③资产/标签分离 | ④task_type 开放 | ⑤事件只增/actor/时间戳 |
|---|:--:|:--:|:--:|:--:|:--:|
| tenant | 自身即租户 | — | — | — | — |
| app_user | ✅ | — | — | — | — |
| asset | ✅ | 上传溯源(uploader/hash/time) | ✅ 以 asset_id+hash 关联存储 | — | 上传落 event |
| task | ✅ | run_id/config_version/token/model | 引用 asset_id 非路径 | ✅ task_type 普通列 | 完成落 event |
| tag | ✅ | ✅ 全字段(见 §3.5) | ✅ 挂 asset_id | 由 task 承载类型 | 修正落 event |
| tag_correction | ✅ | ✅ source/corrected_by/at/原值 | ✅ | — | 每条修正落 event |
| vocabulary | ✅ | 版本号 | — | — | 编辑落 event |
| vocabulary_version | ✅ | ✅ 版本即溯源锚点 | — | — | 升级落 event |
| alias_map | ✅ | 来源(人工/回流) | — | — | 变更落 event |
| config_version | ✅ | ✅ 配置快照被标签引用 | — | 配置可含 task_type | 变更落 event |
| event | ✅ | — | — | event_type 开放 | ✅ 只增/actor/occurred_at |
| selection* | ✅ | — | 引用 asset_id | — | 选图/转发落 event |
| export_job | ✅ | 导出参数快照 | 打包引用 asset_id | — | 导出落 event(sensitive) |

---

## 3. 核心表 DDL(草案)

### 3.1 tenant / app_user 【不变量一】

```sql
CREATE TABLE tenant (
    tenant_id     BIGINT PRIMARY KEY,           -- 0 保留给平台公共库;不用 NULL 承载"无租户"
    slug          TEXT UNIQUE NOT NULL,          -- 如 'demo_tenant'
    display_name  TEXT NOT NULL,                 -- '示例工作室'
    industry      TEXT NOT NULL DEFAULT 'balloon_party',  -- 首个行业
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app_user (
    user_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     BIGINT NOT NULL REFERENCES tenant(tenant_id),
    -- 双通道账号:Web=用户名密码;小程序=微信 openid。二者归一到"用户属某租户"
    username      TEXT,                          -- Web 端;租户内唯一
    password_hash TEXT,
    wx_openid     TEXT,                          -- 小程序端
    role          TEXT NOT NULL DEFAULT 'operator',  -- operator | reviewer | admin(租户内角色,非平台角色)
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, username),
    UNIQUE (tenant_id, wx_openid)
);
```

> 账号体系是隔断墙(第一版可简化),但 `tenant_id` 无特例。【不变量一】

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
    -- 对象存储 key 由 {tenant_id}/{asset_id}/... 规则推导,不作为业务依赖;此处仅缓存便于运维
    storage_key    TEXT NOT NULL,
    original_name  TEXT,                          -- 仅导出展示用,不承载任何业务逻辑
    uploaded_by    BIGINT REFERENCES app_user(user_id),
    uploaded_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at     timestamptz,                   -- 软删;删除落 event
    UNIQUE (tenant_id, content_hash)              -- 同租户内容去重
);
CREATE INDEX asset_tenant_idx ON asset (tenant_id) WHERE deleted_at IS NULL;
```

> 关键:业务只用 `asset_id` + `content_hash`。`storage_key` 是可再生的缓存字段,换存储供应商时按规则重算即可,业务层零改动。【不变量三】

### 3.3 task — 通用任务表(task_type 开放)【不变量四】

```sql
CREATE TABLE task (
    task_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    task_type      TEXT NOT NULL,                 -- 本期仅 'tagging';未来 bom_extract/audit/… 直接加值,不改表
    asset_id       BIGINT NOT NULL REFERENCES asset(asset_id),  -- 输入资产(引用非路径)
    run_id         TEXT NOT NULL,                 -- 批次号,批量执行/断点续跑的键
    status         TEXT NOT NULL DEFAULT 'pending', -- pending|running|done|failed|needs_review
    config_version_id BIGINT REFERENCES config_version(config_version_id),
    output         JSONB,                         -- 按 task_type 各自定义的结构化输出(tagging=四维标签原始 JSON)
    output_schema_version TEXT,                   -- 如 'tagging_output_v2'
    -- 溯源:代价与来源(token/model/耗时)
    model_id       TEXT,                          -- 如 'qwen-vl-max'
    input_tokens   INT,
    output_tokens  INT,
    latency_ms     INT,
    error          TEXT,
    created_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz
);
CREATE INDEX task_tenant_type_idx ON task (tenant_id, task_type, status);
CREATE INDEX task_run_idx ON task (tenant_id, run_id);
```

> `task_type` 是普通字符串列,`output` 是 JSONB —— 新增任务类型不改表结构,只加新 `task_type` 值 + 新 `output_schema_version`。**不建任何插件/编排框架。**【不变量四"禁止"条款】

### 3.4 vocabulary / vocabulary_version / alias_map — 词表 【不变量二、三】

```sql
-- 词表版本:每次编辑生成新版本号,标签溯源引用它;升级后据此定位需重打的标签
CREATE TABLE vocabulary_version (
    vocab_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    dimension      TEXT NOT NULL,                 -- 'structure' | 'color' | 'scene'
    version_no     INT NOT NULL,                  -- 该维度下自增
    created_by     BIGINT REFERENCES app_user(user_id),
    created_at     timestamptz NOT NULL DEFAULT now(),
    note           TEXT,
    UNIQUE (tenant_id, dimension, version_no)
);

-- 词表条目:概念级,预留多语言映射位(本期只填 zh)
CREATE TABLE vocabulary (
    vocab_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    dimension      TEXT NOT NULL,                 -- structure | color | scene
    concept_key    TEXT NOT NULL,                 -- 概念稳定 id,如 'column'(立柱)、'arch'(拱门)
    -- 多语言留位:翻译发生在词表层,不在数据层;本期只存 zh。【不变量三】
    labels         JSONB NOT NULL,                -- {"zh":"立柱"} ；未来 {"zh":"立柱","en":"column"}
    color_kind     TEXT,                          -- color 维专用:'simple'(单字色)|'compound'(复合色),迁移自旧 colors.yaml
    active         BOOLEAN NOT NULL DEFAULT true,
    vocab_version_id BIGINT NOT NULL REFERENCES vocabulary_version(vocab_version_id),
    UNIQUE (tenant_id, dimension, concept_key, vocab_version_id)
);

-- 输出归一化:模型输出别名 → 标准概念。按字段分区,迁移自旧 alias_map.yaml
CREATE TABLE alias_map (
    alias_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    dimension      TEXT NOT NULL,                 -- structure|theme|color|scene
    alias          TEXT NOT NULL,                 -- 别名/变体,如 '气球花盒'
    standard_value TEXT NOT NULL,                 -- 标准值,如 '花盒'
    source         TEXT NOT NULL DEFAULT 'human', -- human | sync_corrections(回流自动追加)
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, dimension, alias)          -- 同字段同别名唯一,防冲突(旧逻辑:冲突/成环拒绝自动写)
);
```

### 3.5 tag — 标签溯源完整 【不变量二】

一条 AI 产出的标签,必须能回答"五问"。字段布局:

```sql
CREATE TABLE tag (
    tag_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    asset_id       BIGINT NOT NULL REFERENCES asset(asset_id),   -- 挂在资产上(非路径/文件名)【不变量三】
    task_id        BIGINT NOT NULL REFERENCES task(task_id),     -- 由哪个打标任务产生

    dimension      TEXT NOT NULL,                 -- 'theme'|'color'|'structure'|'scene'
    value          TEXT NOT NULL,                 -- 归一化后的当前值(经 alias_map)
    -- ── 溯源五问 ──────────────────────────────────────────
    -- 谁打的
    source         TEXT NOT NULL,                 -- 'model' | 'human'
    model_id       TEXT,                          -- 'qwen-vl-max'(含版本)
    -- 在什么规则下打的
    prompt_version TEXT,                           -- 提示词版本
    vocab_version_id BIGINT REFERENCES vocabulary_version(vocab_version_id), -- 词表版本
    config_version_id BIGINT REFERENCES config_version(config_version_id),
    -- 基于什么输入打的
    run_id         TEXT,                           -- 批次
    input_hash     TEXT,                           -- = asset.content_hash 快照,输入内容 hash
    -- 花了什么代价(token 用量按租户聚合即计费底层)
    input_tokens   INT,
    output_tokens  INT,
    -- 打分
    confidence     NUMERIC(4,3),                   -- 0.000–1.000
    needs_review   BOOLEAN NOT NULL DEFAULT false,
    -- 后来被谁改过:修正链头(最新一次修正指针,详情在 tag_correction)
    current_correction_id BIGINT,                  -- NULL=未被修正,当前即 model 原值
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tag_filter_idx  ON tag (tenant_id, dimension, value);   -- 维度筛选主力
CREATE INDEX tag_asset_idx   ON tag (tenant_id, asset_id);
CREATE INDEX tag_vocabver_idx ON tag (tenant_id, vocab_version_id);  -- 词表升级定位
```

> `value` 存归一化后的当前值;原始模型值永久保留在 `tag_correction`(见下),**人工修正不覆盖原值**。【不变量二】

### 3.6 tag_correction — 修正链(只增)【不变量二、五】

```sql
CREATE TABLE tag_correction (
    correction_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    tag_id         BIGINT NOT NULL REFERENCES tag(tag_id),
    old_value      TEXT NOT NULL,                 -- 修正前的值(第一次修正即 model 原值)
    new_value      TEXT NOT NULL,                 -- 修正后的值
    source         TEXT NOT NULL DEFAULT 'human', -- human | model(重打)
    corrected_by   BIGINT REFERENCES app_user(user_id),
    corrected_at   timestamptz NOT NULL DEFAULT now(),
    reason         TEXT
    -- 只增不改不删:一条 tag 的多次修正 = 多行,按 corrected_at 排即完整履历
);
CREATE INDEX tag_correction_tag_idx ON tag_correction (tenant_id, tag_id, corrected_at);
```

> 原始模型值 = `tag_correction` 中该 tag 最早一行的 `old_value`(或 tag 从未被修正时 = `tag.value`)。修正回流(sync_corrections)的 diff 基准即此,不再依赖旧项目的 `original_tags` 快照表。【不变量五】

### 3.7 config_version — 配置版本快照 【不变量二】

```sql
CREATE TABLE config_version (
    config_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    scope          TEXT NOT NULL,                 -- 'tagging' | 'review' | ...
    payload        JSONB NOT NULL,                -- 快照:{model, temperature, few_shot:false, image_max_edge, review_threshold,...}
    created_by     BIGINT REFERENCES app_user(user_id),
    created_at     timestamptz NOT NULL DEFAULT now()
);
```

> 生产打标配置(`qwen-vl-max` / 无 few-shot / `temperature=0` / `image_max_edge=1568`)作为首个 `tagging` scope 的 payload 落库,被每条标签 `config_version_id` 引用。【迁移自旧项目锁定配置】

### 3.8 event — 事件流水(唯一事件承重墙)【不变量五】

```sql
CREATE TABLE event (
    event_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),   -- 带 tenant
    event_type     TEXT NOT NULL,   -- upload|tagging_done|correction|selection|export|config_change|delete|...(开放)
    actor_user_id  BIGINT REFERENCES app_user(user_id),            -- 带行为人
    actor_kind     TEXT NOT NULL DEFAULT 'human',                  -- human|system(system 打标完成等)
    occurred_at    timestamptz NOT NULL DEFAULT now(),             -- 带时间戳
    sensitive      BOOLEAN NOT NULL DEFAULT false,                 -- true 子集 = 审计视图(导出全库/删除/配置变更)
    subject_type   TEXT,            -- 'asset'|'tag'|'vocabulary'|... 关联对象类型
    subject_id     BIGINT,
    payload        JSONB            -- 事件明细
    -- 只增不改不删:无 UPDATE/DELETE 入口,应用层与权限双重禁止
);
CREATE INDEX event_tenant_time_idx ON event (tenant_id, occurred_at);
CREATE INDEX event_audit_idx ON event (tenant_id, occurred_at) WHERE sensitive;
```

> 审计视图 = `WHERE sensitive`,不另建审计表;用量计费 = 从 `tag`/`task` 的 token 聚合,不另建计量系统。【不变量二、五】

### 3.9 selection / export_job(小程序选图 & 导出)

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
    asset_id       BIGINT NOT NULL REFERENCES asset(asset_id),   -- 引用 asset_id,非路径
    added_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (selection_id, asset_id)
);
CREATE TABLE export_job (
    export_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL REFERENCES tenant(tenant_id),
    requested_by   BIGINT REFERENCES app_user(user_id),
    kind           TEXT NOT NULL,                 -- 'tag_json' | 'tag_csv' | 'asset_zip'
    params         JSONB,                         -- 筛选条件快照
    status         TEXT NOT NULL DEFAULT 'pending',
    result_key     TEXT,                          -- 产物在对象存储的 key
    created_at     timestamptz NOT NULL DEFAULT now()
);
```

---

## 4. 三个典型查询走查

### 查询①:筛选「配色=红金 且 造型=立柱」的图 【不变量一、三】

`红金` 是配色的 `scheme_name` 语义,底层落成 color 维度的两个概念(`红`+`金`)或复合概念;此处按"造型含立柱 且 配色含红、含金"给出可执行 SQL。标签维度筛选 = `tag` 表自连接,GIN/BTree 索引支撑,**无需向量检索**。

```sql
-- 参数::tenant, 造型='立柱', 配色需同时含 '红' 与 '金'
SELECT a.asset_id, a.storage_key
FROM asset a
WHERE a.tenant_id = :tenant AND a.deleted_at IS NULL
  AND EXISTS (SELECT 1 FROM tag t WHERE t.tenant_id=a.tenant_id AND t.asset_id=a.asset_id
              AND t.dimension='structure' AND t.value='立柱')
  AND EXISTS (SELECT 1 FROM tag t WHERE t.tenant_id=a.tenant_id AND t.asset_id=a.asset_id
              AND t.dimension='color' AND t.value='红')
  AND EXISTS (SELECT 1 FROM tag t WHERE t.tenant_id=a.tenant_id AND t.asset_id=a.asset_id
              AND t.dimension='color' AND t.value='金');
```

- 走 `tag_filter_idx (tenant_id, dimension, value)`;每个 EXISTS 一次索引探测。
- `tenant_id` 全程带在每个子查询,跨租户不可能命中。【不变量一】
- 命中的是 `asset_id` → `storage_key` 取图,**不碰文件名/目录**。【不变量三】
- 若产品把「红金」作为 `scheme_name` 直接存了一条 color 标签,则退化为单个 EXISTS(`value='红金'`),更快。

### 查询②:词表升级后,找出需重打的标签 【不变量二】

词表某维度从 v3 升级到 v4(如新增造型概念、修订标准值)。需重打 = "用旧于 v4 的词表版本打的、该维度的标签"。

```sql
-- 参数::tenant, :dimension='structure', :new_vocab_version_id(v4 的 id)
SELECT DISTINCT t.asset_id
FROM tag t
JOIN vocabulary_version vv ON vv.vocab_version_id = t.vocab_version_id
WHERE t.tenant_id = :tenant
  AND t.dimension = :dimension
  AND vv.version_no < (SELECT version_no FROM vocabulary_version
                       WHERE vocab_version_id = :new_vocab_version_id);
-- 结果 asset_id 集合 → 生成一批 task(task_type='tagging', 新 config/vocab 版本),批量重打
```

- 全靠标签溯源里的 `vocab_version_id`;没有溯源就无法定位——这正是不变量二要求"版本号永久保留"的用途。【不变量二】
- 走 `tag_vocabver_idx`。重打即新建 task,老标签保留(历史可追),不覆盖。

### 查询③:某租户本月 token 用量 【不变量二、五】

计费 = 溯源里的 token 按租户/时间聚合,**不另建计量系统**。既可从 `task`(每次调用),也可从 `tag` 聚合;下例用 `task`(一次模型调用一行,最准)。

```sql
-- 参数::tenant, 本月区间 :start, :end
SELECT date_trunc('day', created_at) AS day,
       count(*)                     AS n_calls,
       sum(input_tokens)            AS in_tok,
       sum(output_tokens)           AS out_tok
FROM task
WHERE tenant_id = :tenant
  AND task_type = 'tagging'
  AND created_at >= :start AND created_at < :end
GROUP BY 1 ORDER BY 1;
-- 全租户总量:去掉 tenant 过滤并 GROUP BY tenant_id,即多租户计量报表底稿
```

- 走 `task_tenant_type_idx`。token 用量是"未来按量计费的底层",本期不做计费 UI,但数据从第一天就可聚合。【不变量二】

---

## 5. 索引与约束小结

- 每张业务表首列 `tenant_id` 且入组合索引首位——租户过滤是所有查询的前缀。【不变量一】
- 去重:`asset (tenant_id, content_hash)` 唯一。【不变量三】
- 溯源不可空的关键列(生产环境):`tag.model_id / prompt_version / vocab_version_id / config_version_id / run_id / input_hash`——评审确认后在迁移里加 `NOT NULL`(草案暂留可空以便回填历史迁移数据)。【不变量二 / 见 §6 待裁决】
- `event` 无 UPDATE/DELETE 路径,权限层回收这两个动作。【不变量五】

## 6. 待评审裁决点

1. **「红金」的落库粒度** — 存成一条 `scheme_name='红金'` 标签,还是拆成 `红`+`金` 两条 color 标签?二者查询写法不同(查询①已给两种)。建议**两者都存**:`scheme_name` 便于人看与转发,拆分色便于交叉筛选;代价是每图 color 维度多几条标签。
2. **溯源列 NOT NULL 的时机** — 新数据应强制非空;但迁移历史标签(旧项目产物)可能缺字段。建议:新写入路径强制,迁移数据放宽并标 `source='migrated'`。见 [migration.md](./migration.md)。
3. **RLS vs 应用层过滤** — 本期用应用层强制 `tenant_id` 过滤;是否第一天就上 PostgreSQL Row-Level Security?建议留位不启用(隔断墙允许后置),但表结构已就绪。
4. **多值维度是否用数组列** — `tag` 采用"一维度多行"而非数组列,利于 GIN 单值索引与修正链挂载;确认可接受。
