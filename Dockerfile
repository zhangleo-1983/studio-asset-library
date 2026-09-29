# 同一镜像,api / worker 两个入口(见 docker-compose.yml 的 command)。
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖(利用层缓存)
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install -e .

# alembic 配置、行业包(提示词/词表/UI 文案按路径加载,须随镜像)与脚本
COPY alembic.ini ./
COPY packs ./packs
COPY scripts ./scripts

# 默认入口 = api;worker 在 compose 里覆盖 command
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
