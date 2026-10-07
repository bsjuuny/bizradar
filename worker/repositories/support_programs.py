"""Supabase persistence for support_programs. Uses the service_role client - RLS is
bypassed here by design (see docs/DATABASE.md), this is the only writer."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any

from worker.collectors.bizinfo import BizInfoNormalizedProgram
from worker.collectors.kstartup import KStartupNormalizedProgram
from worker.dedupe.support_programs import ProgramTitle
from worker.repositories.opportunities import get_service_client

PAGE_SIZE = 1000


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


def _select_all(build_query: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = build_query().range(start, start + PAGE_SIZE - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE


def close_unlisted_bizinfo(listed_ids: Iterable[str]) -> int:
    """기업마당 목록에서 내려간 공고를 모집 마감으로 표시한다. Call only with the complete
    current list (BizInfoCollector.complete) - otherwise a truncated response would close
    announcements that are still open. Returns how many rows were closed."""
    client = get_service_client()
    listed = set(listed_ids)
    open_rows = _select_all(
        lambda: (
            client.table("support_programs")
            .select("id, external_id")
            .eq("source", "bizinfo")
            .eq("recruiting", True)
            .order("id")
        )
    )
    stale = [row["id"] for row in open_rows if row["external_id"] not in listed]
    for start in range(0, len(stale), 100):
        chunk = stale[start : start + 100]
        client.table("support_programs").update({"recruiting": False}).in_("id", chunk).execute()
    return len(stale)


def _to_date(value: str | None) -> date | None:
    return datetime.fromisoformat(value).date() if value else None


def fetch_open_kstartup_titles(today: date) -> list[ProgramTitle]:
    client = get_service_client()
    rows = _select_all(
        lambda: (
            client.table("support_programs")
            .select("id, title, application_end, recruiting")
            .eq("source", "kstartup")
            .or_(f"application_end.gte.{today.isoformat()},recruiting.eq.true")
            .order("id")
        )
    )
    return [ProgramTitle(row["id"], row["title"], _to_date(row["application_end"])) for row in rows]


def fetch_open_bizinfo_titles() -> tuple[list[ProgramTitle], dict[str, str | None]]:
    """Open 기업마당 rows, plus each one's current duplicate_of (to diff against)."""
    client = get_service_client()
    rows = _select_all(
        lambda: (
            client.table("support_programs")
            .select("id, title, application_end, duplicate_of")
            .eq("source", "bizinfo")
            .eq("recruiting", True)
            .order("id")
        )
    )
    titles = [
        ProgramTitle(row["id"], row["title"], _to_date(row["application_end"])) for row in rows
    ]
    return titles, {row["id"]: row["duplicate_of"] for row in rows}


def set_duplicate_of(changes: Mapping[str, str | None]) -> None:
    client = get_service_client()
    for row_id, duplicate_of in changes.items():
        client.table("support_programs").update({"duplicate_of": duplicate_of}).eq(
            "id", row_id
        ).execute()


# Columns derived from the source payload by the collectors' normalize(), i.e. the ones a
# rule change can make stale (worker/jobs/support_reclassify.py).
DERIVED_COLUMNS = (
    "title",
    "organization",
    "department",
    "supervising_type",
    "category",
    "region",
    "target",
    "description",
    "investment_linked",
    "it_related",
)


def fetch_programs_for_reclassify(source: str) -> list[dict[str, Any]]:
    """Every row of one source with its derived columns - plus raw_payload for K-Startup,
    whose normalize() is re-run from it. (BizInfo rows are only re-flagged from their
    title; their raw payloads are large and not needed.)"""
    client = get_service_client()
    columns = "id, external_id, " + ", ".join(DERIVED_COLUMNS)
    if source == "kstartup":
        columns += ", raw_payload"
    return _select_all(
        lambda: client.table("support_programs").select(columns).eq("source", source).order("id")
    )


def update_program(row_id: str, changes: Mapping[str, Any]) -> None:
    client = get_service_client()
    client.table("support_programs").update(dict(changes)).eq("id", row_id).execute()
