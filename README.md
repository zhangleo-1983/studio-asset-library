# balloon-platform

[![CI](https://github.com/zhangleo-1983/studio-asset-library/actions/workflows/ci.yml/badge.svg)](https://github.com/zhangleo-1983/studio-asset-library/actions/workflows/ci.yml)

定制服务行业选款与供应链 SaaS 平台(首个行业:气球派对设计;首个租户:示例客户)。

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
| 种子 | `app/seed.py` | 参数化可重放租户种子(migration §4 步骤 0) |

## 从零建库(一条命令跑通)

前置:一个可连的 PostgreSQL 15。

```bash
uv venv --python 3.11 && uv pip install -e ".[dev]"
export DATABASE_URL="postgresql+psycopg2://localhost:5432/balloon_platform"

# 建库结构(逐表 DDL + REVOKE 只增表 + 固化 tenant_id=0)
.venv/bin/alembic upgrade head

# 种子首个租户示例客户(可重放脚本;第二租户换参数重放同一命令)
.venv/bin/balloon-seed --tenant-id 1 --slug demo_tenant --display-name 示例客户
```

## 测试

```bash
.venv/bin/pytest -q
```

两条集成测试:① 无租户上下文查询必失败【加固3】;② 种子双 tenant 重放数据互不可见(场景 3)。

## compose 三件套

```bash
docker compose up --build     # api / worker / postgres(无 Redis)
```

> 状态:**已由 CI 每次提交自动验证**(`compose` job:`docker compose up -d --build` → 轮询
> `/healthz` 通过 → `compose down`),badge 见页首。

## 交付自证

[`docs/skeleton-checklist.md`](docs/skeleton-checklist.md):alembic DDL 与 data-model.md 的
表名/约束名/索引名三列对照,供人工抽查。
