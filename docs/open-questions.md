# 挂账清单(open questions)

> 骨架阶段暴露、但不属骨架范围、需在对应阶段开工前先定的问题。设计冻结于
> design-freeze-v3;本清单只记账,不自行裁决。

---

## OQ-1 「当前生效配置」的选取规则未定义 —— ✅ 已关闭(裁决七,张亮 2026-07-05)

> **裁决七(2026-07-05 书面确认,按变更纪律归档):采纳方案二(显式生效指针)**;方案一(取最新
> `created_at`)、方案三(config_version 加 active 列)否决。落点:
> - DDL:新增小表 `active_config`(PK `(tenant_id, scope)`,唯一 `config_version_id` FK),alembic `0002`。
>   data-model.md §3.10【OQ-1/裁决七】。
> - 唯一推指针函数 `app/active_config.py::activate_config`:UPDATE 指针 + 必落 `config_activate` 事件
>   (`sensitive=true`,payload 带 `from`/`to`);回滚 = 指针回拨,事件可辨识。
> - `config_activate` 已入 `record_event` 的 sensitive 集中映射。
> - 当期配置/当期词表版本一律经 `current_config_version_id()` 解析;禁止取最新 `created_at`、禁止硬编码。
> - 本期产品口径:保存配置后系统自动推指针(效率模式,无审批);种子已在建配置后自动激活。
> - roadmap 二期候选:「质量模式开关 + 租户内审批流」,留位方式 = 本指针机制。
>
> 以下为裁决前的原始记账,存档。

### 原始记账（存档）

**背景:** `config_version` 是只增表(迁移已 `REVOKE UPDATE, DELETE`,实测生效)。种子写入首行
生产配置后,提示词/词表升级都以**新增一行 config_version**的方式演进,老行作为历史溯源锚点
永久保留、永不 UPDATE(不变量二)。

**缺口:** worker 取"该 tenant + scope=tagging 现在该用哪一行 config_version"时,选取规则尚未定义:

- 方案 A:按 `(tenant_id, scope)` 取 `created_at` 最新的一行(隐式"最新即生效")。
  风险:新增一行即刻改变生效配置,无显式启用动作,回滚也只能靠再插一行。
- 方案 B:加一个显式"当前生效指针"(如 `tenant_config_pointer(tenant_id, scope, config_version_id)`,
  该指针表可 UPDATE),启用/回滚 = 改指针 + 落 config_change 事件。语义清晰、可审计。
- 方案 C:在 `config_version` 加 `active`/`effective_from` 列并约定唯一生效行(需想清只增表上
  如何表达"仅一行 active"而不 UPDATE 老行)。

**动作:** 打标闭环阶段(worker 取配置的代码)**开工前先裁决本条**,再写取配置逻辑。
在此之前 worker 不得硬编码"取最新行"。

**牵连:** 同一问题也适用于 `vocabulary_version` 的"当期版本"选取(查询② 已按 version_no 比较,
但"当期 = 哪一版"的生效指针同样未定);两者宜一并裁决,口径统一。

**关联:** data-model §3.7【N3】(config.payload.vocab_versions 批次内锁定)、seed.py 的 config_version 播种、
skeleton-checklist §5 取舍 1。

---

## OQ-2 running 孤儿任务无回收机制 —— 【NAS 迁移阶段前置条件】

> 来源:R03 评审 P2-1。挂账,不阻塞打标闭环销账;**NAS 2–3 万张批打前必须先做**。

`claim_next_task` 把任务置 `running` 并提交后,若 worker 崩溃,该任务永久滞留 `running`——
`run_batch` 只认 `pending`,resume 对它无感,该图再不会被打。单图 demo/冒烟无碍,批量必炸。

**动作(NAS 阶段开工前):** 加一条回收入口(不必自动化):一个 CLI/make 目标,把**超时** `running`
与 `failed` 重置为 `pending`;`claim_next_task` 补记 `claimed_at`(需加列/迁移)作为超时判据。
在此之前不得启动 NAS 批量打标。

**关联:** [app/tagging/execute.py](../app/tagging/execute.py) `claim_next_task`/`run_batch`;migration §4 步骤 3–4。

---

## OQ-3 run_id 无生成纪律 —— 【NAS 迁移阶段前置条件】

> 来源:R03 评审 P2-5。挂账,不阻塞打标闭环销账。

`run_id` 是断点续跑与查询②(词表升级定位)的键,不是备注字段。当前 demo 用常量、冒烟用文件名、
`enqueue_tagging_task` 让调用方随手编,无统一格式。

**动作(NAS/批量阶段开工前):** 建统一生成函数与格式规范(如 `{purpose}_{yyyymmdd}_{seq}`),
批量入队一律经它,禁止裸传字符串。

**关联:** [app/tagging/execute.py](../app/tagging/execute.py) `enqueue_tagging_task`;查询② 定位依赖 run_id/vocab_version。
