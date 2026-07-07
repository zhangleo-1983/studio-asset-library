"""打标 worker 入口(worker)。

与 api 同镜像、不同入口。从 task 表经 FOR UPDATE SKIP LOCKED 取 pending、调 Qwen-VL、写
tag + 完整溯源、落 event(architecture §3.3)。【队列=PG】不引 Redis。

生产 provider 走真实 Qwen(需 DASHSCOPE_API_KEY);CI/测试不跑本入口,直接以 Fake provider
调 app.tagging.execute.run_batch。
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import text

from app.context import tenant_context
from app.db import platform_session
from app.tagging.execute import run_batch
from app.tagging.provider import TaggingProvider, get_default_provider

logger = logging.getLogger("balloon.worker")


def _tenants_with_pending() -> list[int]:
    # 【裁决九 · 第 1 类】只读基础设施扫描:reason 声明即可、日志留痕,不落 event
    # (只为调度自身服务、不触碰业务数据对外产出)。见 architecture §3.1 / db.py docstring。
    with platform_session(reason="worker:scan_pending") as session:
        rows = session.execute(
            text(
                "SELECT DISTINCT tenant_id FROM task "
                "WHERE task_type='tagging' AND status='pending' ORDER BY tenant_id"
            )
        ).scalars().all()
    return list(rows)


def drain_all(provider: TaggingProvider) -> int:
    """把所有租户的 pending 打标任务处理干净。返回处理条数。"""
    total = 0
    for tenant_id in _tenants_with_pending():
        with tenant_context(tenant_id):
            total += run_batch(provider)
    return total


def run_forever(poll_interval_s: float = 5.0) -> None:  # pragma: no cover
    from app.tagging.provider import ProviderConfigError

    try:
        provider = get_default_provider()
    except ProviderConfigError:
        # 无 DASHSCOPE_API_KEY(如 compose/CI 无密钥):空转待命,不崩溃、不处理任务。
        logger.warning("未配置 DASHSCOPE_API_KEY,worker 空转待命(不处理任务)")
        while True:
            time.sleep(poll_interval_s)
    logger.info("worker 启动:轮询 pending 打标任务(间隔 %ss)", poll_interval_s)
    while True:
        n = drain_all(provider)
        if n:
            logger.info("本轮处理 %s 条", n)
        time.sleep(poll_interval_s)


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
