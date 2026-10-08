"""Supabase persistence for support_programs. Uses the service_role client - RLS is
bypassed here by design (see docs/DATABASE.md), this is the only writer.

Whole-table reads page by id (worker/repositories/paging.py): never an unbounded select,
which max-rows silently truncates, and keyed rather than offset paging, so rows the
K-Startup or BizInfo job inserts meanwhile can't make a read skip or repeat a row."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from worker.collectors.bizinfo import BizInfoNormalizedProgram, StoredRow
from worker.collectors.kstartup import KStartupNormalizedProgram
from worker.dedupe.support_programs import ProgramTitle
from worker.repositories.opportunities import get_service_client
from worker.repositories.paging import chunked, fetch_all_pages

_UPDATE_CHUNK_SIZE = 100


def _common_row(
    source: str, normalized: KStartupNormalizedProgram | BizInfoNormalizedProgram
) -> dict[str, Any]:
    # duplicate_of is deliberately absent: it belongs to the dedupe pass, and an upsert
    # only overwrites the columns it sends.
    return {
        "source": source,
        "external_id": normalized.external_id,
        "content_hash": normalized.content_hash,
        "title": normalized.title,
        "organization": normalized.organization,
        "department": normalized.department,
        "category": normalized.category,
        "region": normalized.region,
        "target": normalized.target,
        "recruiting": normalized.recruiting,
        "investment_linked": normalized.investment_linked,
        "it_related": normalized.it_related,
        "application_start": (
            normalized.application_start.isoformat() if normalized.application_start else None
        ),
        "application_end": (
            normalized.application_end.isoformat() if normalized.application_end else None
        ),
        "description": normalized.description,
        "source_url": normalized.source_url,
        "raw_payload": normalized.raw_payload,
    }


def upsert_support_program(normalized: KStartupNormalizedProgram) -> None:
    client = get_service_client()
    row = _common_row("kstartup", normalized)
    row["supervising_type"] = normalized.supervising_type
    client.table("support_programs").upsert(row, on_conflict="source,external_id").execute()


def upsert_bizinfo_programs(programs: Sequence[BizInfoNormalizedProgram]) -> None:
    """One request for all of `programs` (callers chunk them). Every row has the same keys,
    as a multi-row upsert requires."""
    client = get_service_client()
    # Only ever written for postings that are in the response being persisted.
    seen_at = datetime.now(UTC).isoformat()
    rows = []
    for normalized in programs:
        row = _common_row("bizinfo", normalized)
        row["application_period_text"] = normalized.application_period_text
        row["last_seen_at"] = seen_at
        rows.append(row)
    client.table("support_programs").upsert(rows, on_conflict="source,external_id").execute()


def _read_all(table: str, columns: str, narrow: Callable[[Any], Any]) -> list[dict[str, Any]]:
    """Every row of `table` matching `narrow(query)`, paged by id (must be in `columns`)."""
    client = get_service_client()
    return fetch_all_pages(lambda: narrow(client.table(table).select(columns)), key="id")


# A listed row's last_seen_at is rewritten only once it is this old, so the hourly run
# doesn't rewrite all ~1,450 rows (each update also bumps updated_at and leaves a dead
# tuple). is_open() treats a date-less row as gone after 3 days unseen
# (supabase/migrations/20261008100000_support_programs_open_status.sql) - that must stay well above
# this interval, or listed rows would flicker out between refreshes
# (test_support_programs_repository.py checks it against the migration).
LAST_SEEN_REFRESH_AFTER = timedelta(days=1)
# What the hourly reads look at: 기업마당 rows seen in the list this recently. Every listed
# row was refreshed within LAST_SEEN_REFRESH_AFTER (plus a run), so this covers them with a
# wide margin, and it keeps the reads the size of a month of listings even if the closing
# pass stalls - otherwise delisted rows would stay recruiting=true and pile into every read.
_STATE_WINDOW = timedelta(days=30)
# K-Startup originals a 기업마당 copy may pair with: open ones and those closed this
# recently, so a copy first collected just after its original closed still pairs (pairing
# never changes status - it only collapses the two into one listed row).
PAIRING_WINDOW = timedelta(days=30)


def _parse_timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _recent_or_dated_open() -> str:
    """PostgREST or-filter: 기업마당 rows seen within _STATE_WINDOW, or still recruiting with
    a deadline not yet passed (bounded by the dated open postings, ~500)."""
    now = datetime.now(UTC)
    since = (now - _STATE_WINDOW).isoformat()
    today = datetime.combine(now.date(), datetime.min.time(), tzinfo=UTC).isoformat()
    return f'last_seen_at.gte."{since}",and(recruiting.is.true,application_end.gte."{today}")'


def fetch_bizinfo_state() -> dict[str, StoredRow]:
    """external_id -> StoredRow for the 기업마당 rows a run can touch: those seen in the
    list within _STATE_WINDOW - every listed row, including a listed posting past its
    deadline (stored closed, still recognized as unchanged), and every recruiting row the
    closing pass may need to close. Not the closed history - ~1,500 new postings a month
    pile up there, and a posting that reappears after that long is simply written again.
    Recruiting rows with a deadline still ahead are read however long ago they were seen:
    is_open keeps those open until their date, so if one was delisted while the closing
    pass was stalled for over _STATE_WINDOW, the pass must still find and close it. A
    date-less recruiting row unseen that long drops out - is_open already treats it as
    closed (3 days unseen), so only its stored flag lags."""
    rows = _read_all(
        "support_programs",
        "id, external_id, content_hash, recruiting, last_seen_at",
        lambda query: query.eq("source", "bizinfo").or_(_recent_or_dated_open()),
    )
    return {
        row["external_id"]: StoredRow(
            row["id"],
            row["content_hash"],
            row["recruiting"],
            _parse_timestamp(row["last_seen_at"]),
        )
        for row in rows
    }


def seen_refresh_due(
    stored: Mapping[str, StoredRow], listed_ids: Iterable[str], now: datetime
) -> list[str]:
    """Ids of the stored rows that are in the list just fetched and whose last_seen_at is
    missing or older than LAST_SEEN_REFRESH_AFTER - whether persist() skipped them, wrote
    them or failed on them: being listed is what counts."""
    cutoff = now - LAST_SEEN_REFRESH_AFTER
    due = []
    for external_id in listed_ids:
        row = stored.get(external_id)
        if row is not None and (row.last_seen_at is None or row.last_seen_at < cutoff):
            due.append(row.id)
    return due


def mark_bizinfo_seen(row_ids: Sequence[str]) -> None:
    """Record that these rows were in the list just fetched (seen_refresh_due). is_open()
    stops counting a 기업마당 row as open once it has gone 3 days unseen."""
    update_programs(row_ids, {"last_seen_at": datetime.now(UTC).isoformat()})


def close_unlisted_bizinfo(
    listed_ids: Iterable[str], stored: Mapping[str, StoredRow] | None = None
) -> int:
    """기업마당 목록에서 내려간 공고를 모집 마감으로 표시한다. Call only with the complete
    current list (BizInfoCollector.complete) - otherwise a truncated response would close
    announcements that are still open. `stored` is fetch_bizinfo_state() as read before
    the run (the job already has it); rows that became recruiting since are all listed,
    so its recruiting rows are still the full set to check. Read here when not given.
    Returns how many rows were closed."""
    if stored is None:
        stored = fetch_bizinfo_state()
    listed = set(listed_ids)
    stale = [
        row.id
        for external_id, row in stored.items()
        if row.recruiting and external_id not in listed
    ]
    update_programs(stale, {"recruiting": False})
    return len(stale)


def _to_date(value: str | None) -> date | None:
    return datetime.fromisoformat(value).date() if value else None


def _program_title(row: Mapping[str, Any]) -> ProgramTitle:
    return ProgramTitle(
        row["id"], row["title"], _to_date(row["application_end"]), row.get("region")
    )


def fetch_kstartup_pairing_titles() -> list[ProgramTitle]:
    """K-Startup rows a 기업마당 copy may pair with: undated ones and those whose deadline
    is at most PAIRING_WINDOW ago - all open ones (K-Startup rows close on their date) and
    the recently closed. "Open" elsewhere is the is_open computed column, the one
    definition of "모집 중" that the web filters on too
    (supabase/migrations/20261008100000_support_programs_open_status.sql). A
    pairing itself never changes a row's status."""
    since = (datetime.now(UTC) - PAIRING_WINDOW).isoformat()
    rows = _read_all(
        "support_programs",
        "id, title, application_end, region",
        lambda query: query.eq("source", "kstartup").or_(
            f'application_end.is.null,application_end.gte."{since}"'
        ),
    )
    return [_program_title(row) for row in rows]


