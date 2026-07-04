# balloon-platform 旧资产迁移清单

> 状态:**设计草案,待技术合伙人评审**。
> 来源:旧项目 `balloon-tagging-eval`(已退役为资产库,不再开发)。
> 原则:迁移只搬**已验证的资产与结论**,不搬旧项目的临时脚本与一次性 run 产物。目标结构见 [data-model.md](./data-model.md)。

---

## 0. 一句话

从旧项目搬三类东西:**① 打标"知识"**(提示词 / 词表 / alias_map / 锁定的生产配置)、**② 溯源与修正设计**(original_tags / sync_corrections 的机制,数据源换成事件流水+修正链)、**③ 客户 NAS 存量图 2–3 万张**(一次性上云,断点续传 + 内容 hash 去重)。

---

## 1. 打标"知识"资产迁移

### 1.1 打标提示词 → `prompt_version` + 配置

- **来源:** `prompts/tagging.txt`(四维:主题/配色/造型/场景 + suggested_filename/confidence/needs_review/notes)。
- **动作:** 原文迁入新仓库 `prompts/tagging_v2.txt`,登记 `prompt_version = 'tagging_v2'`。提示词里 `{{COLOR_VOCAB}}` / `{{STRUCTURE_VOCAB}}` 占位符改为**从 `vocabulary` 表按当前版本注入**(旧项目从 YAML 注入,新平台从库注入),注入所用的 `vocab_version_id` 写进标签溯源。【不变量二】
- **判分裁判提示词** `prompts/judge_theme.txt`(theme 语义等价裁判)属评测期工具,**本期不迁入生产路径**,归档到 roadmap 的"评测能力"阶段。

### 1.2 structure / colors 词表 → `vocabulary` 表

| 旧文件 | 内容 | 迁入 |
|---|---|---|
| `data/vocab/structure_types.yaml` | `enum: [立柱, 拱门, 花盒]` | `vocabulary` dimension=structure,3 条,concept_key=column/arch/flowerbox,`labels={"zh":"立柱"…}` |
| `data/vocab/colors.yaml` | `simple:[粉白红蓝绿黄紫黑银金]` `compound:[多巴胺,珠光白,珠光粉,铬玫瑰金,铬香槟金,木瓜黄,铬金]` | `vocabulary` dimension=color,`color_kind` 区分 simple/compound |

- 首次迁入即生成各维度 `vocabulary_version` 的 `version_no=1`,`note='migrated from balloon-tagging-eval'`。
- 多语言:`labels` 本期只填 `zh`,结构留位 `en` 等。【不变量三 — 留位不实现】
- scene 枚举(`生日宴/寿宴/宝宝宴/商场美陈/校园活动/开业/婚礼/其他`)旧项目写死在 schema+prompt,新平台**也迁成 `vocabulary` dimension=scene**,消除旧项目"scene 改词表要动两个地方"的痛点(见旧 sync_corrections 对 scene 的特殊处理)。

### 1.3 alias_map → `alias_map` 表

- **来源:** `data/vocab/alias_map.yaml`,按字段分区(structure/theme/color/scene),已有一条 `structure: 气球花盒 → 花盒`。
- **动作:** 逐条迁入 `alias_map` 表,`source='human'`(存量视为人工维护)。冲突/成环校验规则(旧 `apply_alias` 的拒绝逻辑)在新平台的回流写入路径里保留。【见 §2.2】

### 1.4 生产配置(评测锁定)→ `config_version`

旧项目 `config.yaml` + `CLAUDE.md` 锁定的生产结论,迁成首个 `tagging` scope 的 `config_version.payload`:

```json
{
  "model": "qwen-vl-max",
  "few_shot": false,
  "temperature": 0,
  "image_max_edge": 1568,
  "max_retries": 3,
  "concurrency": 2,
  "resume": true,
  "provider": "aliyun_bailian",
  "note": "锁定于 2026-07-03:83 张全量评测 structure 判错率 3.6%,优于 gemini 4.8% 且更快更省;few-shot 三轮实验判错率反涨至 10.8–13.3% 已关闭"
}
```

