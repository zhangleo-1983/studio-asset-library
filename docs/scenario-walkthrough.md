# balloon-platform 场景端到端走查

> 状态:**R02 二审返修稿(v3)**,对应《裁决记录》裁决三;v2 基础上按 N1(场景2 supersede 收敛)、N3(config 锁定词表版本)、N4(场景1 原始值口径)返修。
> 目的:矩阵证明"想到了",走查证明"接得住"。以下三场景逐一给出**每张表的前后行状态**,用真实字段值书写(数据虚构,字段不虚构)。口径与 [data-model.md](./data-model.md) v3、[migration.md](./migration.md) §1.2【A-3 定稿】concept_key 一致。
>
> **公共背景(三场景共用):**
> - 租户:`tenant_id=1`(示例客户,slug=`demo_tenant`);平台保留 `tenant_id=0`。
> - 用户:`user_id=5`(审核员 reviewer,示例客户);`user_id=1`(初始 admin)。
> - 资产:`asset_id=1001`(content_hash=`a1b2…`,storage_key=`1/1001/original.jpg`,deleted_at=NULL)。
> - 词表版本:`vocab_version_id=101`(tenant=1, dimension=structure, version_no=1,含 column/arch/flowerbox)。
> - 配置版本:`config_version_id=201`(scope=tagging, prompt_version=`tagging_v2`, prompt_sha256=`9f8e…`)。

---

## 场景 1:审核员删除一条模型误打的标签(幻觉出的"拱门")【C1】

**剧情:** 打标任务 `task_id=3001`(run_id=`init_20260705`)对 `asset_1001` 输出 structure=立柱 + structure=拱门。画面实际只有立柱,"拱门"是模型幻觉。审核员 `user_id=5` 在复核队列删除该错标。

### 打标完成后、删除前(基线)

**tag** — 两行 active:

| tag_id | tenant | asset | dim | value | role | status | source | model_id | vocab_ver | config_ver | run_id | confidence | needs_review | current_correction_id |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 9001 | 1 | 1001 | structure | `column` | ∅ | active | model | qwen-vl-max | 101 | 201 | init_20260705 | 0.970 | false | ∅ |
| 9002 | 1 | 1001 | structure | `arch` | ∅ | active | model | qwen-vl-max | 101 | 201 | init_20260705 | 0.550 | true | ∅ |

**tag_correction** — 空(尚无修正)。 **event** — 一条 `tagging_done`(actor_kind=system,actor_user_id=∅,合法:CHECK 允许 system 无 user)。

### 审核员删除 tag 9002 后

**tag** — 9002 行**不 DELETE**,状态迁移(9001 不动):

| tag_id | value | status | current_correction_id | 说明 |
|---|---|---|---|---|
| 9001 | `column` | active | ∅ | 未受影响 |
| 9002 | `arch` | **removed** | **7001** | 原始值 `arch`、溯源、confidence 全部保留,仅退出检索 |

**tag_correction** — 新增 1 行(只增):

| correction_id | tenant | tag_id | kind | old_value | new_value | source | corrected_by | corrected_at | reason |
|---|---|---|---|---|---|---|---|---|---|
| 7001 | 1 | 9002 | `remove` | `arch` | ∅ | human | 5 | 2026-07-05T09:12Z | 画面无拱门,模型幻觉 |

> CHECK `correction_shape` 放行:`kind='remove'` 要求 `new_value IS NULL` ✅。

**event** — 新增 1 行(只增):

| event_id | tenant | event_type | actor_kind | actor_user_id | sensitive | subject_type | subject_id | payload |
|---|---|---|---|---|---|---|---|---|
| 8005 | 1 | `correction` | human | 5 | false | tag | 9002 | `{"kind":"remove","dimension":"structure","value":"arch"}` |

> CHECK `event_actor_present` 放行:human 且 actor_user_id=5 非空 ✅。sensitive 由 `record_event()` 按 event_type 推导(correction→false)【Q7】。

### 检索如何排除该标签

查询①风格谓词一律带 `status='active'`:

```sql
-- 找"造型=立柱"的图:9002 因 status='removed' 不参与
SELECT 1 FROM tag t WHERE t.tenant_id=1 AND t.asset_id=1001
  AND t.status='active' AND t.dimension='structure' AND t.value='arch';
-- → 0 行。asset_1001 不再出现在"拱门"检索结果里
```

