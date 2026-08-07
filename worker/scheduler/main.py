"""PM2 entrypoint (bizradar-worker). Job registration lands per-phase as collectors ship."""

from __future__ import annotations

import logging

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler

from worker.jobs import analyze_job, g2b_job, match_job
from worker.logging_config import configure_logging

configure_logging()
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
    scheduler.add_job(g2b_job.run, "interval", hours=1, id="g2b-collect")
    scheduler.add_job(analyze_job.run, "interval", minutes=10, id="analyze")
    scheduler.add_job(match_job.run, "interval", minutes=15, id="match")
    logger.info(
        "bizradar-worker starting",
        extra={
            "jobs": [
                "g2b-collect (hourly)",
                "analyze (every 10min, batch of 5)",
                "match (every 15min, all companies x analyzed opportunities)",
            ]
        },
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("bizradar-worker stopped")


if __name__ == "__main__":
    main()
