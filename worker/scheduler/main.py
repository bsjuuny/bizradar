"""PM2 entrypoint (bizradar-worker). Job registration lands per-phase as collectors ship."""

from __future__ import annotations

import logging
import sys

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}',
    stream=sys.stdout,
)
logger = logging.getLogger("bizradar.worker")


def build_scheduler() -> BlockingScheduler:
    return BlockingScheduler(
        timezone="Asia/Seoul",
        executors={"default": ThreadPoolExecutor(5)},
        job_defaults={
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time": 60,
        },
    )


def main() -> None:
    scheduler = build_scheduler()
    logger.info("bizradar-worker starting (no jobs registered yet)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("bizradar-worker stopped")


if __name__ == "__main__":
    main()
