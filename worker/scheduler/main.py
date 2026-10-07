"""PM2 entrypoint (bizradar-worker). Job registration lands per-phase as collectors ship."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger


# 서비스(PM2)로 뜰 때만 금고를 읽는다 — worker/config.py 에 두면 테스트가 import 할 때
# 실제 키가 들어가 "키 없으면 건너뜀" 테스트가 깨졌다(2026-09-30).
# 공용 DPAPI 금고(C:\github\.secrets)를 .env 보다 먼저 읽는다(2026-09-30). 금고에 없는 값만
# .env 가 채운다. 금고가 없는 환경(다른 PC·CI)에서는 조용히 건너뛰고, 열지 못하면 경고만 남긴다.
# 그래서 아래 worker.* import 는 일부러 이 호출 뒤에 둔다(E402).
def _load_github_secrets(file_keys):
    import importlib.util as _ilu
    import os as _os
    import sys as _sys

    _path = r"C:\github\.secrets\load.py"
    if not _os.path.exists(_path):
        return
    try:
        _spec = _ilu.spec_from_file_location("github_secrets_load", _path)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _mod.load_secrets(file_keys, optional=True)
    except Exception as _exc:  # noqa: BLE001
        print(f"[secrets] 금고 로더를 불러오지 못했습니다: {_exc}", file=_sys.stderr)


_load_github_secrets(["bizradar/.env.worker"])

from worker.config import get_settings  # noqa: E402
from worker.jobs import (  # noqa: E402
    analyze_job,
    bizinfo_job,
    challenge_analyze_job,
    challenge_job,
    digest_job,
    g2b_award_job,
    g2b_job,
    kstartup_job,
    match_job,
)
from worker.logging_config import configure_logging  # noqa: E402

configure_logging()
logger = logging.getLogger("bizradar.worker")
SEOUL = ZoneInfo("Asia/Seoul")


def build_scheduler() -> BlockingScheduler:
    return BlockingScheduler(
        timezone="Asia/Seoul",
        # Interval jobs share the start time, so g2b, kstartup, analyze and match fire
        # together every hour (+ g2b-award every 6h, the challenge jobs). APScheduler checks
        # misfire_grace_time when a queued job actually starts, so with too few threads the
        # one left waiting >60s behind long runs is skipped as "missed". Headroom above
        # the 5-6 that can coincide.
        executors={"default": ThreadPoolExecutor(10)},
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
    scheduler.add_job(g2b_award_job.run, "interval", hours=6, id="g2b-award-collect")
    scheduler.add_job(kstartup_job.run, "interval", hours=1, id="kstartup-collect")
    # Offset from the top-of-the-hour group: ~1,450 upserts through the one shared
    # Supabase client while 4-5 other jobs use it is when the worker's intermittent
    # "WinError 10035" socket failures hit (26-30 BizInfo rows per run on 2026-10-07, at
    # :08 alongside the others). :35 has no other interval job (analyze :x0, match :x5).
    scheduler.add_job(
        bizinfo_job.run,
        "interval",
        hours=1,
        id="bizinfo-collect",
        next_run_time=datetime.now(SEOUL) + timedelta(minutes=35),
    )
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
    if settings.telegram_bot_token:
        scheduler.add_job(
            digest_job.run,
            CronTrigger(hour=9, minute=0, timezone="Asia/Seoul"),
            id="watch-digest",
        )
    logger.info(
        "bizradar-worker starting",
        extra={
            "jobs": [
                "g2b-collect (hourly)",
                "g2b-award-collect (every 6h, when G2B_AWARD_API_KEY is configured)",
                "kstartup-collect (hourly, first 500 recent-first)",
                "bizinfo-collect (hourly, when BIZINFO_API_KEY is configured)",
                "analyze (every 10min, batch of 5)",
                "match (every 15min, all companies x analyzed opportunities)",
                "challenge:collect (configured cron)",
                "challenge:reanalyze (every 10min when enabled)",
                "watch-digest (daily 09:00 KST, when TELEGRAM_BOT_TOKEN is configured)",
            ]
        },
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("bizradar-worker stopped")


if __name__ == "__main__":
    main()
