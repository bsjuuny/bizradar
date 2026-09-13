"""Supabase persistence for the Telegram Watch digest job (worker/jobs/digest_job.py).
Service-role only, same pattern as worker/repositories/match_scores.py - RLS is
bypassed here by design.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from worker.repositories.opportunities import get_service_client

# .in_() puts every id into the request's query string - see
# worker/repositories/match_scores.py's chunking comment for why a large id list can
# blow the URL length limit. Same mitigation here.
_IN_CLAUSE_CHUNK_SIZE = 150


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def get_companies_with_telegram() -> list[dict[str, Any]]:
    """Companies that have registered a telegram_chat_id. Digest is opt-in - a company
    that never fills this in on Settings gets nothing, which is the intended default."""
    client = get_service_client()
    return cast(
        "list[dict[str, Any]]",
        client.table("companies")
        .select("id, name, telegram_chat_id")
        .not_.is_("telegram_chat_id", "null")
        .execute()
        .data
        or [],
    )


def get_active_watch_conditions(company_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Active watch_conditions grouped by company_id, for only the given companies."""
    client = get_service_client()
    if not company_ids:
        return {}

    rows: list[dict[str, Any]] = []
    for chunk in _chunked(company_ids, _IN_CLAUSE_CHUNK_SIZE):
        rows.extend(
            cast(
                "list[dict[str, Any]]",
                client.table("watch_conditions")
                .select(
                    "id, company_id, name, keyword, category, "
                    "min_budget, max_budget, min_match_score, active"
                )
                .eq("active", True)
                .in_("company_id", chunk)
                .execute()
                .data
                or [],
            )
        )

    by_company: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_company.setdefault(row["company_id"], []).append(row)
    return by_company


def get_recent_opportunities(since: datetime, limit: int = 200) -> list[dict[str, Any]]:
    """Opportunities posted since `since`, newest first. Mirrors the lookback window in
    apps/web/src/lib/digest.ts's in-app version - keep the two in sync if this changes."""
    client = get_service_client()
    return cast(
        "list[dict[str, Any]]",
        client.table("opportunities_current")
        .select("id, title, category, organization, budget_amount, posted_at, bid_close_at")
        .gte("posted_at", since.isoformat())
        .order("posted_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or [],
    )


def get_match_scores(
    company_ids: list[str], opportunity_ids: list[str]
) -> dict[tuple[str, str], float]:
    """(company_id, opportunity_id) -> total_score, for exactly the pairs the digest
    might need. Already-computed by match_job.py - this job never recomputes scores."""
    client = get_service_client()
    if not company_ids or not opportunity_ids:
        return {}

    scores: dict[tuple[str, str], float] = {}
    for company_chunk in _chunked(company_ids, _IN_CLAUSE_CHUNK_SIZE):
        for opp_chunk in _chunked(opportunity_ids, _IN_CLAUSE_CHUNK_SIZE):
            rows = cast(
                "list[dict[str, Any]]",
                client.table("match_scores")
                .select("company_id, opportunity_id, total_score")
                .in_("company_id", company_chunk)
                .in_("opportunity_id", opp_chunk)
                .execute()
                .data
                or [],
            )
            for row in rows:
                scores[(row["company_id"], row["opportunity_id"])] = row["total_score"]
    return scores


def get_already_sent(company_id: str, opportunity_ids: list[str]) -> set[str]:
    """opportunity_ids this company has already been notified about (any time), so a
    later run's overlapping lookback window doesn't repeat the same notice."""
    client = get_service_client()
    if not opportunity_ids:
        return set()

    sent: set[str] = set()
    for chunk in _chunked(opportunity_ids, _IN_CLAUSE_CHUNK_SIZE):
        rows = cast(
            "list[dict[str, Any]]",
            client.table("watch_notifications_sent")
            .select("opportunity_id")
            .eq("company_id", company_id)
            .in_("opportunity_id", chunk)
            .execute()
            .data
            or [],
        )
        sent.update(row["opportunity_id"] for row in rows)
    return sent


def mark_sent(company_id: str, opportunity_ids: list[str]) -> None:
    if not opportunity_ids:
        return
    client = get_service_client()
    rows = [{"company_id": company_id, "opportunity_id": opp_id} for opp_id in opportunity_ids]
    client.table("watch_notifications_sent").upsert(
        rows, on_conflict="company_id,opportunity_id"
    ).execute()
