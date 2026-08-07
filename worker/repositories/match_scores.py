"""Supabase persistence for match_scores. Service-role only writer (see
docs/DATABASE.md); RLS bypassed here by design.

Deliberately avoids PostgREST embeds across the project_analyses -> opportunities and
companies -> company_technologies -> technologies relationships: two of Phase 4/5's
gotchas were embeds not behaving as their schema-level cardinality suggests (see
docs/DATABASE.md). Fetching flat and joining in Python is more code but no surprises.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from worker.matching.engine import CompanyProfile, MatchScore, OpportunityRequirements
from worker.repositories.opportunities import get_service_client


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
    """Returns (opportunity_id, requirements) for every opportunity with a SUCCESS
    analysis - only these have anything for the Match Engine to score against."""
    client = get_service_client()

    analysis_columns = (
        "opportunity_id, project_type, technologies, min_experience_years, required_qualifications"
    )
    analyses = cast(
        "list[dict[str, Any]]",
        client.table("project_analyses")
        .select(analysis_columns)
        .eq("status", "SUCCESS")
        .execute()
        .data
        or [],
    )
    if not analyses:
        return []

    ids = [a["opportunity_id"] for a in analyses]
    opportunities = cast(
        "list[dict[str, Any]]",
        client.table("opportunities")
        .select("id, budget_amount, region_restriction, bid_close_at")
        .in_("id", ids)
        .execute()
        .data
        or [],
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
