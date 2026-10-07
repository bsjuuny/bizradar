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
    saved = (root.level, list(root.handlers))
    try:
        configure_logging()
        assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
        assert not logging.getLogger("httpcore").isEnabledFor(logging.INFO)
        assert logging.getLogger("httpx").isEnabledFor(logging.WARNING)
    finally:
        root.setLevel(saved[0])
        root.handlers = saved[1]
        logging.getLogger("httpx").setLevel(logging.NOTSET)
        logging.getLogger("httpcore").setLevel(logging.NOTSET)
