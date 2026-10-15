"""Scheduled K-Startup collection job. A failure here must not take down the scheduler
or other jobs (docs/DATA_PIPELINE.md#failure-isolation) - existing support_programs
rows are left untouched on failure, since collection only ever upserts, never deletes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from worker.collectors.kstartup import KStartupCollector, StoredRow
from worker.repositories import support_programs

logger = logging.getLogger(__name__)


def run() -> None:
    started_at = datetime.now(UTC)

    stored: dict[str, StoredRow] | None
    try:
        stored = support_programs.fetch_kstartup_state()
    except Exception:  # noqa: BLE001 - unknown state only costs extra writes
        # Without it every row is written, as before 2026-10-15.
        logger.warning(
            "kstartup: could not read stored state - writing every row this run", exc_info=True
        )
        stored = None

    try:
        with KStartupCollector(stored=stored) as collector:
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
            "unchanged": collector.unchanged,
            "failed": result.failed,
        },
    )
    if result.errors:
        logger.warning(
            "kstartup job had per-record errors",
            extra={"job": "kstartup-collect", "source": "kstartup", "errors": result.errors[:10]},
        )
