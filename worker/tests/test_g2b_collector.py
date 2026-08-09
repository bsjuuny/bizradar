import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from worker.collectors.base import CollectorError, RawRecord
from worker.collectors.g2b import G2BCollector, _parse_yn, compute_content_hash, parse_response_body
from worker.config import Settings

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "g2b"


def _settings(api_key: str | None = "test-key") -> Settings:
    return Settings(_env_file=None, g2b_api_key=api_key)


def test_parse_response_body_success():
    text = (FIXTURES / "bid_list_servc_sample.json").read_text(encoding="utf-8")
    body = parse_response_body(text)

    assert body["totalCount"] >= 5
    assert len(body["items"]) == 5
    assert body["items"][0]["bidNtceNo"] == "R26BK01664082"


def test_parse_response_body_empty_result():
    text = (FIXTURES / "bid_list_servc_empty.json").read_text(encoding="utf-8")
    body = parse_response_body(text)

    assert body["items"] == []
    assert body["totalCount"] == 0


def test_parse_response_body_service_error_raises():
    text = (FIXTURES / "bid_list_service_error.json").read_text(encoding="utf-8")

    with pytest.raises(CollectorError, match="등록되지 않은 서비스키"):
        parse_response_body(text)


def test_parse_response_body_malformed_html_raises_not_crashes():
    text = (FIXTURES / "bid_list_malformed.html").read_text(encoding="utf-8")

    with pytest.raises(CollectorError, match="non-JSON"):
        parse_response_body(text)


def test_normalize_maps_real_fields():
    text = (FIXTURES / "bid_list_servc_sample.json").read_text(encoding="utf-8")
    item = json.loads(text)["response"]["body"]["items"][0]

    collector = G2BCollector(settings=_settings())
    raw = RawRecord(
        source="g2b",
        external_id="R26BK01664082-000",
        fetched_at=datetime.now(UTC),
        payload=item,
    )
    normalized = collector.normalize(raw)

    assert normalized.title == "2026학년도 명덕여자중학교 3학년 소규모테마형교육여행 위탁용역"
    assert normalized.organization == "서울특별시강서교육청 명덕여자중학교"
    assert normalized.posted_at == datetime(2026, 8, 4, 8, 25, 58)
    assert normalized.bid_close_at == datetime(2026, 8, 18, 12, 0, 0)
    assert normalized.content_hash == compute_content_hash(item)
    # A school trip - the rule filter (worker/ai/rule_filter.py) should route this away
    # from the LLM, not just leave it UNKNOWN.
    assert normalized.category == "NON_IT"
    # Notice-thread identity (docs/DATA_PIPELINE.md#notice-thread-deduplication).
    assert normalized.bid_ntce_no == "R26BK01664082"
    assert normalized.bid_ntce_ord == 0
    assert normalized.ntce_kind_nm == "등록공고"
    # Market-stats fields (docs/DATA_PIPELINE.md#market-statistics).
    assert normalized.industry_limited is True
    assert normalized.participation_limited is False
    assert normalized.procurement_category == "국내여행서비스"


def test_normalize_handles_missing_and_zero_amounts():
    collector = G2BCollector(settings=_settings())
    raw = RawRecord(
        source="g2b",
        external_id="X-000",
        fetched_at=datetime.now(UTC),
        payload={"bidNtceNm": "Test", "asignBdgtAmt": "0", "presmptPrce": ""},
    )
    normalized = collector.normalize(raw)

    assert normalized.budget_amount is None
    assert normalized.estimated_price is None
    assert normalized.bid_ntce_no is None
    assert normalized.bid_ntce_ord is None
    assert normalized.ntce_kind_nm is None
    assert normalized.industry_limited is None
    assert normalized.participation_limited is None
    assert normalized.procurement_category is None


def test_parse_yn_treats_empty_string_as_unknown_not_false():
    # G2B sometimes sends "" rather than omitting a Y/N field entirely - that means "not
    # stated", which must stay None (unknown), not silently become False ("no
    # restriction") for market-stats purposes.
    assert _parse_yn("Y") is True
    assert _parse_yn("N") is False
    assert _parse_yn("") is None
    assert _parse_yn(None) is None


def test_validate_rejects_empty_title():
    collector = G2BCollector(settings=_settings())
    raw = RawRecord(
        source="g2b", external_id="X-000", fetched_at=datetime.now(UTC), payload={"bidNtceNm": "  "}
    )
    normalized = collector.normalize(raw)

    assert collector.validate(normalized) is False


def test_collect_paginates_until_total_count_reached():
    page1 = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "정상"},
            "body": {
                "totalCount": 3,
                "pageNo": 1,
                "numOfRows": 2,
                "items": [
                    {"bidNtceNo": "A1", "bidNtceOrd": "000", "bidNtceNm": "first"},
                    {"bidNtceNo": "A2", "bidNtceOrd": "000", "bidNtceNm": "second"},
                ],
            },
        }
    }
    page2 = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "정상"},
            "body": {
                "totalCount": 3,
                "pageNo": 2,
                "numOfRows": 2,
                "items": [{"bidNtceNo": "A3", "bidNtceOrd": "000", "bidNtceNm": "third"}],
            },
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page_no = httpx.QueryParams(request.url.query.decode())["pageNo"]
        return httpx.Response(200, json=page1 if page_no == "1" else page2)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = G2BCollector(settings=_settings(), client=client, page_size=2)

    records = list(collector.collect())

    assert [r.external_id for r in records] == ["A1-000", "A2-000", "A3-000"]


def test_collect_stops_at_max_records():
    page1 = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "정상"},
            "body": {
                "totalCount": 100,
                "items": [
                    {"bidNtceNo": "A1", "bidNtceOrd": "000", "bidNtceNm": "first"},
                    {"bidNtceNo": "A2", "bidNtceOrd": "000", "bidNtceNm": "second"},
                ],
            },
        }
    }
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=page1)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = G2BCollector(settings=_settings(), client=client, page_size=2, max_records=1)

    records = list(collector.collect())

    assert [r.external_id for r in records] == ["A1-000"]
    assert calls["n"] == 1  # must not keep paginating through all 100 once capped


def test_collect_deduplicates_repeated_external_ids_across_pages():
    duplicate_page = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "정상"},
            "body": {
                "totalCount": 4,
                "items": [{"bidNtceNo": "A1", "bidNtceOrd": "000", "bidNtceNm": "dup"}],
            },
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=duplicate_page)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = G2BCollector(settings=_settings(), client=client, page_size=1)

    records = list(collector.collect())

    # Every page returns the same bidNtceNo/bidNtceOrd (a duplicate response, which
    # section 17 requires collectors to tolerate): only the first occurrence is
    # yielded, and the loop still terminates once `fetched` (raw item count, not
    # unique count) reaches totalCount=4 after 4 page fetches - it must not hang.
    assert [r.external_id for r in records] == ["A1-000"]


def test_collect_raises_collector_error_without_api_key():
    collector = G2BCollector(settings=_settings(api_key=None))

    with pytest.raises(CollectorError, match="G2B_API_KEY"):
        list(collector.collect())


def test_run_isolates_persist_failure(monkeypatch):
    text = (FIXTURES / "bid_list_servc_sample.json").read_text(encoding="utf-8")
    body = parse_response_body(text)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"response": {"header": {"resultCode": "00", "resultMsg": "정상"}, "body": body}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = G2BCollector(settings=_settings(), client=client, page_size=100)

    calls = {"n": 0}

    def fake_persist(self, normalized):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(G2BCollector, "persist", fake_persist)

    result = collector.run()

    assert result.collected == 5
    assert result.persisted == 4
    assert result.failed == 1
