from datetime import datetime

from worker.challenges.ai_policy import analyze_ai_policy
from worker.challenges.parsers import (
    SEOUL,
    calculate_status,
    canonicalize_url,
    classify_challenge_type,
    classify_eligibility,
    make_dedupe_key,
    parse_date_range,
    parse_prize,
    parse_team_size,
)


def test_date_parser_handles_full_and_short_end_date():
    start, end = parse_date_range("2026. 7. 22.(수) ~ 8.31.(월)")

    assert start == datetime(2026, 7, 22, tzinfo=SEOUL)
    assert end == datetime(2026, 8, 31, 23, 59, 59, tzinfo=SEOUL)


def test_date_parser_does_not_invent_unknown_deadlines():
    for text in ("상시 모집", "예산 소진 시까지", "선착순", "추후 공지", "미정"):
        assert parse_date_range(text) == (None, None)


def test_date_parser_handles_d_day_relative_to_reference():
    _, end = parse_date_range("D-10", reference=datetime(2026, 8, 7, 9, tzinfo=SEOUL))
    assert end == datetime(2026, 8, 17, 23, 59, 59, tzinfo=SEOUL)


def test_prize_parser_preserves_text_and_normalizes_amount():
    amount, description = parse_prize("총 18팀 / 1,100만원")
    assert amount == 11_000_000
    assert description == "총 18팀 / 1,100만원"
    assert parse_prize("상금 없음") == (0, "상금 없음")
    assert parse_prize("사업화 지원")[0] is None


def test_challenge_type_classifier_uses_specific_types_first():
    assert classify_challenge_type("공공데이터 활용 아이디어 공모전") == ("PUBLIC_DATA_COMPETITION")
    assert classify_challenge_type("2026 AI 해커톤") == "HACKATHON"
    assert classify_challenge_type("AI 서비스 경진대회") == "AI_COMPETITION"


def test_eligibility_classifier_does_not_widen_a_restricted_audience():
    assert classify_eligibility("대전 및 세종지역 대학(원)생 누구나") == "UNIVERSITY"
    assert classify_eligibility("전 국민 누구나") == "ANYONE"


def test_ai_policy_is_unknown_without_explicit_evidence():
    result = analyze_ai_policy("AI 서비스 경진대회", "웹 서비스를 제출합니다.")
    assert result.ai_policy.status == "UNKNOWN"
    assert result.ai_policy.evidence is None


def test_ai_policy_rule_fallback_handles_all_explicit_states():
    cases = {
        "생성형 AI 활용 필수": "REQUIRED",
        "ChatGPT 등 생성형 AI 활용 가능": "ALLOWED",
        "생성형 AI 사용 범위와 도구를 제출 문서에 명시": "LIMITED",
        "생성형 AI 사용 금지": "PROHIBITED",
    }
    for text, expected in cases.items():
        result = analyze_ai_policy("테스트 공모전", text)
        assert result.ai_policy.status == expected
        assert result.ai_policy.evidence == text


def test_url_canonicalizer_removes_tracking_but_preserves_identity_query():
    value = "https://Example.com/path?id=42&utm_source=x&gclid=y#section"
    assert canonicalize_url(value) == "https://example.com/path?id=42"


def test_dedupe_key_collapses_title_punctuation_for_same_canonical_record():
    deadline = datetime(2026, 8, 31, tzinfo=SEOUL)
    first = make_dedupe_key("2026 AI 서비스 공모전", "ABC 기관", deadline)
    second = make_dedupe_key("2026-AI 서비스 공모전!", "ABC기관", deadline)
    assert first == second


def test_team_size_and_status_boundaries():
    assert parse_team_size("개인 또는 팀(최대 4인)") == (1, 4)
    now = datetime(2026, 8, 7, 12, tzinfo=SEOUL)
    assert calculate_status(None, datetime(2026, 8, 10, tzinfo=SEOUL), now=now) == ("CLOSING_SOON")
    assert calculate_status(None, datetime(2026, 8, 6, tzinfo=SEOUL), now=now) == "CLOSED"
    assert calculate_status(None, None, now=now) == "UNKNOWN"
