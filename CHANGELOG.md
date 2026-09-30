# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/)。

## [未发布]

## [0.1.0] - 2026-09-30

首个公开版本。早期版本,接口可能变化。

### Added

- **AI 自动打标**:调用通义千问视觉模型(Qwen-VL,经阿里云百炼)给作品图打标签;原始输出原样留存,标签带完整溯源(模型、提示词版本、词表版本、输入哈希)。
- **受词表约束的维度 + 自由文本维度**:受约束维度归一化到词表(支持别名),词表外的词记为「待归类」进入复核;自由文本维度按原词形保存。
- **入库去重与复核修正**:按内容哈希去重、软删除可恢复;复核队列;人工新增/改值/删除/恢复标签,全程留痕。
- **按标签召回相似案例**与**方案页导出**(demo)。
- **行业包机制**:`packs/<id>/`(分类体系、带槽位的提示词、UI 文案、演示数据集指向、专属测试),`INDUSTRY_PACK` 一项配置切换;随仓库提供完整示例包 `balloon` 与空骨架 `template`;文档见 `docs/industry-packs.md`。
- **一键体验**:`docker compose --profile demo up --build demo`(示例包 + mock provider,无需密钥),浏览器打开 http://localhost:8100 。
- **`make smoke`**:面向零基础用户的真实 Qwen 冒烟测试(预检、key 仅本进程内存、独立 compose 项目与全新数据库、3 图逐项断言、错误 key 反向测试、key 落盘扫描、中文汇总),说明见 `docs/SMOKE.md`。单张图的开发者冒烟为 `make smoke-single`。
- demo 服务 `DEMO_STRICT=1` 严格模式(禁止 mock/离线兜底,真实调用失败返回 HTTP 502);任务输出记录调用来源 `_provider`;`GET /ui.json`(页面文案来自行业包)。
- `docker-compose.yml` 宿主机端口可由 `API_HOST_PORT` / `DEMO_HOST_PORT` / `PG_HOST_PORT` 覆盖。
- 多租户数据隔离;`LICENSE`(AGPL-3.0)、`CONTRIBUTING.md`、`ASSETS.md`、README 演示截图(`docs/images/demo.png`)。

### 相对内部预发布版本的不兼容变更

- **demo `POST /upload` 响应的 `tags` 结构变更。** 原为固定四键:
  `{"theme", "scene", "structure": [...], "colors": [{"zh", "role"}], "scheme_name"}`;
  现为由行业包 `pack.json` 的 `demo.view` 决定的通用结构:
  `{"fields": [{"label": str, "caption": str|null, "items": [{"text": str, "role": str|null}]}]}`。
  其余字段(`asset_id`、`degraded`、`similar`)不变。role 的展示名不再由后端硬编码,取自行业包 `ui.json` 的 `role_labels`。
- **命名变更**:分发名 `balloon-platform` → `studio-asset-library`;命令 `balloon-seed` → `assetlib-seed`;
  默认库名 `balloon_platform` → `asset_library`;DB 角色 `balloon_app` → `platform_app`(迁移 0001/0002 文本内改名,公开前无生产库);日志名 `balloon.*` → `assetlib.*`。
- 提示词模板槽位改为 `{{VOCAB:<维度键>}}` / `{{SLOT:<名>}}`;示例包提示词版本 `tagging_v2` → `tagging_v3`(判别规则与词表不变,内容锚 `prompt_sha256` 随之变化)。
- 移除 `app/seed_data.py`、`prompts/`、`schema/`:词表、提示词、输出 schema 迁入 `packs/<id>/`。

### Changed

- 打标输出的取值改为按包内 `extraction` 声明;`coerce_theme_str` 改名 `coerce_scalar`(行为不变)。
- 测试分层:`tests/`(核心)+ `packs/<id>/tests`(逐包运行)。
- 默认打标配置不再携带评测备注。

### 已知局限

见 [README](README.md#已知局限) 与 [docs/roadmap.md](docs/roadmap.md):仅标签检索(无以图搜图)、维度键固定为 5 个、自由文本维度不受词表约束、compose 部署的 worker 为占位(不做真实打标)、示例素材为程序绘制插画(不代表真实照片准确率)。

[未发布]: https://github.com/zhangleo-1983/studio-asset-library/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/zhangleo-1983/studio-asset-library/releases/tag/v0.1.0
