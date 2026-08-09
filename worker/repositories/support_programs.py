"""Supabase persistence for support_programs. Uses the service_role client - RLS is
bypassed here by design (see docs/DATABASE.md), this is the only writer."""

from __future__ import annotations

from worker.collectors.kstartup import KStartupNormalizedProgram
from worker.repositories.opportunities import get_service_client


def upsert_support_program(normalized: KStartupNormalizedProgram) -> None:
    client = get_service_client()
    row = {
        "source": "kstartup",
        "external_id": normalized.external_id,
        "content_hash": normalized.content_hash,
        "title": normalized.title,
        "organization": normalized.organization,
        "department": normalized.department,
        "supervising_type": normalized.supervising_type,
        "category": normalized.category,
        "region": normalized.region,
        "target": normalized.target,
        "recruiting": normalized.recruiting,
        "investment_linked": normalized.investment_linked,
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
    client.table("support_programs").upsert(row, on_conflict="source,external_id").execute()
