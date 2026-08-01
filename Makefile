# balloon-platform 常用目标。DATABASE_URL 可覆盖。
DATABASE_URL ?= postgresql+psycopg2://localhost:5432/balloon_platform
export DATABASE_URL

PY := .venv/bin/python
PIP := uv pip

.PHONY: install migrate seed demo loop test smoke compose-up compose-down

install:
	uv venv --python 3.11
	$(PIP) install -e ".[dev]"

migrate:
	.venv/bin/alembic upgrade head

seed:
	.venv/bin/balloon-seed --tenant-id 1 --slug demo_tenant --display-name 示例客户

# 一键闭环演示(mock provider,无需密钥):上传→入库→打标→落 tag→复核→修正
demo: migrate
	$(PY) scripts/demo_loop.py

# 从零到闭环:建库 + 演示
loop: migrate demo

test:
	.venv/bin/pytest -q

# 真实 Qwen 冒烟(需 .env 的 DASHSCOPE_API_KEY);IMAGE=/path/to.jpg
smoke: migrate
	$(PY) scripts/smoke_qwen.py --image $(IMAGE) --tenant 1

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down -v

# ── 零级验证 demo(demo/zero-validation 分支)────────────────────────
export STORAGE_BACKEND ?= local
export LOCAL_STORAGE_ROOT ?= /tmp/balloon-demo-storage
export DEMO_ASSETS_DIR ?= demo_assets

.PHONY: demo-assets demo-seed demo-web internal-qa-seed

# 生成自有版权合规占位素材(正式演示前换真实合规图,重跑本目标)
demo-assets:
	$(PY) scripts/gen_demo_assets.py

# 一键:建库 + 合规素材 + 只入合规库并断言计数(验收①)。DEMO_MOCK=1 走确定性 provider
demo-seed: migrate demo-assets
	$(PY) scripts/demo_seed.py

# 起单页 demo web(需先 demo-seed)
demo-web:
	.venv/bin/uvicorn app.demo.server:app --host 0.0.0.0 --port 8100

# 内部质量目测集(69 张)——强制独立库,永不进 demo 实例/入仓。DIR=<LOCAL_IMAGE_DIR>
internal-qa-seed:
	DATABASE_URL=postgresql+psycopg2://localhost:5432/balloon_internal_qa \
	  $(PY) scripts/internal_qa_seed.py --dir $(DIR)

# 词表对齐(演示前置):给 demo 补词条。DIM= KEY= ZH=
demo-vocab-add:
	$(PY) scripts/demo_vocab_add.py --dim $(DIM) --key $(KEY) --zh $(ZH)
