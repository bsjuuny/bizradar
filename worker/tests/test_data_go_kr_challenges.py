from pathlib import Path

import httpx
import pytest

from worker.challenges.resilience import get_text_with_retry
from worker.collectors.base import CollectorError
from worker.collectors.data_go_kr_challenges import (
    DataGoKrChallengeCollector,
    parse_notice_detail,
    parse_notice_list,
)
from worker.config import Settings

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "challenges"


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        data_mode="mock",
        challenge_ai_analysis_enabled=False,
        **overrides,
    )


def test_official_html_fixture_parses_and_normalizes():
    list_html = (FIXTURES / "data_go_kr_list.html").read_text(encoding="utf-8")
    detail_html = (FIXTURES / "data_go_kr_detail.html").read_text(encoding="utf-8")
    notices = parse_notice_list(list_html)
    detail = parse_notice_detail(detail_html, source_url="https://www.data.go.kr/detail?id=1")

    assert notices[0]["external_id"] == "NOTICE_0000000004891"
    assert detail["title"].startswith("[한국조폐공사]")
    assert detail["attachments"][0]["media_type"] == "hwp"


def test_integration_source_to_normalize_to_persist(monkeypatch):
    captured = []
    monkeypatch.setattr(
        DataGoKrChallengeCollector,
        "persist",
        lambda self, item: captured.append(item),
    )
    collector = DataGoKrChallengeCollector(settings=_settings())

    result = collector.run()

    assert result.collected == result.persisted == 1
    challenge = captured[0]
    assert challenge.challenge_type == "PUBLIC_DATA_COMPETITION"
    assert challenge.team_max == 4
    assert challenge.total_prize_amount == 11_000_000
    assert challenge.ai_policy.status == "LIMITED"
    assert challenge.analysis_status == "RULE_ONLY"


def test_parser_rejects_invalid_html_without_crashing_process():
    with pytest.raises(CollectorError, match="missing title or body"):
        parse_notice_detail("<html><p>changed layout</p></html>", source_url="https://example.com")


def test_http_429_respects_retry_after_then_succeeds():
    calls = {"count": 0}
    delays = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, request=request)
        return httpx.Response(
            200,
            text="<html>ok</html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    text = get_text_with_retry(
        client,
        "https://example.test",
        params=None,
        source="test",
        max_retries=2,
        sleep=delays.append,
    )

    assert text == "<html>ok</html>"
    assert calls["count"] == 2
    assert delays == [0.0]


def test_http_503_and_timeout_are_bounded():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(CollectorError, match="after 3 attempts"):
        get_text_with_retry(
            client,
            "https://example.test",
            params=None,
            source="test",
            max_retries=2,
            sleep=lambda _: None,
        )
    assert calls["count"] == 3

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(CollectorError, match="after 2 attempts"):
        get_text_with_retry(
            httpx.Client(transport=httpx.MockTransport(timeout)),
            "https://example.test",
            params=None,
            source="test",
            max_retries=1,
            sleep=lambda _: None,
        )


def test_http_403_is_not_retried():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(403, request=request)

    with pytest.raises(CollectorError, match="retry disabled"):
        get_text_with_retry(
            httpx.Client(transport=httpx.MockTransport(handler)),
            "https://example.test",
            params=None,
            source="test",
            max_retries=3,
            sleep=lambda _: None,
        )
    assert calls["count"] == 1
