"""Scheduled G2B collection job. A failure here must not take down the scheduler or
other jobs (docs/DATA_PIPELINE.md#failure-isolation) - existing opportunities rows are
left untouched on failure, since collection only ever upserts, never deletes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from worker.collectors.g2b import G2BCollector

logger = logging.getLogger(__name__)

# Runs hourly (see worker/scheduler/main.py) - a couple of hours of lookback gives
# overlap against a missed or slow run without re-scanning the whole day every time.
DEFAULT_LOOKBACK = timedelta(hours=2)


def run(lookback: timedelta = DEFAULT_LOOKBACK) -> None:
    since = datetime.now(UTC) - lookback

    started_at = datetime.now(UTC)

    try:
        with G2BCollector(since=since) as collector:
            result = collector.run()
    except Exception:
        logger.exception(
            "g2b job failed entirely - existing opportunities rows are unaffected",
            extra={"job": "g2b-collect", "source": "g2b", "status": "failed"},
        )
        return

    duration_seconds = (datetime.now(UTC) - started_at).total_seconds()
    logger.info(
        "g2b job finished",
        extra={
            "job": "g2b-collect",
            "source": "g2b",
            "status": "ok" if result.failed == 0 else "partial",
            "duration": duration_seconds,
            "collected": result.collected,
            "persisted": result.persisted,
            "failed": result.failed,
        },
    )
    if result.errors:
        logger.warning(
            "g2b job had per-record errors",
            extra={"job": "g2b-collect", "source": "g2b", "errors": result.errors[:10]},
        )
