"""Scheduled K-Startup collection job. A failure here must not take down the scheduler
or other jobs (docs/DATA_PIPELINE.md#failure-isolation) - existing support_programs
rows are left untouched on failure, since collection only ever upserts, never deletes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from worker.collectors.kstartup import KStartupCollector

logger = logging.getLogger(__name__)


def run() -> None:
    started_at = datetime.now(UTC)

    try:
        with KStartupCollector() as collector:
            result = collector.run()
    except Exception:
        logger.exception(
            "kstartup job failed entirely - existing support_programs rows are unaffected",
            extra={"job": "kstartup-collect", "source": "kstartup", "status": "failed"},
        )
        return

    duration_seconds = (datetime.now(UTC) - started_at).total_seconds()
    logger.info(
        "kstartup job finished",
        extra={
            "job": "kstartup-collect",
            "source": "kstartup",
            "status": "ok" if result.failed == 0 else "partial",
            "duration": duration_seconds,
            "collected": result.collected,
            "persisted": result.persisted,
            "failed": result.failed,
        },
    )
    if result.errors:
        logger.warning(
            "kstartup job had per-record errors",
            extra={"job": "kstartup-collect", "source": "kstartup", "errors": result.errors[:10]},
        )