def fetch_bizinfo_for_dedupe() -> tuple[
    list[ProgramTitle], list[ProgramTitle], dict[str, str | None]
]:
    """(open rows to pair, rows that carry a mark, id -> current duplicate_of of both).

    "Open" is is_open. An open 기업마당 row has been seen within 3 days or carries a
    future date while listed - either way within _STATE_WINDOW - so the recent-or-marked
    read covers every candidate. Marked rows are read whether open
    or not: plan_duplicate_marks re-checks each against its original, so a rule change
    reaches old pairs too. That set only grows with real duplicates - 17 of ~1,450 open
    postings on 2026-10-07, so a few hundred a year: one page, and microseconds to
    re-match."""
    rows = _read_all(
        "support_programs",
        "id, title, application_end, region, duplicate_of, is_open",
        lambda query: query.eq("source", "bizinfo").or_(
            f"{_recent_or_dated_open()},duplicate_of.not.is.null"
        ),
    )
    open_rows = [_program_title(row) for row in rows if row["is_open"] is True]
    marked_rows = [_program_title(row) for row in rows if row["duplicate_of"] is not None]
    return open_rows, marked_rows, {row["id"]: row["duplicate_of"] for row in rows}


def fetch_program_titles(row_ids: Iterable[str]) -> dict[str, ProgramTitle]:
    """id -> ProgramTitle for the given rows (the originals of marked copies)."""
    client = get_service_client()
    titles: dict[str, ProgramTitle] = {}
    for chunk in chunked(sorted(set(row_ids)), _UPDATE_CHUNK_SIZE):
        rows = cast(
            list[dict[str, Any]],
            client.table("support_programs")
            .select("id, title, application_end, region")
            .in_("id", chunk)
            .execute()
            .data,
        )
        for row in rows:
            titles[row["id"]] = _program_title(row)
    return titles


