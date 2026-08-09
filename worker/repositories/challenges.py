"""Supabase persistence for canonical Challenge records."""

from __future__ import annotations

from typing import Any, cast

from worker.challenges.models import ChallengeAIAnalysis, ChallengeNormalized
from worker.repositories.opportunities import get_service_client


def _dt(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _row(normalized: ChallengeNormalized) -> dict[str, Any]:
    policy = normalized.ai_policy
    return {
        "source_id": normalized.source_id,
        "source_name": normalized.source_name,
        "source_type": normalized.source_type,
        "source_priority": normalized.source_priority,
        "external_id": normalized.external_id,
        "dedupe_key": normalized.dedupe_key,
        "content_hash": normalized.content_hash,
        "title": normalized.title,
        "summary": normalized.summary,
        "description": normalized.description,
        "challenge_type": normalized.challenge_type,
        "organizer": normalized.organizer,
        "host": normalized.host,
        "sponsor": normalized.sponsor,
        "start_date": _dt(normalized.start_date),
        "end_date": _dt(normalized.end_date),
        "apply_start_date": _dt(normalized.apply_start_date),
        "apply_end_date": _dt(normalized.apply_end_date),
        "result_date": _dt(normalized.result_date),
        "eligibility": normalized.eligibility,
        "eligibility_type": normalized.eligibility_type,
        "team_min": normalized.team_min,
        "team_max": normalized.team_max,
        "region": normalized.region,
        "participation_type": normalized.participation_type,
        "prize": normalized.prize,
        "total_prize_amount": normalized.total_prize_amount,
        "currency": normalized.currency,
        "prize_description": normalized.prize_description,
        "source_url": normalized.source_url,
        "application_url": normalized.application_url,
        "thumbnail_url": normalized.thumbnail_url,
        "required_documents": normalized.required_documents,
        "submission_requirements": normalized.submission_requirements,
        "technology_keywords": normalized.technology_keywords,
        "categories": normalized.categories,
        "tags": normalized.tags,
        "attachments": [item.model_dump() for item in normalized.attachments],
        "ai_policy": policy.status,
        "ai_policy_confidence": policy.confidence,
        "ai_policy_evidence": policy.evidence,
        "ai_policy_source_section": policy.source_section,
        "generative_ai_policy": normalized.generative_ai_policy,
        "ai_coding_policy": normalized.ai_coding_policy,
        "llm_policy": normalized.llm_policy,
        "ai_image_policy": normalized.ai_image_policy,
        "ai_video_policy": normalized.ai_video_policy,
        "ai_audio_policy": normalized.ai_audio_policy,
        "external_ai_api_policy": normalized.external_ai_api_policy,
        "prompt_disclosure_required": normalized.prompt_disclosure_required,
        "ai_usage_disclosure_required": normalized.ai_usage_disclosure_required,
        "analysis_status": normalized.analysis_status,
        "analysis_error": normalized.analysis_error,
        "external_api_policy": normalized.external_api_policy,
        "open_source_policy": normalized.open_source_policy,
        "copyright_policy": normalized.copyright_policy,
        "ownership_policy": normalized.ownership_policy,
        "original_text": normalized.original_text,
        "search_text": normalized.search_text,
        "status": normalized.status,
        "raw_payload": normalized.raw_payload,
        "collected_at": normalized.collected_at.isoformat(),
        "last_checked_at": normalized.last_checked_at.isoformat(),
    }


def upsert_challenge(normalized: ChallengeNormalized) -> None:
    client = get_service_client()
    response = (
        client.table("challenges")
        .select("id,source_priority,content_hash")
        .eq("dedupe_key", normalized.dedupe_key)
        .limit(1)
        .execute()
    )
    existing = cast("list[dict[str, Any]]", response.data or [])
    row = _row(normalized)
    if not existing:
        client.table("challenges").upsert(row, on_conflict="dedupe_key").execute()
        return

    current = existing[0]
    if normalized.source_priority > int(current["source_priority"]):
        client.table("challenges").update(
            {"last_checked_at": normalized.last_checked_at.isoformat()}
        ).eq("id", current["id"]).execute()
        return

    if current.get("content_hash") == normalized.content_hash:
        for key in tuple(row):
            if key.startswith("ai_") or key in {
                "analysis_status",
                "analysis_error",
                "generative_ai_policy",
                "llm_policy",
                "external_ai_api_policy",
            }:
                row.pop(key)
    client.table("challenges").update(row).eq("id", current["id"]).execute()


def get_pending_challenges(limit: int) -> list[dict[str, Any]]:
    response = (
        get_service_client()
        .table("challenges")
        .select("id,title,original_text,content_hash")
        # FAILED records retain the conservative rule-based fallback. Requeue only
        # after a content change resets analysis_status to PENDING, avoiding an
        # unbounded LLM retry/cost loop.
        .eq("analysis_status", "PENDING")
        .order("last_checked_at")
        .limit(limit)
        .execute()
    )
    return cast("list[dict[str, Any]]", response.data or [])


def update_challenge_analysis(
    challenge_id: str,
    analysis: ChallengeAIAnalysis,
    *,
    status: str,
    error: str | None,
    model: str | None,
    prompt_version: str,
) -> None:
    row: dict[str, Any] = {
        "challenge_type": analysis.challenge_type,
        "ai_policy": analysis.ai_policy.status,
        "ai_policy_confidence": analysis.ai_policy.confidence,
        "ai_policy_evidence": analysis.ai_policy.evidence,
        "ai_policy_source_section": analysis.ai_policy.source_section,
        "generative_ai_policy": analysis.generative_ai.status,
        "ai_coding_policy": analysis.ai_coding.status,
        "llm_policy": analysis.generative_ai.status,
        "ai_image_policy": analysis.ai_image.status,
        "ai_video_policy": analysis.ai_video.status,
        "ai_audio_policy": analysis.ai_audio.status,
        "external_ai_api_policy": analysis.external_ai_api.status,
        "prompt_disclosure_required": analysis.prompt_disclosure_required,
        "ai_usage_disclosure_required": analysis.ai_usage_disclosure_required,
        "analysis_status": status,
        "analysis_error": error[:1000] if error else None,
        "analysis_model": model,
        "analysis_prompt_version": prompt_version,
        "analyzed_at": None,
    }
    # PostgREST does not evaluate SQL expressions in JSON values. Use an actual timestamp.
    from datetime import UTC, datetime

    row["analyzed_at"] = datetime.now(UTC).isoformat()
    get_service_client().table("challenges").update(row).eq("id", challenge_id).execute()


def record_source_status(
    *,
    source_id: str,
    source_name: str,
    status: str,
    fetched: int,
    error: str | None,
) -> None:
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    row: dict[str, Any] = {
        "source_id": source_id,
        "source_name": source_name,
        "enabled": True,
        "last_run_at": now,
        "last_status": status,
        "fetched": fetched,
        "error": error[:1000] if error else None,
    }
    if status in {"SUCCESS", "PARTIAL_SUCCESS"}:
        row["last_success_at"] = now
    else:
        row["last_failure_at"] = now
    get_service_client().table("challenge_source_status").upsert(
        row, on_conflict="source_id"
    ).execute()
