# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/);尚未发布正式版本,以下为未发布变更。

## [Unreleased]

### ⚠️ Breaking

- **demo `POST /upload` 响应的 `tags` 结构变更。** 原为固定四键:
  `{"theme", "scene", "structure": [...], "colors": [{"zh", "role"}], "scheme_name"}`;
  现为由行业包 `pack.json` 的 `demo.view` 决定的通用结构:
  `{"fields": [{"label": str, "caption": str|null, "items": [{"text": str, "role": str|null}]}]}`。
  其余字段(`asset_id`、`degraded`、`similar`)不变。role 的展示名不再由后端硬编码,取自行业包 `ui.json` 的 `role_labels`。
  调用方需按 `fields` 渲染。
- **命名变更**:分发名 `balloon-platform` → `studio-asset-library`;命令 `balloon-seed` → `assetlib-seed`;
  默认库名 `balloon_platform` → `asset_library`;DB 角色 `balloon_app` → `platform_app`(迁移 0001/0002 文本内改名,
  公开前无生产库);日志名 `balloon.*` → `assetlib.*`。
- 提示词模板槽位改为 `{{VOCAB:<维度键>}}` / `{{SLOT:<名>}}`;示例包提示词版本 `tagging_v2` → `tagging_v3`
  (判别规则与词表不变,内容锚 `prompt_sha256` 随之变化)。
- 移除 `app/seed_data.py`、`prompts/`、`schema/`:词表、提示词、输出 schema 迁入 `packs/<id>/`。

### Added

- `make smoke`:面向零基础用户的真实 Qwen 冒烟测试(预检、key 仅本进程内存、独立 compose 项目与全新数据库、3 图逐项断言、错误 key 反向测试、key 落盘扫描、中文汇总),说明见 `docs/SMOKE.md`。原 `make smoke` 更名为 `make smoke-single`。
- demo 服务 `DEMO_STRICT=1` 严格模式(禁止 mock/离线兜底,真实调用失败返回 HTTP 502);任务输出记录调用来源 `_provider`。
- `docker-compose.yml` 宿主机端口可由 `API_HOST_PORT` / `DEMO_HOST_PORT` / `PG_HOST_PORT` 覆盖;api 增加 8100(demo)端口映射。

- 行业包机制:`packs/<id>/`(分类体系、带槽位的提示词、UI 文案、演示数据集指向、专属测试),
  `INDUSTRY_PACK` 一项配置切换;随仓库提供完整示例包与空骨架 `template`;文档见 `docs/industry-packs.md`。
- demo 新增 `GET /ui.json`(页面文案来自行业包)。
- `LICENSE`(AGPL-3.0)、`CONTRIBUTING.md`、`ASSETS.md`。

### Changed

- 打标输出的取值改为按包内 `extraction` 声明;`coerce_theme_str` 改名 `coerce_scalar`(行为不变)。
- 测试分层:`tests/`(核心)+ `packs/<id>/tests`(逐包运行)。
- 默认打标配置不再携带评测备注。
