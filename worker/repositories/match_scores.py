"""Supabase persistence for match_scores. Service-role only writer (see
docs/DATABASE.md); RLS bypassed here by design.

Deliberately avoids PostgREST embeds across the project_analyses -> opportunities and
companies -> company_technologies -> technologies relationships: two of Phase 4/5's
gotchas were embeds not behaving as their schema-level cardinality suggests (see
docs/DATABASE.md). Fetching flat and joining in Python is more code but no surprises.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

from worker.matching.engine import CompanyProfile, MatchScore, OpportunityRequirements
from worker.repositories.opportunities import get_service_client

# .in_() puts every id into the GET request's query string. Once project_analyses
# accumulates enough SUCCESS rows, that id list makes the URL long enough that
# Supabase's gateway rejects it outright with a plain-text 400 "Bad Request" (not
# PostgREST's usual JSON error body) before the query ever reaches PostgREST - live-
# reproduced 2026-08-26 with 769 ids producing a ~30KB URL, and confirmed as the
# reason match_job had failed on every single run since 2026-08-07: it made this
# request first, so match_scores never got computed at all. Chunking keeps each
# request's id list small regardless of how large project_analyses grows.
_IN_CLAUSE_CHUNK_SIZE = 150


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


# PostgREST caps an unbounded select at the project's max-rows setting and returns the
# truncated first page with no error and no warning - the caller cannot tell a complete
# result from a clipped one. Live on 2026-09-17: project_analyses held 1,902 SUCCESS
# rows, the unbounded select below returned exactly 1,000, and match_job consequently
# scored only 903 opportunities. The dropped rows were the most recently analyzed ones,
# so every newly collected opportunity was missing a match_scores row entirely and the
# Watch digest never had a score to show. Page explicitly instead of trusting an
# unbounded select to return everything.
_PAGE_SIZE = 1000


def _fetch_all_pages(build_query: Callable[[], Any]) -> list[dict[str, Any]]:
    """Reads every page of a select.

    ``build_query`` must return a fresh *ordered* query - paginating an unordered
    select lets rows repeat or go missing between requests, since PostgREST gives no
    stable row order without an explicit sort.

    Advances by however many rows actually came back rather than by _PAGE_SIZE, so a
    server-side max-rows smaller than _PAGE_SIZE still paginates to the end instead of
    stopping a page short.
    """
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = cast(
            "list[dict[str, Any]]",
            build_query().range(offset, offset + _PAGE_SIZE - 1).execute().data or [],
        )
        if not page:
            return rows
        rows.extend(page)
        offset += len(page)


def _parse_datetime(value: Any) -> datetime | None:
    # PostgREST returns timestamptz columns as plain JSON strings - supabase-py does no
    # automatic coercion. Found live: passing the raw string into
    # OpportunityRequirements.bid_close_at crashed worker/matching/engine.py's schedule
    # scoring the first time an opportunity actually had a non-null deadline.
    if not value:
        return None
    return datetime.fromisoformat(value)


def get_companies_for_matching() -> list[tuple[str, CompanyProfile]]:
    client = get_service_client()

    companies = cast(
        "list[dict[str, Any]]",
        client.table("companies")
        .select(
            "id, business_type, budget_min, budget_max, experience_years, qualifications, region"
        )
        .execute()
        .data
        or [],
    )
    if not companies:
        return []

    links = cast(
        "list[dict[str, Any]]",
        client.table("company_technologies").select("company_id, technologies(name)").execute().data
        or [],
    )
    tech_names_by_company: dict[str, set[str]] = {}
    for link in links:
        tech = link.get("technologies") or {}
        name = tech.get("name") if isinstance(tech, dict) else None
        if name:
            tech_names_by_company.setdefault(link["company_id"], set()).add(name)

    profiles = []
    for row in companies:
        profile = CompanyProfile(
            technologies=tech_names_by_company.get(row["id"], set()),
            business_type=row.get("business_type"),
            budget_min=row.get("budget_min"),
            budget_max=row.get("budget_max"),
            experience_years=row.get("experience_years", 0),
            qualifications=set(row.get("qualifications") or []),
            region=row.get("region"),
        )
        profiles.append((row["id"], profile))
    return profiles


def get_analyzed_opportunities() -> list[tuple[str, OpportunityRequirements]]:
    """Returns (opportunity_id, requirements) for every *current* opportunity with a
    SUCCESS analysis - only these have anything for the Match Engine to score against.
    Reads the opportunity side from opportunities_current, not the raw table, so a
    superseded/cancelled G2B notice revision (docs/DATA_PIPELINE.md#notice-thread-
    deduplication) is silently skipped via the existing `opp is None` fallback below,
    rather than getting a match_scores row nothing will ever display."""
    client = get_service_client()

    analysis_columns = (
        "opportunity_id, project_type, technologies, min_experience_years, required_qualifications"
    )
    analyses = _fetch_all_pages(
        lambda: (
            client.table("project_analyses")
            .select(analysis_columns)
            .eq("status", "SUCCESS")
            .order("opportunity_id")
        )
    )
    if not analyses:
        return []

    ids = [a["opportunity_id"] for a in analyses]
    opportunities: list[dict[str, Any]] = []
    for chunk in _chunked(ids, _IN_CLAUSE_CHUNK_SIZE):
        opportunities.extend(
            cast(
                "list[dict[str, Any]]",
                client.table("opportunities_current")
                .select("id, budget_amount, region_restriction, bid_close_at")
                .in_("id", chunk)
                .execute()
                .data
                or [],
            )
        )
    opp_by_id = {o["id"]: o for o in opportunities}

    results = []
    for analysis in analyses:
        opp = opp_by_id.get(analysis["opportunity_id"])
        if opp is None:
            continue
        tech_names = [t["name"] for t in (analysis.get("technologies") or []) if t.get("name")]
        results.append(
            (
                analysis["opportunity_id"],
                OpportunityRequirements(
                    technologies=tech_names,
                    project_type=analysis.get("project_type"),
                    budget_amount=opp.get("budget_amount"),
                    min_experience_years=analysis.get("min_experience_years"),
                    required_qualifications=analysis.get("required_qualifications") or [],
                    region_restriction=opp.get("region_restriction"),
                    bid_close_at=_parse_datetime(opp.get("bid_close_at")),
                ),
            )
        )
    return results


def upsert_match_score(company_id: str, opportunity_id: str, score: MatchScore) -> None:
    client = get_service_client()
    row: dict[str, Any] = {
        "company_id": company_id,
        "opportunity_id": opportunity_id,
        "technology_score": score.technology,
        "business_type_score": score.business_type,
        "budget_score": score.budget,
        "experience_score": score.experience,
        "qualification_score": score.qualification,
        "region_score": score.region,
        "schedule_score": score.schedule,
    }
    client.table("match_scores").upsert(row, on_conflict="company_id,opportunity_id").execute()
