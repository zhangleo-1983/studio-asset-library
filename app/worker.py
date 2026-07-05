"""打标 worker 入口(worker)。

与 api 同镜像、不同入口。本期只立骨架:一个空转的取任务循环占位。
真实实现(从 task 表 SELECT ... FOR UPDATE SKIP LOCKED 取 pending、调 Qwen-VL、写 tag+
溯源、落 event)属打标业务闭环,本阶段不写(architecture §3.3)。
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger("balloon.worker")


def run_forever(poll_interval_s: float = 5.0) -> None:  # pragma: no cover - 骨架占位
    logger.info("worker 启动(骨架:暂不取任务,本期不跑打标)")
    while True:
        # TODO(打标闭环): SELECT ... FOR UPDATE SKIP LOCKED 取 pending task。
        # 【队列=PG】不引 Redis。
        time.sleep(poll_interval_s)


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
