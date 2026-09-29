# studio-asset-library

[![CI](https://github.com/zhangleo-1983/studio-asset-library/actions/workflows/ci.yml/badge.svg)](https://github.com/zhangleo-1983/studio-asset-library/actions/workflows/ci.yml)

小工作室多模态素材库:AI 图像打标、词表/复核/修正闭环、按标签检索。**行业相关的一切(分类体系、提示词、UI 文案、演示数据集)都在可替换的「行业包」里**,核心与行业无关,改一项配置即可切换整套 demo——见 [docs/industry-packs.md](docs/industry-packs.md)。

> **当前阶段:仓库骨架**(architecture.md §10 第一步)。只建骨架,不写打标业务闭环。
> 设计冻结于 tag `design-freeze-v3`;唯一依据是 [`docs/`](docs/) 下设计文档,宪法是根目录
> [`PRINCIPLES.md`](PRINCIPLES.md)。

## 骨架包含什么

| 模块 | 文件 | 说明 |
|---|---|---|
| 配置加载 | `app/config.py` | pydantic-settings,集中读环境变量 |
| FastAPI 入口 | `app/main.py` | api 入口,挂租户中间件 + 健康检查 |
| worker 入口 | `app/worker.py` | 同镜像不同入口(本期空转占位) |
| 租户上下文 | `app/context.py` | ContextVar;缺上下文即 `NoTenantContext`【加固3】 |
| 租户中间件 | `app/middleware.py` | 解析 tenant_id 注入上下文 |
| DB 会话 | `app/db.py` | `tenant_session()`(强制上下文)/ `platform_session(reason)` |
| 存储接口 | `app/storage/` | `StorageBackend`(put/get/presign/thumbnail_url)+ OSS 占位【不变量三】 |
| 事件写入 | `app/events.py` | 唯一 `record_event()` + `event_type→sensitive` 映射【Q7】 |
| 迁移 | `app/migrations/` | alembic 首版 = data-model.md 全部 DDL 逐表照搬 |
| 种子 | `app/seed.py` | 参数化可重放租户种子(migration §4 步骤 0);词表/配置取自行业包 |
| 行业包 | `app/packs.py` + `packs/<id>/` | 分类体系 / 提示词模板 / UI 文案 / 演示数据集指向;`INDUSTRY_PACK` 选用 |

## 快速开始(用完整示例包跑通 demo)

前置:一个可连的 PostgreSQL 15。

```bash
uv venv --python 3.11 && uv pip install -e ".[dev]"
export DATABASE_URL="postgresql+psycopg2://localhost:5432/asset_library"
export INDUSTRY_PACK=balloon      # 完整示例包(见 packs/README.md);make demo 系列目标默认也用它

make migrate                      # 建库结构(逐表 DDL + REVOKE 只增表 + 固化 tenant_id=0)
DEMO_MOCK=1 make demo-seed        # 生成演示素材 + 入库 + 打标(mock provider,无需密钥)
make demo-web                     # 演示页 http://localhost:8100
make demo                         # 打标闭环演示(mock provider)
```

### `balloon` 与 `template` 的区别

| | `INDUSTRY_PACK=balloon` | `INDUSTRY_PACK=template` |
|---|---|---|
| 定位 | 完整示例:词表、提示词、UI 文案、演示素材生成器、专属测试齐全 | 空骨架:结构齐全,无词表、无演示素材 |
| 用途 | 快速体验、学习、当作写新行业的参考 | **部署默认值**;复制它写自己的行业包 |
| 何时选 | 本地试玩、演示(`make demo*` 默认) | 生产/部署(`app/config.py`、`.env.example`、compose 的默认) |

## 部署/生产

部署默认 `INDUSTRY_PACK=template`,你需要先写好自己的行业包(复制 `packs/template/`,按其 `FIELDS.md` 填写),再把 `INDUSTRY_PACK` 指向它:

```bash
.venv/bin/alembic upgrade head
.venv/bin/assetlib-seed --tenant-id 1 --slug demo_tenant --display-name "Demo tenant"   # 词表取自所选包
```

## 测试

```bash
make test        # 核心测试(默认包)+ 每个行业包自带的 packs/<id>/tests(用该包运行)
```

核心测试覆盖租户隔离【加固3】、当期配置指针、行业包加载与切换;行业相关的打标闭环测试随各行业包。

## compose 三件套

```bash
docker compose up --build     # api / worker / postgres(无 Redis)
```

> 状态:**已由 CI 每次提交自动验证**(`compose` job:`docker compose up -d --build` → 轮询
> `/healthz` 通过 → `compose down`),badge 见页首。

## 切换行业包

```bash
INDUSTRY_PACK=<id> make demo-seed && INDUSTRY_PACK=<id> make demo-web
```

新增行业:复制 `packs/template/`,按其中 `FIELDS.md` 填写;详见 [docs/industry-packs.md](docs/industry-packs.md)。

## 对照校验

alembic DDL 与 [`docs/data-model.md`](docs/data-model.md) 的表名/约束名/索引名一一对应,可人工抽查。

## 许可

本项目以 [GNU AGPL-3.0](LICENSE) 发布。商业授权请联系 zhangliang@getbitbeats.com。