- **硬约束(迁移纪律):** few-shot 保持关闭。旧项目 `CLAUDE.md` 明确"不要为了试试看重开 few-shot",重开需先满足 `prompts/fewshot/README.md` 的重开条件。新平台默认无 few-shot。
- Gemini 配置仅作"能力上限对照"留档,不进生产 `config_version`。

### 1.5 schema 兜底逻辑(必须迁,别删)

旧项目 `CLAUDE.md` 第 5 条:模型输出经常不严格守 schema。两个兜底函数必须迁入新平台的打标结果解析层:

- `coerce_theme_str` — theme 偶尔被包成 `{"name":…,"theme_type":…}` 而非字符串。
- `coerce_str_list` — `color_scheme.primary` / `structure_types` 偶尔是裸字符串而非数组,直接 join 会把"多巴胺"拆成"多+巴+胺"。

> 迁移风险提示:任何读取 Qwen 输出四维字段的新代码,都要先过这两个兜底函数,不能假设输出严格符合 `tagging_output_v2` schema。

### 1.6 输出 schema → `output_schema_version = 'tagging_output_v2'`

- **来源:** `schema/output_schema.json`(title `balloon_tagging_output_v2`)。
- **动作:** 迁成 pydantic 模型 + JSON Schema 双份,版本号 `tagging_output_v2`,存于 `task.output_schema_version`。字段完全沿用(image_id/theme/theme_type/color_scheme{primary,accent,scheme_name}/structure_types/scene_guess/suggested_filename/confidence/needs_review/notes)。

---

## 2. 溯源与修正设计迁移

### 2.1 original_tags 设计 → 修正链的"原始值"

- **旧设计:** `db.py` 的 `original_tags`(SQLite)记录"工具当初往 Eagle 写了什么",作为 diff 基准;`latest_original_tags` 取每个 (item_id, field) 最近 run 的值。
- **新设计:** 不再需要独立快照表。**原始值 = `tag_correction` 里该 tag 最早一行的 `old_value`;从未修正时 = `tag.value`**。溯源的 `run_id` 承担旧 `original_tags.run_id` 的角色。【不变量二 — 原始值永久保留在修正链】

### 2.2 sync_corrections 设计 → 数据源改为事件流水 + 修正链

**保留旧算法,替换数据源。** 旧 `sync_corrections.py` 的 diff 逻辑与人工闸门原样迁移:

| 旧项目 | 新平台 |
|---|---|
| 数据源:Eagle 当前标签 vs `original_tags` 快照 | 数据源:`tag` 当前值 vs 修正链原始值(纯库内 diff,无外部 Eagle) |
| `diff_item` 四字段分类:RENAMED / ADDED / REMOVED / 人工补漏 | **算法不变**,逐字段比对当前值集合 vs 原始值集合 |
| RENAMED(1:1 且新值在词表内)→ 建议进 alias_map | 不变;写入走 `alias_map` 表 |
| ADDED(新值不在词表)→ 建议扩 vocab | 不变;写入生成新 `vocabulary_version` |
| REMOVED(删除无替代)→ 写 `error_cases`(SQLite) | 改为落 `event`(event_type='correction' 的子类)+ 可选一张 `error_case` 视图,不再单建 SQLite |
| 两阶段:扫描只读产 CSV → `--apply` 写规则 | **两阶段人工闸门保留**;apply 落"配置变更"事件,取代旧 `applied_rules_log` |
| `apply_alias` 冲突/成环拒绝自动写 | **保留**:冲突(别名已映射到不同标准值)/ 成环(A→B→A)拒绝,交人工裁决 |
| scene 需人工改 schema+prompt | 消解:scene 迁成 `vocabulary`,回流可正常扩表 |

> 迁移工作量提示(架构文档 §9 冲突点 3):diff 的**数据来源部分需重写**(从读 Eagle 改为读库),分类算法与闸门逻辑可整段移植。这是迁移成本,非原则冲突。【不变量五】

### 2.3 不迁的旧资产(明确排除)

