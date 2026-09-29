# studio-asset-library 常用目标。DATABASE_URL 可覆盖。
# 行业包:INDUSTRY_PACK=<packs/ 下的目录名>。部署默认值是 template(空骨架,见 app/config.py);
# 下面的 demo 系列目标默认用完整示例包 balloon,可用 `INDUSTRY_PACK=<id> make demo-seed` 覆盖。
DATABASE_URL ?= postgresql+psycopg2://localhost:5432/asset_library
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
	.venv/bin/assetlib-seed --tenant-id 1 --slug demo_tenant --display-name "Demo tenant"

# 一键闭环演示(mock provider,无需密钥):上传→入库→打标→落 tag→复核→修正
# 演示脚本由行业包提供(pack.json demo.loop_script);空骨架包无脚本则跳过
demo: migrate
	$(PY) scripts/pack_run.py loop

# 从零到闭环:建库 + 演示
loop: migrate demo

# 核心测试(tests/,用默认行业包)+ 每个行业包自带测试(packs/<id>/tests,用该包)
test:
	.venv/bin/pytest -q
	@for d in packs/*/tests; do [ -d "$$d" ] || continue; p=$$(basename $$(dirname $$d)); echo "== pack tests: $$p"; INDUSTRY_PACK=$$p .venv/bin/pytest -q $$d || exit 1; done

# 真实 Qwen 冒烟(需 .env 的 DASHSCOPE_API_KEY);IMAGE=/path/to.jpg
smoke: migrate
	$(PY) scripts/smoke_qwen.py --image $(IMAGE) --tenant 1

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down -v

# ── demo(数据集/文案/维度取自行业包)────────────────────────────
export STORAGE_BACKEND ?= local
export LOCAL_STORAGE_ROOT ?= /tmp/assetlib-demo-storage
export DEMO_ASSETS_DIR ?= demo_assets

.PHONY: demo-assets demo-seed demo-web internal-qa-seed

# demo 系列目标(含 demo / loop)默认使用示例包;部署与其余目标沿用 template 默认值
demo loop demo-assets demo-seed demo-web demo-vocab-add: export INDUSTRY_PACK ?= balloon

# 生成行业包自带的演示素材(pack.json demo.assets.generator;正式演示前换真实合规图)
demo-assets:
	$(PY) scripts/pack_run.py assets

# 一键:建库 + 合规素材 + 只入合规库并断言计数(验收①)。DEMO_MOCK=1 走确定性 provider
demo-seed: migrate demo-assets
	$(PY) scripts/demo_seed.py

# 起单页 demo web(需先 demo-seed)
demo-web:
	.venv/bin/uvicorn app.demo.server:app --host 0.0.0.0 --port 8100

# 内部质量目测集(来源未核实的本地图)——强制独立库,永不进 demo 实例/入仓。DIR=/path/to/images
internal-qa-seed:
	DATABASE_URL=postgresql+psycopg2://localhost:5432/asset_library_internal_qa \
	  $(PY) scripts/internal_qa_seed.py --dir $(DIR)

# 词表对齐(演示前置):给 demo 补词条。DIM= KEY= ZH=
demo-vocab-add:
	$(PY) scripts/demo_vocab_add.py --dim $(DIM) --key $(KEY) --zh $(ZH)
