"""PM2 entrypoint (bizradar-worker). Job registration lands per-phase as collectors ship."""

from __future__ import annotations

import logging

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from worker.config import get_settings
from worker.jobs import (
    analyze_job,
    challenge_analyze_job,
    challenge_job,
    g2b_job,
    kstartup_job,
    match_job,
)
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
    settings = get_settings()
    scheduler.add_job(g2b_job.run, "interval", hours=1, id="g2b-collect")
    scheduler.add_job(kstartup_job.run, "interval", hours=1, id="kstartup-collect")
    scheduler.add_job(analyze_job.run, "interval", minutes=10, id="analyze")
    scheduler.add_job(match_job.run, "interval", minutes=15, id="match")
    if settings.feature_challenge and settings.challenge_collection_enabled:
        scheduler.add_job(
            challenge_job.run,
            CronTrigger.from_crontab(settings.challenge_collection_cron, timezone="Asia/Seoul"),
            id="challenge:collect",
        )
    if settings.feature_challenge and settings.challenge_ai_analysis_enabled:
        scheduler.add_job(
            challenge_analyze_job.run,
            "interval",
            minutes=10,
            id="challenge:reanalyze",
        )
    logger.info(
        "bizradar-worker starting",
        extra={
            "jobs": [
                "g2b-collect (hourly)",
                "kstartup-collect (hourly, first 500 recent-first)",
                "analyze (every 10min, batch of 5)",
                "match (every 15min, all companies x analyzed opportunities)",
                "challenge:collect (configured cron)",
                "challenge:reanalyze (every 10min when enabled)",
            ]
        },
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("bizradar-worker stopped")


if __name__ == "__main__":
    main()
