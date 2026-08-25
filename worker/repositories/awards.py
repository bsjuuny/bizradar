"""Supabase persistence for G2B final award results."""

from __future__ import annotations

from worker.collectors.g2b_awards import G2BAwardResult
from worker.repositories.opportunities import get_service_client


def upsert_award_result(result: G2BAwardResult) -> None:
    row = {
        "external_id": result.external_id,
        "bid_ntce_no": result.bid_ntce_no,
        "bid_ntce_ord": result.bid_ntce_ord,
        "bid_classification_no": result.bid_classification_no,
        "rebid_no": result.rebid_no,
        "title": result.title,
        "winner_name": result.winner_name,
        "winner_business_no": result.winner_business_no,
        "winner_representative": result.winner_representative,
        "winner_address": result.winner_address,
        "award_amount": result.award_amount,
        "award_rate": result.award_rate,
        "planned_price": result.planned_price,
        "participant_count": result.participant_count,
        "opened_at": result.opened_at.isoformat() if result.opened_at else None,
        "awarded_at": result.awarded_at.date().isoformat() if result.awarded_at else None,
        "raw_payload": result.raw_payload,
    }
    get_service_client().table("g2b_award_results").upsert(row, on_conflict="external_id").execute()
