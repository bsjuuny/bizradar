from datetime import datetime
from typing import Any

from worker.repositories import match_scores
from worker.repositories.match_scores import _chunked, _parse_datetime, get_analyzed_opportunities


def test_parses_a_real_postgrest_timestamptz_string():
    # Exact shape PostgREST returned live and crashed on before this was added.
    parsed = _parse_datetime("2026-08-19T10:00:00+00:00")
    assert parsed == datetime.fromisoformat("2026-08-19T10:00:00+00:00")


def test_none_and_empty_string_both_map_to_none():
    assert _parse_datetime(None) is None
    assert _parse_datetime("") is None


def test_chunked_splits_into_bounded_groups():
    assert _chunked(list(range(7)), 3) == [[0, 1, 2], [3, 4, 5], [6]]
    assert _chunked([], 3) == []
    assert _chunked([1, 2], 5) == [[1, 2]]


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, table_name: str, opportunities_by_id: dict[str, dict[str, Any]], in_clause_sizes: list[int]):
        self._table_name = table_name
        self._opportunities_by_id = opportunities_by_id
        self._in_clause_sizes = in_clause_sizes
        self._requested_ids: list[str] | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> "_FakeQuery":
        return self

    def eq(self, *_args: Any, **_kwargs: Any) -> "_FakeQuery":
        return self

    def in_(self, _column: str, values: list[str]) -> "_FakeQuery":
        self._requested_ids = list(values)
        return self

    def execute(self) -> _FakeResult:
        if self._table_name == "project_analyses":
            return _FakeResult(
                [{"opportunity_id": oid, "project_type": None, "technologies": [],
                  "min_experience_years": None, "required_qualifications": []}
                 for oid in self._opportunities_by_id]
            )
        assert self._requested_ids is not None, "opportunities_current queried without .in_()"
        self._in_clause_sizes.append(len(self._requested_ids))
        return _FakeResult([self._opportunities_by_id[oid] for oid in self._requested_ids])


class _FakeClient:
    def __init__(self, opportunities_by_id: dict[str, dict[str, Any]]):
        self._opportunities_by_id = opportunities_by_id
        self.in_clause_sizes: list[int] = []

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(name, self._opportunities_by_id, self.in_clause_sizes)


def test_get_analyzed_opportunities_chunks_the_in_clause(monkeypatch):
    # Regression test for the live 2026-08-26 incident: a single unchunked .in_()
    # call with hundreds of ids got rejected outright by Supabase's gateway with a
    # plain-text 400, and match_job had failed on every run since 2026-08-07 as a
    # result. This asserts every .in_() call stays within _IN_CLAUSE_CHUNK_SIZE and
    # that results from every chunk are still merged into the final return value.
    opportunities_by_id = {
        f"opp-{i}": {"id": f"opp-{i}", "budget_amount": i, "region_restriction": None, "bid_close_at": None}
        for i in range(match_scores._IN_CLAUSE_CHUNK_SIZE * 2 + 5)
    }
    fake_client = _FakeClient(opportunities_by_id)
    monkeypatch.setattr(match_scores, "get_service_client", lambda: fake_client)

    results = get_analyzed_opportunities()

    assert len(results) == len(opportunities_by_id)
    assert {oid for oid, _ in results} == set(opportunities_by_id)
    assert len(fake_client.in_clause_sizes) == 3  # 150 + 150 + 5
    assert all(size <= match_scores._IN_CLAUSE_CHUNK_SIZE for size in fake_client.in_clause_sizes)


def test_get_analyzed_opportunities_empty_analyses_makes_no_opportunities_call(monkeypatch):
    fake_client = _FakeClient({})
    monkeypatch.setattr(match_scores, "get_service_client", lambda: fake_client)

    assert get_analyzed_opportunities() == []
    assert fake_client.in_clause_sizes == []
