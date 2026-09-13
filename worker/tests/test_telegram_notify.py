import httpx

from worker.config import Settings
from worker.notify import telegram


def test_returns_false_and_warns_when_token_missing(monkeypatch, caplog):
    monkeypatch.setattr(telegram, "get_settings", lambda: Settings(_env_file=None))

    import logging

    with caplog.at_level(logging.WARNING):
        result = telegram.send_telegram_message("123", "hello")

    assert result is False
    assert any("TELEGRAM_BOT_TOKEN not configured" in r.message for r in caplog.records)


def test_sends_successfully_with_expected_payload(monkeypatch):
    monkeypatch.setattr(
        telegram, "get_settings", lambda: Settings(_env_file=None, telegram_bot_token="test-token")
    )

    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(telegram.httpx, "post", fake_post)

    result = telegram.send_telegram_message("123456789", "hello world")

    assert result is True
    assert captured["url"] == "https://api.telegram.org/bottest-token/sendMessage"
    assert captured["json"]["chat_id"] == "123456789"
    assert captured["json"]["text"] == "hello world"


def test_returns_false_and_does_not_raise_on_http_error(monkeypatch, caplog):
    import logging

    monkeypatch.setattr(
        telegram, "get_settings", lambda: Settings(_env_file=None, telegram_bot_token="test-token")
    )

    def fake_post(url, json, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(
            400, json={"ok": False, "description": "chat not found"}, request=request
        )

    monkeypatch.setattr(telegram.httpx, "post", fake_post)

    with caplog.at_level(logging.WARNING):
        result = telegram.send_telegram_message("bad-chat-id", "hello")

    assert result is False
    assert any("send failed" in r.message for r in caplog.records)


def test_bot_token_never_appears_in_logs_on_http_status_error(monkeypatch, caplog):
    # Regression: httpx.HTTPStatusError's default str() embeds the full request URL
    # (https://api.telegram.org/bot<TOKEN>/sendMessage) - logging str(exc) directly
    # would leak the token via worker/logging_config.py's log output.
    import logging

    secret_token = "super-secret-token-do-not-log"
    monkeypatch.setattr(
        telegram, "get_settings", lambda: Settings(_env_file=None, telegram_bot_token=secret_token)
    )

    def fake_post(url, json, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(
            400, json={"ok": False, "description": "chat not found"}, request=request
        )

    monkeypatch.setattr(telegram.httpx, "post", fake_post)

    with caplog.at_level(logging.WARNING):
        result = telegram.send_telegram_message("bad-chat-id", "hello")

    assert result is False
    log_text = "\n".join(r.getMessage() + str(getattr(r, "__dict__", {})) for r in caplog.records)
    assert secret_token not in log_text
