import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from worker.collectors.base import CollectorError, RawRecord
from worker.collectors.g2b_awards import G2BAwardCollector
from worker.config import Settings

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "g2b"
SEOUL = ZoneInfo("Asia/Seoul")


def _settings(api_key: str | None = "award-key") -> Settings:
    return Settings(_env_file=None, g2b_award_api_key=api_key)


def _sample_item() -> dict:
    payload = json.loads((FIXTURES / "award_list_servc_sample.json").read_text(encoding="utf-8"))
    return payload["response"]["body"]["items"][0]


def test_build_url_uses_separate_key_service_business_code_and_opening_window():
    collector = G2BAwardCollector(
        settings=_settings(),
        since=datetime(2026, 8, 24, 0, 0, tzinfo=UTC),
        until=datetime(2026, 8, 25, 0, 0, tzinfo=UTC),
    )

    url = collector._build_url(2)

    assert "serviceKey=award-key" in url
    assert "bsnsDivCd=5" in url
    assert "opengBgnDt=202608240000" in url
    assert "opengEndDt=202608250000" in url
    assert "pageNo=2" in url


def test_normalize_maps_winner_amount_rate_and_notice_identity():
    collector = G2BAwardCollector(settings=_settings())
    item = _sample_item()
    raw = RawRecord(
        source="g2b_award",
        external_id=collector._external_id(item),
        fetched_at=datetime.now(UTC),
        payload=item,
    )

    result = collector.normalize(raw)

    assert result.external_id == "R26BK01664123-000-0-0"
    assert result.bid_ntce_no == "R26BK01664123"
    assert result.bid_ntce_ord == 0
    assert result.winner_name == "주식회사 비즈레이더"
    assert result.award_amount == 123456789
    assert result.award_rate == 87.995
    assert result.participant_count == 7
    assert result.opened_at == datetime(2026, 8, 24, 11, 0, tzinfo=SEOUL)
    assert result.awarded_at == datetime(2026, 8, 25, tzinfo=SEOUL)
    assert collector.validate(result) is True


def test_collect_paginates_and_deduplicates():
    item = _sample_item()
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {"totalCount": 2, "items": [item]},
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = G2BAwardCollector(settings=_settings(), client=client, page_size=1)

    records = list(collector.collect())

    assert [record.external_id for record in records] == ["R26BK01664123-000-0-0"]
    assert calls["count"] == 2


def test_collect_requires_award_specific_key():
    collector = G2BAwardCollector(settings=_settings(api_key=None))

    with pytest.raises(CollectorError, match="G2B_AWARD_API_KEY"):
        list(collector.collect())


def test_collect_skips_opening_rows_without_a_final_winner():
    incomplete = _sample_item() | {
        "bidNtceNo": "R26-INCOMPLETE",
        "bidwinnrNm": "",
        "fnlSucsfCorpNm": "",
    }
    winner = _sample_item()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {"totalCount": 2, "items": [incomplete, winner]},
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = G2BAwardCollector(settings=_settings(), client=client)

    records = list(collector.collect())

    assert [record.external_id for record in records] == ["R26BK01664123-000-0-0"]


def test_normalize_maps_current_standard_service_field_names():
    collector = G2BAwardCollector(settings=_settings())
    item = {
        "bidNtceNo": "R26-CURRENT",
        "bidNtceOrd": "000",
        "fnlSucsfCorpNm": "현재 낙찰업체",
        "fnlSucsfCorpCeoNm": "대표자",
        "fnlSucsfCorpAdrs": "서울특별시",
        "fnlSucsfAmt": "86363636",
        "fnlSucsfRt": "88.065",
        "presmptPrce": "98066000",
        "opengDate": "2026-08-25",
        "opengTm": "11:00",
        "fnlSucsfDate": "2026-08-25",
    }
    raw = RawRecord(
        source="g2b_award",
        external_id=collector._external_id(item),
        fetched_at=datetime.now(UTC),
        payload=item,
    )

    result = collector.normalize(raw)

    assert result.winner_name == "현재 낙찰업체"
    assert result.winner_representative == "대표자"
    assert result.winner_address == "서울특별시"
    assert result.award_rate == 88.065
    assert result.planned_price == 98_066_000
    assert result.opened_at == datetime(2026, 8, 25, 11, 0, tzinfo=SEOUL)


def test_validate_rejects_result_without_winner():
    collector = G2BAwardCollector(settings=_settings())
    item = {"bidNtceNo": "R26", "bidNtceOrd": "000"}
    normalized = collector.normalize(
        RawRecord(
            source="g2b_award",
            external_id=collector._external_id(item),
            fetched_at=datetime.now(UTC),
            payload=item,
        )
    )

    assert collector.validate(normalized) is False
