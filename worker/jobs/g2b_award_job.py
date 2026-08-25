"""Scheduled G2B award collection, isolated from bid-announcement collection."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from worker.collectors.g2b_awards import G2BAwardCollector
from worker.config import get_settings

logger = logging.getLogger(__name__)

# The job runs every six hours. A twelve-hour overlap tolerates delayed publication
# and missed cycles while remaining well within the public API's normal date window.
DEFAULT_LOOKBACK = timedelta(hours=12)
SEOUL = ZoneInfo("Asia/Seoul")


def run(lookback: timedelta = DEFAULT_LOOKBACK) -> None:
    if not get_settings().g2b_award_api_key:
        logger.info(
            "g2b award job skipped - G2B_AWARD_API_KEY is not configured",
            extra={"job": "g2b-award-collect", "status": "skipped"},
        )
        return

    started_at = datetime.now(UTC)
    query_until = datetime.now(SEOUL)
    try:
        with G2BAwardCollector(
            since=query_until - lookback,
            until=query_until,
        ) as collector:
            result = collector.run()
    except Exception:
        logger.exception(
            "g2b award job failed - existing award rows are unaffected",
            extra={"job": "g2b-award-collect", "source": "g2b_award", "status": "failed"},
        )
        return

    logger.info(
        "g2b award job finished",
        extra={
            "job": "g2b-award-collect",
            "source": "g2b_award",
            "status": "ok" if result.failed == 0 else "partial",
            "duration": (datetime.now(UTC) - started_at).total_seconds(),
            "collected": result.collected,
            "persisted": result.persisted,
            "failed": result.failed,
        },
    )
    if result.errors:
        logger.warning(
            "g2b award job had per-record errors",
            extra={"job": "g2b-award-collect", "errors": result.errors[:10]},
        )
