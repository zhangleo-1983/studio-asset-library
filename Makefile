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
