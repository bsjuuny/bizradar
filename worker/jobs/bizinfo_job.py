"""Scheduled 기업마당(BizInfo) collection job. Collection skips cleanly until
BIZINFO_API_KEY is configured. A failure here must not take down the scheduler or other
jobs (docs/DATA_PIPELINE.md#failure-isolation) - existing support_programs rows are left
untouched on failure, since collection only ever upserts.

After a successful collection every listed row has a recent last_seen_at - upserted
rows set it, and the job refreshes the stored ones that are listed once theirs is a day
old (support_programs.seen_refresh_due). is_open() in SQL stops counting a date-less
기업마당 row as 모집 중 once it has gone 3 days unseen: for the 65% of postings whose
신청기간 is a phrase ("예산 소진시까지"), leaving the list is the only way they close, and
pass 1 below can stall (expired key, responses that keep coming back incomplete). Dated
rows close on their date.

Two follow-up passes, each isolated from the other:
1. close (after a successful collection only): announcements that dropped off 기업마당's
   list are marked recruiting=false - only when the response was provably the complete
   list (BizInfoCollector.complete).
2. dedupe (every run with Supabase configured, even when collection was skipped or failed
   - K-Startup rows keep opening and closing, and a stale duplicate_of would pair a
   기업마당 copy with a K-Startup original that has left the 모집 중 view): 기업마당 rows
   that repeat an open K-Startup announcement get duplicate_of set, so Support Radar
   shows the program once (worker/dedupe/support_programs.py). K-Startup is the row kept:
   it is the original posting and carries more fields (모집 여부, 지원대상, 지역) - unless
   only the copy is still open. A pair stays paired after either side closes
   (plan_duplicate_marks); pairing never changes a row's 모집 status. Runs here rather than
   in the K-Startup job because only BizInfo rows are ever marked; a K-Startup row
   collected in between is picked up within the hour.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from worker.collectors.bizinfo import BizInfoCollector, StoredRow
from worker.config import get_settings
from worker.dedupe.support_programs import plan_duplicate_marks
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
    stored: dict[str, StoredRow] | None
    try:
        stored = support_programs.fetch_bizinfo_state()
    except Exception:
        # Read once per run: without it every row is written, and the closing pass
        # reads for itself.
        logger.warning(
            "bizinfo: could not read stored state - writing every row this run",
            extra={"job": JOB},
            exc_info=True,
        )
        stored = None
    try:
        with BizInfoCollector(stored=stored) as collector:
            result = collector.run()
    except Exception:
        logger.exception(
            "bizinfo job failed entirely - existing support_programs rows are unaffected",
            extra={"job": JOB, "source": "bizinfo", "status": "failed"},
        )
        return

    unchanged = collector.unchanged
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
            "written": result.persisted - unchanged,
            "unchanged": unchanged,
            "failed": result.failed,
            "complete": collector.complete,
        },
    )
    if result.errors:
        logger.warning(
            "bizinfo job had per-record errors",
            extra={"job": JOB, "source": "bizinfo", "errors": result.errors[:10]},
        )

    if stored is not None:
        try:
            support_programs.mark_bizinfo_seen(
                # Rows upserted just now already carry a fresh last_seen_at.
                support_programs.seen_refresh_due(
                    stored, collector.listed_ids - collector.written, started_at
                )
            )
        except Exception:
            logger.exception("bizinfo: recording listed rows as seen failed", extra={"job": JOB})

    if collector.complete:
        try:
            closed = support_programs.close_unlisted_bizinfo(collector.listed_ids, stored)
            logger.info(
                "bizinfo: closed unlisted announcements", extra={"job": JOB, "closed": closed}
            )
        except Exception:
            logger.exception("bizinfo: closing unlisted announcements failed", extra={"job": JOB})


def dedupe() -> None:
    kstartup = support_programs.fetch_open_kstartup_titles()
    bizinfo, marked_rows, current = support_programs.fetch_bizinfo_for_dedupe()
    originals = support_programs.fetch_program_titles(
        original_id for row in marked_rows if (original_id := current[row.id]) is not None
    )
    marked = [
        (row, originals[original_id])
        for row in marked_rows
        if (original_id := current[row.id]) is not None and original_id in originals
    ]
    changes = plan_duplicate_marks(keep=kstartup, hide=bizinfo, marked=marked, current=current)
    support_programs.set_duplicate_of(changes)
    logger.info(
        "bizinfo: cross-source dedupe finished",
        extra={
            "job": JOB,
            "kstartup_open": len(kstartup),
            "bizinfo_open": len(bizinfo),
            "already_marked": len(marked),
            "marked": sum(1 for value in changes.values() if value is not None),
            "cleared": sum(1 for value in changes.values() if value is None),
        },
    )
