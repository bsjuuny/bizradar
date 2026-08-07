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
        "model": model,
        "model_version": model_version,
        "prompt_version": prompt_version,
        "analyzed_at": datetime.now(UTC).isoformat(),
        "analyzed_content_hash": content_hash,
        "error_message": None,
    }
    client.table("project_analyses").upsert(row, on_conflict="opportunity_id").execute()


def upsert_failure(opportunity_id: str, content_hash: str, error_message: str) -> None:
    client = get_service_client()
    row = {
        "opportunity_id": opportunity_id,
        "status": "FAILED",
        "analyzed_at": datetime.now(UTC).isoformat(),
        "analyzed_content_hash": content_hash,
        "error_message": error_message[:2000],
    }
    client.table("project_analyses").upsert(row, on_conflict="opportunity_id").execute()


def get_pending_opportunities(category: str, limit: int) -> list[dict[str, Any]]:
    """Opportunities in `category` with no analysis yet, or whose existing analysis was
    computed against an older content_hash (the source G2B data changed since) - see
    docs/DATA_PIPELINE.md's idempotency section. Over-fetches candidates since some will
    already be up to date, then filters in Python: PostgREST can't easily express
    "column X != related row's column Y" as a single filter.
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
        .select("opportunity_id, analyzed_content_hash")
        .in_("opportunity_id", ids)
        .execute()
        .data
        or [],
    )
    analyzed_hash_by_opportunity = {
        row["opportunity_id"]: row["analyzed_content_hash"] for row in existing
    }

    pending = [
        c for c in candidates if analyzed_hash_by_opportunity.get(c["id"]) != c["content_hash"]
    ]
    return pending[:limit]