def set_duplicate_of(changes: Mapping[str, str | None]) -> None:
    """One request per distinct value (per chunk) rather than per row: a rule change can
    clear or set hundreds of marks at once."""
    by_value: dict[str | None, list[str]] = {}
    for row_id, duplicate_of in changes.items():
        by_value.setdefault(duplicate_of, []).append(row_id)
    for duplicate_of, row_ids in by_value.items():
        update_programs(row_ids, {"duplicate_of": duplicate_of})


# Per source, the columns its collector's normalize() derives from the raw payload, i.e.
# the ones a rule or text-handling change can make stale (worker/jobs/support_reclassify.py).
# The dates are pure functions of the payload, so they are included (a parse_period fix
# must reach stored rows - and 기업마당's content_hash covers them). Never recruiting: it
# depends on when the row was collected and, for 기업마당, on the unlisted-closing pass -
# re-deriving it from an old payload would undo that. Nor last_seen_at: it records when
# the posting was in a response, not anything in its payload.
_SHARED_DERIVED = (
    "application_start",
    "application_end",
    "title",
    "organization",
    "department",
    "category",
    "region",
    "target",
    "description",
    "investment_linked",
    "it_related",
    "source_url",
)
DERIVED_COLUMNS: dict[str, tuple[str, ...]] = {
    "kstartup": (*_SHARED_DERIVED, "supervising_type"),
    # content_hash too: for 기업마당 it covers the derived columns (BizInfoCollector), so
    # leaving it stale would make the next hourly run re-send every reclassified row.
    "bizinfo": (*_SHARED_DERIVED, "application_period_text", "content_hash"),
}


def fetch_programs_for_reclassify(source: str) -> list[dict[str, Any]]:
    """Every row of one source: its derived columns plus the raw_payload they come from."""
    return _read_all(
        "support_programs",
        "id, external_id, raw_payload, " + ", ".join(DERIVED_COLUMNS[source]),
        lambda query: query.eq("source", source),
    )


def update_programs(row_ids: Sequence[str], changes: Mapping[str, Any]) -> None:
    """Write the same `changes` to every row in `row_ids`, a chunk per request."""
    client = get_service_client()
    for chunk in chunked(row_ids, _UPDATE_CHUNK_SIZE):
        client.table("support_programs").update(dict(changes)).in_("id", chunk).execute()
