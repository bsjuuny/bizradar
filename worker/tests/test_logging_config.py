import json
import logging
import sys

from worker.logging_config import JsonFormatter


def _make_record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_includes_standard_fields():
    payload = json.loads(JsonFormatter().format(_make_record()))

    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    assert "timestamp" in payload


def test_includes_arbitrary_extra_fields():
    payload = json.loads(JsonFormatter().format(_make_record(job="g2b-collect", collected=5)))

    assert payload["job"] == "g2b-collect"
    assert payload["collected"] == 5


def test_includes_exception_info():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    payload = json.loads(JsonFormatter().format(record))

    assert "boom" in payload["error"]


def test_httpx_request_lines_are_not_logged_at_info():
    # httpx logs "HTTP Request: GET <url>" at INFO, and API keys travel in those URLs.
    from worker.logging_config import configure_logging

    root = logging.getLogger()
    saved_root = (root.level, list(root.handlers))
    saved_levels = {name: logging.getLogger(name).level for name in ("httpx", "httpcore")}
    try:
        configure_logging()
        assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
        assert not logging.getLogger("httpcore").isEnabledFor(logging.INFO)
        assert logging.getLogger("httpx").isEnabledFor(logging.WARNING)
    finally:
        root.setLevel(saved_root[0])
        root.handlers = saved_root[1]
        for name, level in saved_levels.items():
            logging.getLogger(name).setLevel(level)


def test_api_keys_in_query_strings_are_redacted_everywhere_on_the_line():
    # The shape httpx.HTTPStatusError produces - as message, as an extra, and in a traceback.
    url = "https://apis.data.go.kr/x?serviceKey=AbC%2B123%3D%3D&page=1&crtfcKey=zzz9"
    try:
        raise RuntimeError(f"Server error '500' for url '{url}'")
    except RuntimeError:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg=f"K-Startup API HTTP error: {url}",
            args=(),
            exc_info=sys.exc_info(),
        )
    record.error_detail = url

    line = JsonFormatter().format(record)

    assert "AbC" not in line and "zzz9" not in line
    assert "serviceKey=<redacted>&page=1" in line
    assert "crtfcKey=<redacted>" in line
