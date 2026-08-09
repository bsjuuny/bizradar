import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from worker.collectors.base import CollectorError, RawRecord
from worker.collectors.kstartup import (
    KStartupCollector,
    compute_content_hash,
    parse_response_body,
)
from worker.config import Settings

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "kstartup"


def _settings(api_key: str | None = "test-key") -> Settings:
    return Settings(_env_file=None, kstartup_api_key=api_key)


def test_parse_response_body_success():
    text = (FIXTURES / "announcement_list_sample.json").read_text(encoding="utf-8")
    body = parse_response_body(text)

    assert body["totalCount"] >= 5
    assert len(body["data"]) == 5
    assert body["data"][0]["pbanc_sn"] == 178845


def test_parse_response_body_empty_result():
    text = (FIXTURES / "announcement_list_empty.json").read_text(encoding="utf-8")
    body = parse_response_body(text)

    assert body["data"] == []
    assert body["currentCount"] == 0


def test_parse_response_body_service_error_raises():
    text = (FIXTURES / "announcement_list_service_error.json").read_text(encoding="utf-8")

    with pytest.raises(CollectorError, match="등록되지 않은 서비스키"):
        parse_response_body(text)


def test_parse_response_body_malformed_raises_not_crashes():
    with pytest.raises(CollectorError, match="non-JSON"):
        parse_response_body("<html>not json</html>")


def test_normalize_maps_real_fields_and_flags_investment_linked():
    text = (FIXTURES / "announcement_list_sample.json").read_text(encoding="utf-8")
    item = json.loads(text)["data"][0]  # "2026년 웰컴 투 팁스 1차 참가기업 모집 (충청권)"

    collector = KStartupCollector(settings=_settings())
    raw = RawRecord(
        source="kstartup",
        external_id="178845",
        fetched_at=datetime.now(UTC),
        payload=item,
    )
    normalized = collector.normalize(raw)

    assert normalized.title == "2026년 웰컴 투 팁스 1차 참가기업 모집 (충청권)"
    assert normalized.organization == "(주)로우파트너스"
    assert normalized.department == "프리팁스 투자육성부"
    assert normalized.supervising_type == "민간"
    assert normalized.category == "행사ㆍ네트워크"
    assert normalized.region == "전국"
    assert normalized.recruiting is True
    assert normalized.application_start == datetime(2026, 8, 7)
    assert normalized.application_end == datetime(2026, 8, 18)
    assert normalized.source_url == (
        "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=178845"
    )
    assert normalized.content_hash == compute_content_hash(item)
    # "팁스" in the title - a real TIPS-linked program.
    assert normalized.investment_linked is True


def test_normalize_flags_non_investment_program_correctly():
    text = (FIXTURES / "announcement_list_sample.json").read_text(encoding="utf-8")
    # item[2]: "「민관협력 오픈이노베이션 지원」2026년 '성과기업 후속 지원' 창업기업
    # 모집공고" - a real program with no investment keyword in title or description
    # (item[1], "...팁스타운...", and item[3], "...투자유치...", both DO match, so this
    # one was picked specifically to confirm the filter isn't just matching everything).
    item = json.loads(text)["data"][2]

    collector = KStartupCollector(settings=_settings())
    raw = RawRecord(
        source="kstartup", external_id="178821", fetched_at=datetime.now(UTC), payload=item
    )
    normalized = collector.normalize(raw)

    assert normalized.investment_linked is False


def test_normalize_handles_missing_dates_and_empty_payload():
    collector = KStartupCollector(settings=_settings())
    raw = RawRecord(
        source="kstartup",
        external_id="X",
        fetched_at=datetime.now(UTC),
        payload={"biz_pbanc_nm": "Test"},
    )
    normalized = collector.normalize(raw)

    assert normalized.application_start is None
    assert normalized.application_end is None
    assert normalized.recruiting is None
    assert normalized.investment_linked is False


def test_validate_rejects_empty_title():
    collector = KStartupCollector(settings=_settings())
    raw = RawRecord(
        source="kstartup",
        external_id="X",
        fetched_at=datetime.now(UTC),
        payload={"biz_pbanc_nm": "  "},
    )
    normalized = collector.normalize(raw)

    assert collector.validate(normalized) is False


def test_collect_paginates_until_total_count_reached():
    page1 = {
        "data": [
            {"pbanc_sn": 1, "biz_pbanc_nm": "first"},
            {"pbanc_sn": 2, "biz_pbanc_nm": "second"},
        ],
        "totalCount": 3,
        "page": 1,
        "perPage": 2,
    }
    page2 = {
        "data": [{"pbanc_sn": 3, "biz_pbanc_nm": "third"}],
        "totalCount": 3,
        "page": 2,
        "perPage": 2,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = httpx.QueryParams(request.url.query.decode())["page"]
        return httpx.Response(200, json=page1 if page == "1" else page2)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = KStartupCollector(
        settings=_settings(), client=client, page_size=2, max_records=None
    )

    records = list(collector.collect())

    assert [r.external_id for r in records] == ["1", "2", "3"]


def test_collect_stops_at_max_records():
    page1 = {
        "data": [
            {"pbanc_sn": 1, "biz_pbanc_nm": "first"},
            {"pbanc_sn": 2, "biz_pbanc_nm": "second"},
        ],
        "totalCount": 100,
    }
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=page1)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = KStartupCollector(settings=_settings(), client=client, page_size=2, max_records=1)

    records = list(collector.collect())

    assert [r.external_id for r in records] == ["1"]
    assert calls["n"] == 1  # must not keep paginating through all 100 once capped


def test_collect_deduplicates_repeated_external_ids_across_pages():
    duplicate_page = {
        "data": [{"pbanc_sn": 1, "biz_pbanc_nm": "dup"}],
        "totalCount": 4,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=duplicate_page)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = KStartupCollector(
        settings=_settings(), client=client, page_size=1, max_records=None
    )

    records = list(collector.collect())

    assert [r.external_id for r in records] == ["1"]


def test_collect_raises_collector_error_without_api_key():
    collector = KStartupCollector(settings=_settings(api_key=None))

    with pytest.raises(CollectorError, match="KSTARTUP_API_KEY"):
        list(collector.collect())


def test_run_isolates_persist_failure(monkeypatch):
    text = (FIXTURES / "announcement_list_sample.json").read_text(encoding="utf-8")
    body = parse_response_body(text)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = KStartupCollector(
        settings=_settings(), client=client, page_size=100, max_records=None
    )

    calls = {"n": 0}

    def fake_persist(self, normalized):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(KStartupCollector, "persist", fake_persist)

    result = collector.run()

    assert result.collected == 5
    assert result.persisted == 4
    assert result.failed == 1
