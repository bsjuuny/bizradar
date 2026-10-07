"""Supabase persistence for support_programs. Uses the service_role client - RLS is
bypassed here by design (see docs/DATABASE.md), this is the only writer.

Whole-table reads page by id (worker/repositories/paging.py): never an unbounded select,
which max-rows silently truncates, and keyed rather than offset paging, so rows the
K-Startup or BizInfo job inserts meanwhile can't make a read skip or repeat a row."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import date, datetime
from typing import Any

from worker.collectors.bizinfo import BizInfoNormalizedProgram
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


def upsert_bizinfo_program(normalized: BizInfoNormalizedProgram) -> None:
    client = get_service_client()
    row = _common_row("bizinfo", normalized)
    row["application_period_text"] = normalized.application_period_text
    client.table("support_programs").upsert(row, on_conflict="source,external_id").execute()


def _read_all(table: str, columns: str, narrow: Callable[[Any], Any]) -> list[dict[str, Any]]:
    """Every row of `table` matching `narrow(query)`, paged by id (must be in `columns`)."""
    client = get_service_client()
    return fetch_all_pages(lambda: narrow(client.table(table).select(columns)), key="id")


def fetch_bizinfo_state() -> dict[str, tuple[str, bool | None]]:
    """external_id -> (content_hash, recruiting) for every stored 기업마당 row."""
    rows = _read_all(
        "support_programs",
        "id, external_id, content_hash, recruiting",
        lambda query: query.eq("source", "bizinfo"),
    )
    return {row["external_id"]: (row["content_hash"], row["recruiting"]) for row in rows}


def close_unlisted_bizinfo(listed_ids: Iterable[str]) -> int:
    """기업마당 목록에서 내려간 공고를 모집 마감으로 표시한다. Call only with the complete
    current list (BizInfoCollector.complete) - otherwise a truncated response would close
    announcements that are still open. Returns how many rows were closed."""
    listed = set(listed_ids)
    open_rows = _read_all(
        "support_programs",
        "id, external_id",
        lambda query: query.eq("source", "bizinfo").eq("recruiting", True),
    )
    stale = [row["id"] for row in open_rows if row["external_id"] not in listed]
    client = get_service_client()
    for chunk in chunked(stale, _UPDATE_CHUNK_SIZE):
        client.table("support_programs").update({"recruiting": False}).in_("id", chunk).execute()
    return len(stale)


def _to_date(value: str | None) -> date | None:
    return datetime.fromisoformat(value).date() if value else None


def _program_title(row: Mapping[str, Any]) -> ProgramTitle:
    return ProgramTitle(
        row["id"], row["title"], _to_date(row["application_end"]), row.get("region")
    )


def fetch_open_kstartup_titles() -> list[ProgramTitle]:
    """K-Startup rows that are open right now - the is_open computed column, the one
    definition of "모집 중" that the web filters on too
    (supabase/migrations/20261007130000_support_programs_listing.sql). A 기업마당 copy is
    paired only with an original the default 모집 중 view would actually show."""
    rows = _read_all(
        "support_programs",
        "id, title, application_end, region",
        lambda query: query.eq("source", "kstartup").eq("is_open", True),
    )
    return [_program_title(row) for row in rows]


def fetch_open_bizinfo_titles() -> tuple[list[ProgramTitle], dict[str, str | None]]:
    """The 기업마당 rows to pair (the recruiting ones) and the current duplicate_of of every
    기업마당 row that is recruiting *or* still carries a mark. Closed rows are never paired,
    so including their marks here is what clears them: otherwise a mark set while a row
    was open - or by an older rule - would stay on it forever after it closed."""
    rows = _read_all(
        "support_programs",
        "id, title, application_end, region, duplicate_of, recruiting",
        lambda query: query.eq("source", "bizinfo").or_(
            "recruiting.is.true,duplicate_of.not.is.null"
        ),
    )
    candidates = [_program_title(row) for row in rows if row["recruiting"] is True]
    return candidates, {row["id"]: row["duplicate_of"] for row in rows}


def set_duplicate_of(changes: Mapping[str, str | None]) -> None:
    client = get_service_client()
    for row_id, duplicate_of in changes.items():
        client.table("support_programs").update({"duplicate_of": duplicate_of}).eq(
            "id", row_id
        ).execute()


# Per source, the columns its collector's normalize() derives from the raw payload, i.e.
# the ones a rule or text-handling change can make stale (worker/jobs/support_reclassify.py).
# The dates are pure functions of the payload, so they are included (a parse_period fix
# must reach stored rows - and 기업마당's content_hash covers them). Never recruiting: it
# depends on when the row was collected and, for 기업마당, on the unlisted-closing pass -
# re-deriving it from an old payload would undo that.
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


def update_program(row_id: str, changes: Mapping[str, Any]) -> None:
    client = get_service_client()
    client.table("support_programs").update(dict(changes)).eq("id", row_id).execute()