### sync_corrections 扫描如何分类为 REMOVED

回流 diff 直接读 `tag.status`:`tag_id=9002` 现为 `removed`,当前 active 值集合里无对应替代 → 归类 **REMOVED**(migration §2.2【C1 对齐】)。
> **【N4】原始值口径自洽:** 9002 只被 `remove` 过、从无 `update`,故其**原始值 = `tag.value` = `arch`**(remove 不改 value);同时 correction 7001 的 `old_value='arch'`(N4 收紧后 remove 强制记删除时当前值)。两处一致——data-model §3.6 "原始值 = 最早一行 update 的 old_value;无 update 时 = tag.value" 完整覆盖此例,不再两文各说半句。删标未销毁原值,回流可稳定复现该分类。

---

## 场景 2:词表 structure 维 v1→v2(新增概念"背景墙"),定位并重打受影响标签 【C4 / 不变量二】

**剧情:** 运营发现"背景墙"造型缺词表条目,词表管理页新增 `backdrop`,生成 structure 维 v2。需定位用 v1 打的 structure 标签并重打。

### 词表升级:vocabulary_version 新增行(只增)

| vocab_version_id | tenant | dimension | version_no | created_by | note |
|---|---|---|---|---|---|
| 101 | 1 | structure | 1 | 1 | migrated from balloon-tagging-eval(**保留不动**) |
| **140** | 1 | structure | **2** | 5 | 新增 backdrop(背景墙) |

**vocabulary** 新增 1 行:`vocab_id=520, dimension=structure, concept_key=backdrop, labels={"zh":"背景墙"}, vocab_version_id=140`(column/arch/flowerbox 的 v2 条目按迁移策略复制进 v140,concept_key 不变)。

**event** — 新增 `config_change`(actor=5, sensitive=**true**,词表变更属敏感)。

### 查询②(修正版)命中集

```sql
-- 主命中集:structure 维、用早于 v2 的版本打的、资产未软删的 active 标签
SELECT DISTINCT t.asset_id
FROM tag t
JOIN asset a ON a.asset_id=t.asset_id AND a.tenant_id=t.tenant_id AND a.deleted_at IS NULL   -- 【C4-3】
LEFT JOIN vocabulary_version vv ON vv.vocab_version_id=t.vocab_version_id
     AND vv.tenant_id=1 AND vv.dimension='structure'                                          -- 【C4-1】
WHERE t.tenant_id=1 AND t.dimension='structure' AND t.status='active'
  AND vv.version_no < (SELECT version_no FROM vocabulary_version
                       WHERE vocab_version_id=140 AND tenant_id=1 AND dimension='structure');
-- 命中:tag 9001(vocab_ver=101,version_no=1 < 2)→ asset_id=1001
-- 注意:tag 9002 已 status='removed',不进重打(正确——已知是幻觉,不该复活)
```

**【C4-2】待人工归类清单(单独输出):** `vocab_version_id IS NULL` 的 structure 标签 → 本例为空;若存在 human 补的背景墙标签(无 vocab_ver),会在此单列,不被静默吞掉。

### 新 task 批次 + 老标签保留 + 验收后 superseded 收敛【N1/裁决五】

对命中的 `asset_1001` 生成重打任务。**【N3】词表版本经 config 锁定**:`config_version_id=202` 的 `payload.vocab_versions.structure=140`,批次内不变——这就是"config 引用 vocab_ver=140"的落点。

| task_id | task_type | asset_id | run_id | config_version_id | 说明 |
|---|---|---|---|---|---|
| 3050 | tagging | 1001 | `retag_structure_v2_20260706` | 202(payload.vocab_versions.structure=140) | 用 v2 词表重打 |

**阶段一 · 验收前(新老并存,供人工对比):** 重打**新增** tag 行,**不 UPDATE/DELETE 老行**:

| tag_id | value | status | vocab_ver | run_id | 说明 |
|---|---|---|---|---|---|
| 9001 | `column` | active | **101** | init_20260705 | 老标签原样保留(v1) |
| 9101 | `column` | active | **140** | retag_structure_v2_20260706 | 新打标(v2) |

**阶段二 · 人工验收通过后(系统自动收敛)【N1】:** 系统对同 `(asset_id=1001, dimension=structure)` 且 vocab_version 早于本批的 active 标签(9001)批量置 `superseded`:

