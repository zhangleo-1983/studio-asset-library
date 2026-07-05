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

# alembic 配置与迁移随源码 COPY(app/migrations 已在 app 内)
COPY alembic.ini ./

# 默认入口 = api;worker 在 compose 里覆盖 command
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
