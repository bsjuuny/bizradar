"""Supabase persistence for project_analyses. Service-role only writer (see
docs/DATABASE.md); RLS bypassed here by design."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from worker.ai.schemas import ProjectExtraction
from worker.repositories.opportunities import get_service_client


def upsert_success(
    opportunity_id: str,
    content_hash: str,
    extraction: ProjectExtraction,
    *,
    model: str,
    model_version: str,
    prompt_version: str,
) -> None:
    client = get_service_client()
    row: dict[str, Any] = {
        "opportunity_id": opportunity_id,
        "status": "SUCCESS",
        "project_type": extraction.project_type,
        "technologies": [t.model_dump() for t in extraction.technologies],
        "required_roles": extraction.required_roles,
        "requirements": extraction.requirements,
        "risks": extraction.risks,
        "summary": extraction.summary,
        "min_experience_years": extraction.min_experience_years,
        "required_qualifications": extraction.required_qualifications,
        "model": model,
        "model_version": model_version,
        "prompt_version": prompt_version,
        "analyzed_at": datetime.now(UTC).isoformat(),
        "analyzed_content_hash": content_hash,
        "error_message": None,
    }
    client.table("project_analyses").upsert(row, on_conflict="opportunity_id").execute()


def upsert_failure(opportunity_id: str, content_hash: str, error_message: str) -> None:
    """`prompt_version` is deliberately set to `None`, not left out of the payload.

    An upsert only touches columns present in the payload - if `prompt_version` were
    omitted, a FAILED row would keep whatever version it last succeeded (or failed) at.
    That's a real bug found live: a reanalysis triggered purely by a `content_hash`
    change (not a prompt_version bump) that then fails leaves `analyzed_content_hash`
    matching the candidate and `prompt_version` still equal to the current version, so
    `get_pending_opportunities()`'s "needs reanalysis" check (hash OR version mismatch)
    is permanently false - the opportunity silently drops out of the pipeline until
    content changes *again* or the prompt bumps *again*. Forcing `prompt_version` to
    `None` on every failure guarantees a mismatch against any real current version, so a
    FAILED row is always retried on the next scheduled run - deliberately not
    distinguishing "transient infra failure" from "genuine bad extraction" here, since
    the alternative (silently dropping opportunities) is worse than a bounded amount of
    repeat Ollama calls on real failures."""
    client = get_service_client()
    row = {
        "opportunity_id": opportunity_id,
        "status": "FAILED",
        "analyzed_at": datetime.now(UTC).isoformat(),
        "analyzed_content_hash": content_hash,
        "prompt_version": None,
        "error_message": error_message[:2000],
    }
    client.table("project_analyses").upsert(row, on_conflict="opportunity_id").execute()


def get_pending_opportunities(
    category: str, limit: int, *, current_prompt_version: str
) -> list[dict[str, Any]]:
    """Opportunities in `category` with no analysis yet, whose existing analysis was
    computed against an older content_hash (the source G2B data changed since), or whose
    existing analysis used an older prompt_version (the extraction prompt/schema itself
    changed - e.g. Phase 5 added min_experience_years/required_qualifications, which a
    Phase-4-era analysis never asked for) - see docs/DATA_PIPELINE.md's idempotency
    section. Over-fetches candidates since some will already be up to date, then filters
    in Python: PostgREST can't easily express "column X != related row's column Y" as a
    single filter.
    """
    client = get_service_client()

    candidates = cast(
        "list[dict[str, Any]]",
        client.table("opportunities")
        .select("id, title, organization, demand_organization, budget_amount, content_hash")
        .eq("category", category)
        .order("posted_at", desc=True)
        .limit(max(limit * 4, 20))
        .execute()
        .data
        or [],
    )
    if not candidates:
        return []

    ids = [c["id"] for c in candidates]
    existing = cast(
        "list[dict[str, Any]]",
        client.table("project_analyses")
        .select("opportunity_id, analyzed_content_hash, prompt_version")
        .in_("opportunity_id", ids)
        .execute()
        .data
        or [],
    )
    existing_by_opportunity = {row["opportunity_id"]: row for row in existing}

    def needs_analysis(candidate: dict[str, Any]) -> bool:
        prior = existing_by_opportunity.get(candidate["id"])
        if prior is None:
            return True
        return (
            prior["analyzed_content_hash"] != candidate["content_hash"]
            or prior["prompt_version"] != current_prompt_version
        )

    pending = [c for c in candidates if needs_analysis(c)]
    return pending[:limit]