- `src/eagle_client.py` / `push_to_eagle.py` — Eagle 专用,新平台无 Eagle(小程序+Web 替代),不迁。`FIELD_PREFIX`(主题:/配色:/造型:/场景:)的"前缀标签"设计是 Eagle 单库无字段结构的妥协,新平台有 `tag.dimension` 列,**不需要前缀**。
- `runs/**` — 一次性评测产物(报告、对照表、确认包、renamed_output),归档留档,不入生产库。
- `src/rename_demo.py` / `parse_filenames.py` / `run_eval.py` / `score.py` / `acceptance_report.py` — 评测期工具,不进生产;其中 `score.py` 的两个兜底函数按 §1.5 单独抽取迁移。
- `prompts/fewshot/*.disabled` — 已关闭的 few-shot 样例,归档,不启用。

---

## 3. 客户 NAS 存量图一次性上云(约 2–3 万张)

> 数量以实际为准(旧项目 `CLAUDE.md` 第 7 条教训:不要照抄文档假设数字,先 `find | wc -l` 核实)。评测期实测原图库仅 83 张;交付方案口径 2–3 万张历史图,迁移前先核数。

### 3.1 迁移管线(设计)

```text
NAS 扫描 ──→ 内容 hash(sha256) ──→ 去重判定 ──→ 上传 OSS ──→ 建 asset 记录 ──→ (可选)入队打标
   │              │                    │            │              │
 逐文件遍历    读文件算 hash        库内 hash 命中?  {tenant}/{asset}/  写 asset 表      task_type=tagging
 记进度清单    (大小写不敏感*)      命中→跳过登记别名  original.ext      + 上传 event      批量执行
```

### 3.2 断点续传

- **迁移清单表/文件:** 每个源文件一行,记 `源路径 / sha256 / 状态(pending|uploaded|registered|skipped_dup|failed) / oss_key / asset_id / 错误`。管线启动先读清单,`uploaded/registered/skipped_dup` 的跳过——即旧项目 `resume: true` 的思路放大到迁移。
- **幂等:** 上传 OSS 用 `{tenant_id}/{asset_id}/original.ext` 确定性 key;asset 写库靠 `(tenant_id, content_hash)` 唯一约束天然幂等,重跑不产生重复。
- **分批与验收:** 沿用交付方案"分批打标、分批验收"节奏,迁移也分批(如按 NAS 目录/日期),每批出一份"入库数/去重数/失败数"小结。

### 3.3 内容 hash 去重(与不变量三对齐)

- 去重键 = `sha256(文件字节)`,**不依赖文件名/路径**。【不变量三】
- 大小写陷阱(旧 `CLAUDE.md` 第 3 条:macOS/Windows 大小写不敏感文件系统,`a.JPG` 与 `a.jpg` 是同一文件,曾静默覆盖丢 2 张):去重只按内容 hash,不按文件名;但**导出/落盘生成文件名时,判重要 `.lower()` 后再比**,该教训迁入导出模块。
- 重复文件不丢弃信息:命中已存在 asset 时,把源路径/原名记入该 asset 的 `original_name` 或迁移清单,便于溯源"这张图在 NAS 哪几处出现过"。
- 特殊格式:iPhone `.HEIC` 需 `pillow_heif` 解码(旧 `providers.py` 已引入);上云保留原图,另生成 JPEG 缩略图供小程序图墙。

### 3.4 迁移期溯源标记

- 存量图历史无打标,上云后统一入队用**当前生产配置**(qwen-vl-max / 无 few-shot / temperature=0)打标,标签溯源正常写全字段。
- 若将来迁入"旧项目已打过的标签数据"(评测 run 产物),这批标签溯源字段不全,按 [data-model.md](./data-model.md) §6 裁决点 2 标 `source='migrated'`,与生产标签区分,溯源 NOT NULL 约束对其放宽。【不变量二】

---

## 4. 迁移执行顺序(评审通过后)

1. 建库骨架 + 迁移 §1.2/§1.3/§1.4 词表·alias·配置(小、可先行、可校对)。
2. 迁移 §1.1 提示词 + §1.5/§1.6 schema 与兜底函数,打通单张打标闭环。
3. NAS 核数 → §3 存量图分批上云 + 去重入库。
4. 存量图批量打标 → 复核队列 → 人工修正闭环。
5. §2.2 修正回流(数据源改造)在有真实修正数据后接入。

> 全部待评审通过后开始;本文仅为迁移设计,不含任何执行。
