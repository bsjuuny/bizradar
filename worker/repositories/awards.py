"""Supabase persistence for G2B final award results."""

from __future__ import annotations

from worker.collectors.g2b_awards import G2BAwardResult
from worker.repositories.opportunities import get_service_client


def award_result_to_row(result: G2BAwardResult) -> dict[str, object]:
    return {
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


def upsert_award_results(
    results: list[G2BAwardResult],
    *,
    batch_size: int = 500,
) -> int:
    """Bulk-upsert normalized award results for historical backfills."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if not results:
        return 0

    rows = [award_result_to_row(result) for result in results]
    client = get_service_client()
    for offset in range(0, len(rows), batch_size):
        client.table("g2b_award_results").upsert(
            rows[offset : offset + batch_size],
            on_conflict="external_id",
        ).execute()
    return len(rows)


def upsert_award_result(result: G2BAwardResult) -> None:
    row = award_result_to_row(result)
    get_service_client().table("g2b_award_results").upsert(row, on_conflict="external_id").execute()
