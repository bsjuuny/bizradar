from datetime import datetime
from zoneinfo import ZoneInfo

from worker.collectors.g2b_awards import G2BAwardResult
from worker.repositories import awards


class _FakeExecute:
    def execute(self):
        return None


class _FakeTable:
    def __init__(self, captured: list[dict]):
        self._captured = captured

    def upsert(self, row: dict, on_conflict: str):
        assert on_conflict == "external_id"
        self._captured.append(row)
        return _FakeExecute()


class _FakeClient:
    def __init__(self, captured: list[dict]):
        self._captured = captured

    def table(self, name: str):
        assert name == "g2b_award_results"
        return _FakeTable(self._captured)


def test_upsert_maps_normalized_award(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(awards, "get_service_client", lambda: _FakeClient(captured))
    result = G2BAwardResult(
        external_id="R26-000-0-0",
        bid_ntce_no="R26",
        winner_name="테스트 업체",
        award_amount=100_000_000,
        award_rate=88.1,
        opened_at=datetime(2026, 8, 25, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        awarded_at=datetime(2026, 8, 26, tzinfo=ZoneInfo("Asia/Seoul")),
        raw_payload={"source": "fixture"},
    )

    awards.upsert_award_result(result)

    assert captured == [
        {
            "external_id": "R26-000-0-0",
            "bid_ntce_no": "R26",
            "bid_ntce_ord": 0,
            "bid_classification_no": "0",
            "rebid_no": 0,
            "title": None,
            "winner_name": "테스트 업체",
            "winner_business_no": None,
            "winner_representative": None,
            "winner_address": None,
            "award_amount": 100_000_000,
            "award_rate": 88.1,
            "planned_price": None,
            "participant_count": None,
            "opened_at": "2026-08-25T10:00:00+09:00",
            "awarded_at": "2026-08-26",
            "raw_payload": {"source": "fixture"},
        }
    ]


def test_bulk_upsert_batches_rows(monkeypatch):
    captured: list[list[dict]] = []
    monkeypatch.setattr(awards, "get_service_client", lambda: _FakeClient(captured))
    results = [
        G2BAwardResult(
            external_id=f"R26-{index}",
            bid_ntce_no=f"R26-{index}",
            winner_name=f"winner-{index}",
            raw_payload={"index": index},
        )
        for index in range(3)
    ]

    persisted = awards.upsert_award_results(results, batch_size=2)

    assert persisted == 3
    assert [[row["external_id"] for row in batch] for batch in captured] == [
        ["R26-0", "R26-1"],
        ["R26-2"],
    ]


def test_bulk_upsert_empty_results_does_not_create_client(monkeypatch):
    monkeypatch.setattr(
        awards,
        "get_service_client",
        lambda: (_ for _ in ()).throw(AssertionError("client should not be created")),
    )

    assert awards.upsert_award_results([]) == 0
