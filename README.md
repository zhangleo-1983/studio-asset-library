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

## 从零建库(一条命令跑通)

前置:一个可连的 PostgreSQL 15。

```bash
uv venv --python 3.11 && uv pip install -e ".[dev]"
export DATABASE_URL="postgresql+psycopg2://localhost:5432/asset_library"
export INDUSTRY_PACK=template     # 行业包:packs/ 下的目录名;template 是空骨架;随仓库提供的包见 packs/README.md

# 建库结构(逐表 DDL + REVOKE 只增表 + 固化 tenant_id=0)
.venv/bin/alembic upgrade head

# 种子首个租户(可重放脚本;第二租户换参数重放同一命令;词表取自所选行业包)
.venv/bin/assetlib-seed --tenant-id 1 --slug demo_tenant --display-name "Demo tenant"
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
