"""BizInfoCollector, offline.

Both fixtures are real responses recorded 2026-10-07:
- `api_response_sample.json`: 5 of the 1,443 items a keyed call returned, values
  untouched except that the contact fields the collector never reads (refrncNm,
  reqstMthPapersCn, rceptEngnHmpgUrl - phone numbers, e-mail addresses) were removed.
  `totCnt` is still the full response's 1,443, so this trimmed sample is (correctly) an
  incomplete list.
- `api_response_missing_key.json`: the answer to a call without crtfcKey.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from worker.collectors.base import CollectorError, RawRecord
from worker.collectors.bizinfo import (
    BizInfoCollector,
    StoredRow,
    extract_items,
    html_to_text,
    parse_period,
    title_tag_region,
)
from worker.config import Settings

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "bizinfo"
TODAY = date(2026, 10, 7)
KEY = "test-bizinfo-key-0123"


def _settings(api_key: str | None = KEY) -> Settings:
    return Settings(_env_file=None, bizinfo_api_key=api_key)


def _fixture_text() -> str:
    return (FIXTURES / "api_response_sample.json").read_text(encoding="utf-8")


def _raw(item: dict) -> RawRecord:
    return RawRecord(
        source="bizinfo",
        external_id=item.get("pblancId") or item.get("seq") or "X",
        fetched_at=datetime.now(UTC),
        payload=item,
    )


def _collector(handler=None, api_key: str | None = KEY, stored=None) -> BizInfoCollector:
    client = httpx.Client(transport=httpx.MockTransport(handler)) if handler else None
    return BizInfoCollector(
        settings=_settings(api_key),
        client=client,
        today=TODAY,
        sleep=lambda seconds: None,
        stored=stored,
    )


def test_extract_items_live_shape_list():
    # The shape a keyed call actually returns: jsonArray is the item list itself.
    items = extract_items(_fixture_text())

    assert len(items) == 5
    assert items[0]["pblancId"] == "PBLN_000000000127023"
    assert items[0]["totCnt"] == 1443  # a number, not the string the spec table shows


def test_extract_items_official_spec_shape_object_with_item_list():
    # https://www.bizinfo.go.kr/apiDetail.do?id=bizinfoApi JSON example:
    # {"jsonArray": {"title": ..., "item": [...]}}
    body = {"jsonArray": {"title": "기업마당 지원사업정보", "item": [{"pblancId": "A"}]}}

    assert extract_items(json.dumps(body)) == [{"pblancId": "A"}]


def test_extract_items_single_item_object():
    body = {"jsonArray": {"item": {"pblancId": "A"}}}

    assert extract_items(json.dumps(body)) == [{"pblancId": "A"}]


def test_extract_items_missing_key_error_raises():
    text = (FIXTURES / "api_response_missing_key.json").read_text(encoding="utf-8")

    with pytest.raises(CollectorError, match="인증키를 입력해주세요"):
        extract_items(text)


def test_extract_items_non_json_raises_not_crashes():
    with pytest.raises(CollectorError, match="non-JSON"):
        extract_items("<html>error</html>")


def test_extract_items_unknown_schema_raises():
    with pytest.raises(CollectorError, match="unexpected schema"):
        extract_items('{"result": []}')


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-02 ~ 2026-10-16", (date(2026, 10, 2), date(2026, 10, 16))),
        ("20220727 ~ 20220930", (date(2022, 7, 27), date(2022, 9, 30))),  # spec example
        ("2020.01.01 ~ 2026.12.31", (date(2020, 1, 1), date(2026, 12, 31))),  # seen live
        (" 2026-10-02~2026-10-02 ", (date(2026, 10, 2), date(2026, 10, 2))),
        ("예산 소진시까지", None),
        ("상시 접수", None),
        ("세부사업별 상이", None),
        ("", None),
        ("2026-02-30 ~ 2026-03-10", None),  # not a real date
        ("2026-10-31 ~ 2026-09-01", None),  # end before start
        # Times, weekdays, single-digit parts, an end date without its year.
        ("2026-10-01 10:00 ~ 2026-10-10 18:00", (date(2026, 10, 1), date(2026, 10, 10))),
        ("2026.10.1 ~ 2026.10.10", (date(2026, 10, 1), date(2026, 10, 10))),
        (
            "2026. 10. 2.(목) 09:00 ~ 10. 16.(목) 18:00 까지",
            (date(2026, 10, 2), date(2026, 10, 16)),
        ),
        ("2026/10/01 ~ 2026/10/31", (date(2026, 10, 1), date(2026, 10, 31))),
        ("2026-10-01 ~", None),  # open end: no deadline to read
        # An end without a year that falls before the start is in the next year.
        ("2025. 12. 15. ~ 1. 15.", (date(2025, 12, 15), date(2026, 1, 15))),
        # ...including Feb 29 of a leap next year (not a ValueError on the start's year).
        ("2027. 12. 1. ~ 2. 29.", (date(2027, 12, 1), date(2028, 2, 29))),
        # But not a typo: as a date this would be a 347-day window, D-360 and open for a
        # year. It stays text.
        ("2026. 10. 20. ~ 10. 2.", None),
        ("2026. 3. 1. ~ 2. 28.", None),
        # Variants not in the stored data but cheap to accept: a full-width tilde, an hour
        # written "18시", a trailing remark.
        ("2026-10-01 ～ 2026-10-31", (date(2026, 10, 1), date(2026, 10, 31))),
        ("2026-10-01(수) ~ 2026-10-31(금) 18시", (date(2026, 10, 1), date(2026, 10, 31))),
        (
            "2026-10-01 ~ 2026-10-31 (예산 소진 시 조기마감)",
            (date(2026, 10, 1), date(2026, 10, 31)),
        ),
        # Still never a second range or free text after the end.
        ("2026-10-01 ~ 2026-10-31, 2026-11-01 ~ 2026-11-30", None),
        ("2026-10-01 ~ 2026-10-31 중 별도 공지", None),
    ],
)
def test_parse_period_reads_only_real_date_ranges(raw, expected):
    assert parse_period(raw) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("[경기] 2026년 10월 동행축제 ...", "경기"),
        ("[전남광주] 목포시 ...", "전남광주"),
        ("[서울ㆍ인천ㆍ경기] 2026년 미래내일 일경험 ...", "서울·인천·경기"),
        ("[대전ㆍ충청] ...", "대전·충청"),
        ("2026년 수출지원사업 통합 공고", None),
        # K-Startup-style organization tag - not a region.
        ("[한국도로공사] 2026년 상생형 창업, 벤처기업 지원사업", None),
        ("[서울ㆍ한국도로공사] ...", None),
        # Regions separated by a space only.
        ("[대구 경북] 2026년 ...", "대구·경북"),
        ("[서울 강남구] ...", None),  # 강남구 isn't in the vocabulary
    ],
)
def test_parse_region_only_from_known_region_tags(title, expected):
    assert title_tag_region(title) == expected


def test_html_to_text_keeps_line_breaks_and_drops_tags():
    raw = (
        "<div>첫 줄&nbsp;입니다.</div><p>둘째 <b>줄</b></p><br/>  <ul><li>항목 &amp; 내용</li></ul>"
    )

    assert html_to_text(raw) == "첫 줄 입니다.\n둘째 줄\n항목 & 내용"


def test_normalize_dated_announcement():
    item = extract_items(_fixture_text())[0]

    normalized = _collector().normalize(_raw(item))

    assert (
        normalized.title == "[경기] 2026년 10월 동행축제 소상공인 라이브커머스 참가기업 모집 공고"
    )
    assert normalized.organization == "경기지방중소벤처기업청"
    assert normalized.department == "중소벤처기업부"
    assert normalized.category == "내수"
    assert normalized.region == "경기"
    assert normalized.application_start == datetime(2026, 10, 2, tzinfo=UTC)
    assert normalized.application_end == datetime(2026, 10, 16, tzinfo=UTC)
    assert normalized.application_period_text == "2026-10-02 ~ 2026-10-16"
    assert normalized.target == "소상공인"
    assert normalized.recruiting is True
    assert normalized.source_url == (
        "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127023"
    )
    # bsnsSumryCn is <p>-wrapped HTML with &nbsp; - read as plain lines.
    assert normalized.description is not None
    assert normalized.description.startswith(
        "2026년 10월 동행축제 기간 내 소상공인의 판매촉진 및 홍보를 위하여"
    )
    assert "☞ 경기지역 소상공인\n- 사업자등록증 소재지 경기지역" in normalized.description
    assert "<" not in normalized.description


def test_normalize_budget_bound_period_keeps_text_and_stays_recruiting():
    item = extract_items(_fixture_text())[1]  # "예산 소진시까지", 수행기관 "기초자치단체"

    normalized = _collector().normalize(_raw(item))

    assert normalized.application_start is None
    assert normalized.application_end is None
    assert normalized.application_period_text == "예산 소진시까지"
    # Posted on 기업마당 right now -> open; no date to say otherwise.
    assert normalized.recruiting is True
    # "기초자치단체" is a placeholder, not an organization name.
    assert normalized.organization == "울산광역시"
    assert normalized.region == "울산"


def test_normalize_relative_url_is_made_absolute():
    # Live responses carry absolute URLs; the spec doesn't promise it.
    item = {
        "pblancId": "A",
        "pblancNm": "x",
        "pblancUrl": "/sii/siia/selectSIIA200Detail.do?pblancId=A",
    }

    assert _collector().normalize(_raw(item)).source_url == (
        "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=A"
    )


def test_normalize_direct_execution_uses_jurisdiction_and_no_region():
    item = extract_items(_fixture_text())[3]  # 수행기관 "직접수행", no [지역] tag

    normalized = _collector().normalize(_raw(item))

    assert normalized.organization == "산업통상부"
    assert normalized.region is None


def test_normalize_flags_investment_linked():
    items = extract_items(_fixture_text())

    flags = [_collector().normalize(_raw(item)).investment_linked for item in items]

    # Only "[경기] 부천시 2026년 스타트업포럼(IR데모데이) ..." mentions 데모데이.
    assert flags == [False, False, False, False, True]


def test_normalize_flags_it_related():
    items = extract_items(_fixture_text())

    flags = [_collector().normalize(_raw(item)).it_related for item in items]

    # None of the five recorded postings is about IT (동행축제 라이브커머스, 석유화학업
    # 버팀이음, 일경험 인턴형, 혁신제품 지정기간 연장, 부천 스타트업포럼).
    assert flags == [False, False, False, False, False]
    item = {"pblancId": "A", "pblancNm": "[경북] 정보보호 스타트업 육성사업 참여기업 모집 공고"}
    assert _collector().normalize(_raw(item)).it_related is True


def test_normalize_past_deadline_is_not_recruiting():
    item = {"pblancId": "A", "pblancNm": "지난 공고", "reqstBeginEndDe": "2026-09-01 ~ 2026-10-06"}

    assert _collector().normalize(_raw(item)).recruiting is False


def test_normalize_spec_rss_aliases_and_html_summary():
    # Field names from the RSS half of the official spec, used only as fallbacks.
    item = {
        "seq": "PBLN_000000000080236",
        "title": "착한임대인 장관 표창 신청 연장 공고",
        "link": "http://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId=PBLN_000000000080236",
        "author": "중소벤처기업부",
        "excInsttNm": "지방중소벤처기업청",
        "description": "<div>임대료를 인하한 임대인을 선정하는 사업입니다.</div>",
        "lcategory": "경영",
        "reqstDt": "20260901 ~ 20261031",
        "trgetNm": "중소기업",
    }

    normalized = _collector().normalize(_raw(item))

    assert normalized.title == "착한임대인 장관 표창 신청 연장 공고"
    assert normalized.organization == "지방중소벤처기업청"
    assert normalized.department == "중소벤처기업부"
    assert normalized.category == "경영"
    assert normalized.target == "중소기업"
    assert normalized.description == "임대료를 인하한 임대인을 선정하는 사업입니다."
    assert normalized.application_end == datetime(2026, 10, 31, tzinfo=UTC)
    # http on the BizInfo host is upgraded.
    assert normalized.source_url.startswith("https://www.bizinfo.go.kr/")


def test_normalize_missing_url_falls_back_to_detail_page():
    normalized = _collector().normalize(_raw({"pblancId": "PBLN_1", "pblancNm": "x"}))

    assert normalized.source_url == (
        "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_1"
    )


def test_validate_rejects_empty_title():
    collector = _collector()

    assert (
        collector.validate(collector.normalize(_raw({"pblancId": "A", "pblancNm": " "}))) is False
    )


def test_collect_sends_key_and_reports_complete_list():
    seen = {}
    body = {
        "jsonArray": [
            {"pblancId": "A", "pblancNm": "a", "totCnt": 2},
            {"pblancId": "B", "pblancNm": "b", "totCnt": 2},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=body)

    collector = _collector(handler)

    records = list(collector.collect())

    assert seen["params"] == {"crtfcKey": KEY, "dataType": "json", "searchCnt": "5000"}
    assert collector.listed_ids == {"A", "B"} == {r.external_id for r in records}
    assert collector.complete is True


def test_collect_trimmed_recorded_sample_is_not_complete():
    # 5 items whose totCnt still says 1,443 - exactly what a truncated response looks like.
    collector = _collector(lambda request: httpx.Response(200, text=_fixture_text()))

    assert len(list(collector.collect())) == 5
    assert collector.complete is False


def test_collect_truncated_response_is_not_complete():
    body = {"jsonArray": [{"pblancId": "A", "pblancNm": "a", "totCnt": 1500}]}
    collector = _collector(lambda request: httpx.Response(200, json=body))

    records = list(collector.collect())

    assert [r.external_id for r in records] == ["A"]
    assert collector.complete is False


def test_collect_empty_list_is_not_complete():
    collector = _collector(lambda request: httpx.Response(200, json={"jsonArray": []}))

    assert list(collector.collect()) == []
    assert collector.complete is False


def test_collect_deduplicates_repeated_ids_in_one_response():
    body = {"jsonArray": [{"pblancId": "A", "pblancNm": "a"}, {"pblancId": "A", "pblancNm": "a"}]}
    collector = _collector(lambda request: httpx.Response(200, json=body))

    assert [r.external_id for r in collector.collect()] == ["A"]


def test_collect_without_api_key_raises():
    collector = _collector(api_key=None)

    with pytest.raises(CollectorError, match="BIZINFO_API_KEY"):
        list(collector.collect())


def test_collect_retries_server_errors_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, text=_fixture_text())

    collector = _collector(handler)

    assert len(list(collector.collect())) == 5
    assert calls["n"] == 2


def test_collect_does_not_retry_refusals():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429)

    collector = _collector(handler)

    with pytest.raises(CollectorError, match="429"):
        list(collector.collect())
    assert calls["n"] == 1


def test_transport_error_message_never_contains_the_key():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed to connect: {request.url}")

    collector = _collector(handler)

    with pytest.raises(CollectorError) as excinfo:
        list(collector.collect())
    assert KEY not in str(excinfo.value)
    assert "***" in str(excinfo.value)


def test_run_persists_every_record_through_repository(monkeypatch):
    # No stored state given (None: unknown) -> every row is written.
    persisted = []
    monkeypatch.setattr(
        "worker.repositories.support_programs.upsert_bizinfo_programs", persisted.extend
    )
    collector = _collector(lambda request: httpx.Response(200, text=_fixture_text()))

    result = collector.run()

    assert result.collected == 5
    assert result.persisted == 5
    assert result.failed == 0
    assert [p.external_id for p in persisted][0] == "PBLN_000000000127023"
    assert collector.unchanged == 0


def test_unchanged_rows_are_not_resent(monkeypatch):
    items = extract_items(_fixture_text())
    first = _collector().normalize(_raw(items[0]))
    second = _collector().normalize(_raw(items[1]))
    stored = {
        first.external_id: StoredRow("row-1", first.content_hash, True),  # unchanged
        # Closed (delisted earlier) and listed again: reopened, so written.
        second.external_id: StoredRow("row-2", second.content_hash, False),
        "PBLN_000000000127013": StoredRow("row-3", "an-older-hash", True),  # content changed
    }
    persisted = []
    monkeypatch.setattr(
        "worker.repositories.support_programs.upsert_bizinfo_programs", persisted.extend
    )
    collector = _collector(lambda request: httpx.Response(200, text=_fixture_text()), stored=stored)

    result = collector.run()

    assert result.persisted == 5 and result.failed == 0
    assert collector.unchanged == 1
    assert first.external_id not in [p.external_id for p in persisted]
    assert len(persisted) == 4


def test_listed_row_past_its_deadline_is_closed_once_then_skipped(monkeypatch):
    item = dict(extract_items(_fixture_text())[0])
    item["reqstBeginEndDe"] = "20260901 ~ 20260930"
    normalized = _collector().normalize(_raw(item))
    assert normalized.recruiting is False
    persisted = []
    monkeypatch.setattr(
        "worker.repositories.support_programs.upsert_bizinfo_programs", persisted.extend
    )

    def run_with(recruiting: bool) -> None:
        collector = _collector(
            lambda request: httpx.Response(200, text=json.dumps({"jsonArray": [item]})),
            stored={
                normalized.external_id: StoredRow("row-1", normalized.content_hash, recruiting)
            },
        )
        collector.run()

    # Stored as recruiting with the same content: the skip must not keep it open.
    run_with(recruiting=True)
    assert [p.recruiting for p in persisted] == [False]
    # Stored closed, still listed: nothing to write (fetch_bizinfo_state includes
    # recently seen rows so this case is recognized).
    run_with(recruiting=False)
    assert len(persisted) == 1


def test_changed_rows_are_written_in_chunks(monkeypatch):
    requests = []
    monkeypatch.setattr(
        "worker.repositories.support_programs.upsert_bizinfo_programs",
        lambda programs: requests.append([p.external_id for p in programs]),
    )
    monkeypatch.setattr("worker.collectors.bizinfo.UPSERT_CHUNK_SIZE", 2)
    collector = _collector(lambda request: httpx.Response(200, text=_fixture_text()))

    result = collector.run()

    assert [len(chunk) for chunk in requests] == [2, 2, 1]
    assert result.persisted == 5 and result.failed == 0
    assert collector.written == {external_id for chunk in requests for external_id in chunk}


def test_a_failing_chunk_is_retried_row_by_row(monkeypatch):
    items = extract_items(_fixture_text())
    bad = _collector().normalize(_raw(items[1])).external_id
    written = []

    def upsert(programs):
        if any(p.external_id == bad for p in programs):
            raise RuntimeError("row rejected")
        written.extend(p.external_id for p in programs)

    monkeypatch.setattr("worker.repositories.support_programs.upsert_bizinfo_programs", upsert)
    collector = _collector(lambda request: httpx.Response(200, text=_fixture_text()))

    result = collector.run()

    assert len(written) == 4 and bad not in written
    assert result.persisted == 4 and result.failed == 1
    assert result.errors[0].startswith(bad)
    assert bad not in collector.written  # so the job still refreshes it as seen


def test_source_url_must_be_an_http_url_on_bizinfo():
    for raw in ("javascript:alert(1)", "https://evil.example/view.do?pblancId=A"):
        item = {"pblancId": "A", "pblancNm": "x", "pblancUrl": raw}
        assert _collector().normalize(_raw(item)).source_url == (
            "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=A"
        )


def test_missing_total_count_is_not_complete():
    # The spec's fallback shape carries no totCnt; without it nothing proves the list is
    # whole, so the job must not close "unlisted" announcements.
    body = {"jsonArray": {"item": [{"pblancId": "A", "pblancNm": "a"}]}}
    collector = _collector(lambda request: httpx.Response(200, json=body))

    assert len(list(collector.collect())) == 1
    assert collector.complete is False


def test_total_count_with_thousands_separator_is_read():
    body = {"jsonArray": [{"pblancId": "A", "pblancNm": "a", "totCnt": "1,443"}]}
    collector = _collector(lambda request: httpx.Response(200, json=body))

    list(collector.collect())
    assert collector.complete is False  # 1 of 1,443 - read as a number, not ignored


def test_repeated_ids_do_not_count_toward_completeness():
    # totCnt == number of entries, but one entry repeats an id: a real announcement is
    # missing, so this is not the complete list.
    body = {
        "jsonArray": [
            {"pblancId": "A", "pblancNm": "a", "totCnt": 2},
            {"pblancId": "A", "pblancNm": "a", "totCnt": 2},
        ]
    }
    collector = _collector(lambda request: httpx.Response(200, json=body))

    assert [r.external_id for r in collector.collect()] == ["A"]
    assert collector.complete is False


def test_collector_reuse_starts_each_collect_fresh():
    body = {"jsonArray": [{"pblancId": "A", "pblancNm": "a", "totCnt": 1}]}
    collector = _collector(lambda request: httpx.Response(200, json=body))

    assert len(list(collector.collect())) == 1
    assert len(list(collector.collect())) == 1  # not skipped as "already seen"
    assert collector.listed_ids == {"A"}
    assert collector.complete is True


def test_source_url_query_string_is_not_entity_decoded():
    # html.unescape would turn "&notice=1" into "¬ice=1" (legacy entity without ";").
    item = {
        "pblancId": "A",
        "pblancNm": "x",
        "pblancUrl": "https://www.bizinfo.go.kr/view.do?pblancId=A&notice=1&regionCd=11",
    }

    assert _collector().normalize(_raw(item)).source_url == (
        "https://www.bizinfo.go.kr/view.do?pblancId=A&notice=1&regionCd=11"
    )


def test_text_fields_decode_only_terminated_entities():
    item = {"pblancId": "A", "pblancNm": "R&D &amp; &apos;AI&apos; &copy2026", "excInsttNm": "x"}

    assert _collector().normalize(_raw(item)).title == "R&D & 'AI' &copy2026"


def test_url_encoded_key_is_masked_too():
    key = "ab+cd/ef=="

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed to connect: {request.url}")

    collector = BizInfoCollector(
        settings=_settings(key),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        today=TODAY,
        sleep=lambda seconds: None,
    )

    with pytest.raises(CollectorError) as excinfo:
        list(collector.collect())
    message = str(excinfo.value)
    assert "ab+cd" not in message and "ab%2Bcd" not in message
    assert "***" in message


def test_retries_back_off_between_attempts():
    waits = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    collector = BizInfoCollector(
        settings=_settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        today=TODAY,
        sleep=waits.append,
    )

    with pytest.raises(CollectorError, match="after 3 attempts"):
        list(collector.collect())
    assert waits == [2.0, 5.0]  # none before the first attempt


def test_content_hash_ignores_view_count_and_list_total():
    item = extract_items(_fixture_text())[0]
    viewed_again = {**item, "inqireCo": item["inqireCo"] + 10, "totCnt": 1500}

    first = _collector().normalize(_raw(item)).content_hash
    second = _collector().normalize(_raw(viewed_again)).content_hash

    assert first == second
    edited = {**item, "pblancNm": item["pblancNm"] + " (수정)"}
    assert _collector().normalize(_raw(edited)).content_hash != first


def test_unknown_semicolon_names_are_left_alone():
    # html.unescape("&notice;") would give "¬ice;" (legacy "&not" prefix).
    item = {"pblancId": "A", "pblancNm": "a &notice; b &copyright; c &amp; d"}

    assert _collector().normalize(_raw(item)).title == "a &notice; b &copyright; c & d"


def test_normalize_change_changes_the_hash_even_with_the_same_payload(monkeypatch):
    item = extract_items(_fixture_text())[0]
    before = _collector().normalize(_raw(item)).content_hash

    # Simulate a rule change in a derived column (here: IT classification).
    monkeypatch.setattr("worker.collectors.bizinfo.is_it_related", lambda title: True)
    after = _collector().normalize(_raw(item)).content_hash

    assert before != after


def test_html_to_text_separates_table_cells_and_br_with_attributes():
    assert html_to_text("<td>지원대상</td><td>중소기업</td>") == "지원대상 중소기업"
    assert html_to_text("a<br class='x'>b") == "a\nb"
    assert html_to_text("<b>지원</b>대상") == "지원대상"


def test_systemic_write_failure_stops_retrying(monkeypatch):
    calls = []

    def upsert(programs):
        calls.append(len(programs))
        raise RuntimeError("relation support_programs has no column last_seen_at")

    monkeypatch.setattr("worker.repositories.support_programs.upsert_bizinfo_programs", upsert)
    monkeypatch.setattr("worker.collectors.bizinfo.UPSERT_CHUNK_SIZE", 2)
    monkeypatch.setattr("worker.collectors.bizinfo.SYSTEMIC_FAILURE_ROWS", 2)
    collector = _collector(lambda request: httpx.Response(200, text=_fixture_text()))

    result = collector.run()

    # One chunk, two single-row retries, then nothing more - not one request per row.
    assert calls == [2, 1, 1]
    assert result.failed == 5 and result.persisted == 0
    assert "not attempted" in result.errors[-1]


def test_bare_less_than_sign_is_text_not_a_tag():
    assert html_to_text("<p>매출 <10억 기업</p><p>지원 > 5건</p>") == "매출 <10억 기업\n지원 > 5건"
    assert html_to_text("<p>A <B and C</p><p>D</p>") == "A <B and C\nD"
    assert html_to_text("<붙임> 신청서") == "<붙임> 신청서"


def test_time_with_seconds_is_read():
    assert parse_period("2026-10-01 09:00:00 ~ 2026-10-31 18:00:00") == (
        date(2026, 10, 1),
        date(2026, 10, 31),
    )


def test_source_url_with_userinfo_or_port_falls_back_to_the_detail_page():
    # The web's safeExternalUrl drops these, which would leave no "원문 보기" link at all.
    for raw in (
        "https://user@www.bizinfo.go.kr/sii/view.do?pblancId=A",
        "https://www.bizinfo.go.kr:8443/sii/view.do?pblancId=A",
    ):
        item = {"pblancId": "A", "pblancNm": "x", "pblancUrl": raw}
        assert _collector().normalize(_raw(item)).source_url == (
            "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=A"
        )
