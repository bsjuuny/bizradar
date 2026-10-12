"""Scheduled G2B collection job. A failure here must not take down the scheduler or
other jobs (docs/DATA_PIPELINE.md#failure-isolation) - existing opportunities rows are
left untouched on failure, since collection only ever upserts, never deletes.

Every run logs the KST window it queried (window_start/window_end), on success and on
failure, so "why was nothing collected" can be answered from the log alone.

A one-off catch-up over a longer window (after downtime, or after a fix to the window
itself) - from the repo root; it reads the shared vault first, like the PM2 entrypoint:

    python -m worker.jobs.g2b_job --lookback-hours 12
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime, timedelta

from worker.collectors.g2b import SEOUL, G2BCollector

logger = logging.getLogger(__name__)

# Runs hourly (see worker/scheduler/main.py) - a couple of hours of lookback gives
# overlap against a missed or slow run without re-scanning the whole day every time.
DEFAULT_LOOKBACK = timedelta(hours=2)


def run(lookback: timedelta = DEFAULT_LOOKBACK) -> None:
    # The window is computed in KST because that is how the API reads it - see
    # worker/collectors/g2b.py:to_seoul for the nine-hour lag a UTC window caused.
    until = datetime.now(SEOUL)
    since = until - lookback
    window = {
        "window_start": since.isoformat(timespec="minutes"),
        "window_end": until.isoformat(timespec="minutes"),
    }

    started_at = datetime.now(UTC)

    try:
        with G2BCollector(since=since, until=until) as collector:
            result = collector.run()
    except Exception as exc:
        logger.exception(
            "g2b job failed entirely - existing opportunities rows are unaffected",
            extra={
                "job": "g2b-collect",
                "source": "g2b",
                "status": "failed",
                "error_type": type(exc).__name__,
                **window,
            },
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
            **window,
        },
    )
    if result.errors:
        logger.warning(
            "g2b job had per-record errors",
            extra={"job": "g2b-collect", "source": "g2b", "errors": result.errors[:10], **window},
        )


def main() -> None:
    from worker.logging_config import configure_logging
    from worker.secrets_loader import load_github_secrets

    parser = argparse.ArgumentParser(description="One-off G2B collection over a custom window.")
    parser.add_argument(
        "--lookback-hours",
        type=float,
        default=DEFAULT_LOOKBACK.total_seconds() / 3600,
        help="how far back from now (KST) to query; upserts are idempotent",
    )
    args = parser.parse_args()
    load_github_secrets()
    configure_logging()
    run(lookback=timedelta(hours=args.lookback_hours))


if __name__ == "__main__":
    main()
