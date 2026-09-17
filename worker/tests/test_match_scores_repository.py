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
    def __init__(
        self,
        table_name: str,
        opportunities_by_id: dict[str, dict[str, Any]],
        in_clause_sizes: list[int],
        analyses_page_sizes: list[int],
        max_rows: int,
    ):
        self._table_name = table_name
        self._opportunities_by_id = opportunities_by_id
        self._in_clause_sizes = in_clause_sizes
        self._analyses_page_sizes = analyses_page_sizes
        self._max_rows = max_rows
        self._requested_ids: list[str] | None = None
        self._range: tuple[int, int] | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> "_FakeQuery":
        return self

    def eq(self, *_args: Any, **_kwargs: Any) -> "_FakeQuery":
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> "_FakeQuery":
        return self

    def range(self, start: int, end: int) -> "_FakeQuery":
        self._range = (start, end)
        return self

    def in_(self, _column: str, values: list[str]) -> "_FakeQuery":
        self._requested_ids = list(values)
        return self

    def execute(self) -> _FakeResult:
        if self._table_name == "project_analyses":
            rows = [
                {
                    "opportunity_id": oid,
                    "project_type": None,
                    "technologies": [],
                    "min_experience_years": None,
                    "required_qualifications": [],
                }
                for oid in self._opportunities_by_id
            ]
            # 실제 PostgREST의 동작을 그대로 흉내낸다: 범위를 주지 않으면 max_rows까지만
            # 오류 없이 잘려서 돌아오고, 범위를 줘도 한 페이지는 max_rows를 못 넘는다.
            if self._range is None:
                return _FakeResult(rows[: self._max_rows])
            start, end = self._range
            window = rows[start : end + 1][: self._max_rows]
            self._analyses_page_sizes.append(len(window))
            return _FakeResult(window)
        assert self._requested_ids is not None, "opportunities_current queried without .in_()"
        self._in_clause_sizes.append(len(self._requested_ids))
        return _FakeResult([self._opportunities_by_id[oid] for oid in self._requested_ids])


class _FakeClient:
    def __init__(self, opportunities_by_id: dict[str, dict[str, Any]], max_rows: int = 1000):
        self._opportunities_by_id = opportunities_by_id
        self._max_rows = max_rows
        self.in_clause_sizes: list[int] = []
        self.analyses_page_sizes: list[int] = []

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(
            name,
            self._opportunities_by_id,
            self.in_clause_sizes,
            self.analyses_page_sizes,
            self._max_rows,
        )


def test_get_analyzed_opportunities_chunks_the_in_clause(monkeypatch):
    # Regression test for the live 2026-08-26 incident: a single unchunked .in_()
    # call with hundreds of ids got rejected outright by Supabase's gateway with a
    # plain-text 400, and match_job had failed on every run since 2026-08-07 as a
    # result. This asserts every .in_() call stays within _IN_CLAUSE_CHUNK_SIZE and
    # that results from every chunk are still merged into the final return value.
    opportunities_by_id = {
        f"opp-{i}": {
            "id": f"opp-{i}",
            "budget_amount": i,
            "region_restriction": None,
            "bid_close_at": None,
        }
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


def test_get_analyzed_opportunities_pages_past_the_server_row_cap(monkeypatch):
    """PostgREST는 상한을 넘는 조회를 오류 없이 잘라서 돌려준다.

    2026-09-17 실측: project_analyses의 status=SUCCESS 1,902건 중 정확히 1,000건만
    반환돼 match_job이 903건만 채점했다. 버려진 쪽이 가장 최근에 분석된 건들이어서
    새로 수집된 공고에는 match_scores 행이 아예 없었고, 그래서 Watch 다이제스트에
    매칭 점수가 한 건도 찍히지 않았다. 잘려도 오류가 없으니 호출부는 완전한 결과와
    구분할 수 없다 - 명시적 페이지네이션 없이는 재발한다.
    """
    opportunities_by_id = {
        f"opp-{i:05d}": {
            "id": f"opp-{i:05d}",
            "budget_amount": i,
            "region_restriction": None,
            "bid_close_at": None,
        }
        for i in range(1902)
    }
    fake_client = _FakeClient(opportunities_by_id, max_rows=1000)
    monkeypatch.setattr(match_scores, "get_service_client", lambda: fake_client)

    results = get_analyzed_opportunities()

    assert len(results) == 1902
    assert {oid for oid, _ in results} == set(opportunities_by_id)
    # 한 번만 요청했다면 상한에서 잘린 것이다 - 여러 페이지를 실제로 읽어야 한다.
    assert len(fake_client.analyses_page_sizes) >= 2
    assert max(fake_client.analyses_page_sizes) <= 1000


def test_get_analyzed_opportunities_pages_when_server_cap_is_below_page_size(monkeypatch):
    # 서버 max-rows가 _PAGE_SIZE보다 작으면 첫 페이지가 요청보다 적게 돌아온다.
    # 그걸 "마지막 페이지"로 오해하면 다시 조용히 데이터를 잃는다.
    opportunities_by_id = {
        f"opp-{i:05d}": {
            "id": f"opp-{i:05d}",
            "budget_amount": i,
            "region_restriction": None,
            "bid_close_at": None,
        }
        for i in range(700)
    }
    fake_client = _FakeClient(opportunities_by_id, max_rows=200)
    monkeypatch.setattr(match_scores, "get_service_client", lambda: fake_client)

    results = get_analyzed_opportunities()

    assert len(results) == 700
    assert all(size <= 200 for size in fake_client.analyses_page_sizes)