| tag_id | value | status | current_correction_id | 说明 |
|---|---|---|---|---|
| 9001 | `column` | **superseded** | 7010 | 退出检索,原行/value/溯源永久保留 |
| 9101 | `column` | active | ∅ | 现役 |

**tag_correction** 新增(只增,source=model):

| correction_id | tag_id | kind | old_value | new_value | source | corrected_at |
|---|---|---|---|---|---|---|
| 7010 | 9001 | `supersede` | ∅ | ∅ | model | 2026-07-06T10:00Z |

> CHECK `correction_shape` 放行:`kind='supersede'` 要求两值皆空 ✅(supersede 不改 value,故 9001 原始值 `column` 恒在 `tag.value`)。**event** 落一条 `config_change`/`correction`(actor_kind=system)。检索只查 `active` → 只命中 9101,**同值不双计、异值不让旧值继续命中**,重打目的完整达成。这补齐了 R01 走查暴露、二审 N1 指出的收敛机制空洞。【不变量二】

---

## 场景 3:第二个租户接入(纸面推演)—— 业务代码零改动 【不变量一/三/四/五】

**剧情:** 第二个租户"气球梦工厂"(slug=`qqmgc`)接入。全过程 = **插入数据行**,不改一行业务代码。

### 需要新增的行清单

**tenant** — 1 行:

| tenant_id | slug | display_name | industry | status |
|---|---|---|---|---|
| **2** | qqmgc | 气球梦工厂 | balloon_party | active |

**app_user** — 1 行(该租户初始 admin):

| user_id | tenant_id | username | role | 说明 |
|---|---|---|---|---|
| 20 | 2 | admin@qqmgc | admin | 密码哈希省略;小程序用户后续按 wx_openid 增 |

**vocabulary_version + vocabulary** — 词表种子(可复制示例客户的 concept_key 起步,或空表冷启动):

| vocab_version_id | tenant_id | dimension | version_no | 说明 |
|---|---|---|---|---|
| 300 | **2** | structure | 1 | 种子:column/arch/flowerbox |
| 301 | **2** | color | 1 | 种子:17 色 concept_key |
| 302 | **2** | scene | 1 | 种子:8 场景 concept_key |

> concept_key 是跨租户可复用的稳定键;`vocabulary` 行按 tenant_id=2 各插一份(labels.zh 相同,但版本与 vocab_id 独立)。租户间词表演化互不干扰。

**config_version** — 1 行:`config_version_id=210, tenant_id=2, scope=tagging, payload={qwen-vl-max, few_shot:false, temperature:0, vocab_versions:{structure:300,color:301,scene:302}…}, prompt_version=tagging_v2, prompt_sha256=9f8e…`(提示词内容共用;`vocab_versions` 锁定租户 2 自己的种子版本【N3】)。

**event** — 每步各 1 条(tenant_id=2,actor=平台侧种子脚本):租户创建、用户创建、词表种子、配置创建。

**asset / task / tag / selection / export_job** — **0 行**(新租户尚无资产);结构对租户 2 完全一致,首次上传即按 `2/{asset_id}/...` 落存储。

### "业务代码零改动"逐条对应不变量

| 声明 | 靠什么保证 | 不变量 |
|---|---|---|
| 新租户数据自动隔离,无需改查询 | 每张表首列 `tenant_id`,租户中间件注入 `WHERE tenant_id=2`;查询语句本身不变 | 一 |
| 存储路径自动分租户 | key 规则 `{tenant_id}/{asset_id}/...`,`StorageBackend` 不变,只是 tenant_id=2 | 一、三 |
| 跨租户挂图库层不可能 | `asset(asset_id, tenant_id)` 复合唯一 + 下游复合外键;租户 2 的 tag 无法挂租户 1 的 asset | 一【加固1】 |
| 打标链路不变 | `task_type='tagging'` 与输出 schema 与租户无关;新增租户不新增 task_type | 四 |
| 溯源/事件结构不变 | tag 溯源 CHECK、event actor CHECK 对所有租户一致 | 二、五 |
| 物理独立部署(若该租户要求) | 同一镜像 + 独立 compose + 独立库/Bucket,复制交付,业务代码零改动 | 一、三 |

> 结论:第二租户接入 = 数据操作 + 一次种子迁移(migration §4 步骤 0 的租户级重放),**零业务代码改动**。这正是"多租户设计、单租户交付"的兑现。
