# 挂账清单(open questions)

> 骨架阶段暴露、但不属骨架范围、需在对应阶段开工前先定的问题。设计冻结于
> design-freeze-v3;本清单只记账,不自行裁决。

---

## OQ-1 「当前生效配置」的选取规则未定义 —— 打标闭环阶段必须先定

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
