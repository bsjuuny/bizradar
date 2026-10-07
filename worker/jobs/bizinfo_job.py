"""Scheduled 기업마당(BizInfo) collection job. Collection skips cleanly until
BIZINFO_API_KEY is configured. A failure here must not take down the scheduler or other
jobs (docs/DATA_PIPELINE.md#failure-isolation) - existing support_programs rows are left
untouched on failure, since collection only ever upserts.

Two follow-up passes, each isolated from the other:
1. close (after a successful collection only): announcements that dropped off 기업마당's
   list are marked recruiting=false - only when the response was provably the complete
   list (BizInfoCollector.complete). Each such run is recorded in support_source_sync:
   is_open() in SQL stops counting date-less 기업마당 rows as 모집 중 once this pass
   hasn't run for 3 days (expired key, persistently truncated responses), since nothing
   else would ever close them.
2. dedupe (every run with Supabase configured, even when collection was skipped or failed
   - K-Startup rows keep opening and closing, and a stale duplicate_of would pair a
   기업마당 copy with a K-Startup original that has left the 모집 중 view): 기업마당 rows
   that repeat an open K-Startup announcement get duplicate_of set, so Support Radar
   shows the program once (worker/dedupe/support_programs.py). K-Startup is the row kept:
   it is the original posting and carries more fields (모집 여부, 지원대상, 지역). Runs
   here rather than in the K-Startup job because only BizInfo rows are ever hidden; a
   K-Startup row collected in between is picked up within the hour.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from worker.collectors.bizinfo import BizInfoCollector
from worker.config import get_settings
from worker.dedupe.support_programs import find_duplicates, plan_updates
from worker.repositories import support_programs

logger = logging.getLogger(__name__)

JOB = "bizinfo-collect"


def run() -> None:
    collect()
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.info(
            "bizinfo dedupe skipped - Supabase is not configured",
            extra={"job": JOB, "status": "skipped"},
        )
        return
    try:
        dedupe()
    except Exception:
        logger.exception("bizinfo: cross-source dedupe failed", extra={"job": JOB})


def collect() -> None:
    if not get_settings().bizinfo_api_key:
        logger.info(
            "bizinfo job skipped - BIZINFO_API_KEY is not configured",
            extra={"job": JOB, "source": "bizinfo", "status": "skipped"},
        )
        return

    started_at = datetime.now(UTC)
    try:
        with BizInfoCollector() as collector:
            result = collector.run()
    except Exception:
        logger.exception(
            "bizinfo job failed entirely - existing support_programs rows are unaffected",
            extra={"job": JOB, "source": "bizinfo", "status": "failed"},
        )
        return

    logger.info(
        "bizinfo job finished",
        extra={
            "job": JOB,
            "source": "bizinfo",
            "status": "ok" if result.failed == 0 else "partial",
            "duration": (datetime.now(UTC) - started_at).total_seconds(),
            "collected": result.collected,
            # persisted counts every record persist() accepted, written or skipped as
            # unchanged; written is what actually went to the database.
            "persisted": result.persisted,
            "written": result.persisted - collector.unchanged,
            "unchanged": collector.unchanged,
            "failed": result.failed,
            "complete": collector.complete,
        },
    )
    if result.errors:
        logger.warning(
            "bizinfo job had per-record errors",
            extra={"job": JOB, "source": "bizinfo", "errors": result.errors[:10]},
        )

    if collector.complete:
        try:
            closed = support_programs.close_unlisted_bizinfo(
                collector.listed_ids, collector.stored_recruiting
            )
            support_programs.mark_source_sync_complete("bizinfo")
            logger.info(
                "bizinfo: closed unlisted announcements", extra={"job": JOB, "closed": closed}
            )
        except Exception:
            logger.exception("bizinfo: closing unlisted announcements failed", extra={"job": JOB})


def dedupe() -> None:
    kstartup = support_programs.fetch_open_kstartup_titles()
    bizinfo, current = support_programs.fetch_open_bizinfo_titles()
    changes = plan_updates(current, find_duplicates(keep=kstartup, hide=bizinfo))
    support_programs.set_duplicate_of(changes)
    logger.info(
        "bizinfo: cross-source dedupe finished",
        extra={
            "job": JOB,
            "kstartup_open": len(kstartup),
            "bizinfo_open": len(bizinfo),
            "marked": sum(1 for value in changes.values() if value is not None),
            "cleared": sum(1 for value in changes.values() if value is None),
        },
    )
