"""Supabase persistence for opportunities. Uses the service_role client - RLS is
bypassed here by design (see docs/DATABASE.md), this is the only writer."""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from worker.collectors.g2b import G2BNormalizedOpportunity
from worker.config import get_settings


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not configured")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def upsert_opportunity(normalized: G2BNormalizedOpportunity) -> None:
    client = get_service_client()
    row = {
        "source": "g2b",
        "external_id": normalized.external_id,
        "content_hash": normalized.content_hash,
        "title": normalized.title,
        "category": normalized.category,
        "organization": normalized.organization,
        "demand_organization": normalized.demand_organization,
        "budget_amount": normalized.budget_amount,
        "estimated_price": normalized.estimated_price,
        "region_restriction": normalized.region_restriction,
        "posted_at": normalized.posted_at.isoformat() if normalized.posted_at else None,
        "bid_close_at": normalized.bid_close_at.isoformat() if normalized.bid_close_at else None,
        "open_at": normalized.open_at.isoformat() if normalized.open_at else None,
        "source_url": normalized.source_url,
        "raw_payload": normalized.raw_payload,
        "bid_ntce_no": normalized.bid_ntce_no,
        "bid_ntce_ord": normalized.bid_ntce_ord,
        "ntce_kind_nm": normalized.ntce_kind_nm,
        "industry_limited": normalized.industry_limited,
        "participation_limited": normalized.participation_limited,
        "procurement_category": normalized.procurement_category,
    }
    client.table("opportunities").upsert(row, on_conflict="source,external_id").execute()
