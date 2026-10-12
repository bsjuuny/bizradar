import logging
from datetime import UTC, datetime, timedelta

from worker.collectors.base import CollectorRunResult
from worker.jobs import g2b_job


class FakeCollector:
    def __init__(self, *, run_result: CollectorRunResult, **kwargs) -> None:
        self._run_result = run_result

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def run(self) -> CollectorRunResult:
        return self._run_result


def test_run_logs_success(monkeypatch, caplog):
    result = CollectorRunResult(source="g2b", collected=3, persisted=3, failed=0)
    monkeypatch.setattr(
        g2b_job, "G2BCollector", lambda **kwargs: FakeCollector(run_result=result, **kwargs)
    )

    with caplog.at_level(logging.INFO):
        g2b_job.run()

    assert any("g2b job finished" in r.message for r in caplog.records)


def test_run_does_not_raise_when_collector_fails(monkeypatch, caplog):
    def boom(**kwargs):
        raise RuntimeError("G2B API is down")

    monkeypatch.setattr(g2b_job, "G2BCollector", boom)

    with caplog.at_level(logging.ERROR):
        g2b_job.run()  # must not raise

    assert any("g2b job failed entirely" in r.message for r in caplog.records)


def test_run_warns_on_partial_failures(monkeypatch, caplog):
    result = CollectorRunResult(
        source="g2b", collected=3, persisted=2, failed=1, errors=["X-000: boom"]
    )
    monkeypatch.setattr(
        g2b_job, "G2BCollector", lambda **kwargs: FakeCollector(run_result=result, **kwargs)
    )

    with caplog.at_level(logging.WARNING):
        g2b_job.run()

    assert any("per-record errors" in r.message for r in caplog.records)


def test_run_queries_a_kst_window_and_logs_it(monkeypatch, caplog):
    captured = {}
    result = CollectorRunResult(source="g2b", collected=0, persisted=0, failed=0)

    def make(**kwargs):
        captured.update(kwargs)
        return FakeCollector(run_result=result, **kwargs)

    monkeypatch.setattr(g2b_job, "G2BCollector", make)

    with caplog.at_level(logging.INFO):
        g2b_job.run(lookback=timedelta(hours=2))

    since, until = captured["since"], captured["until"]
    assert since.utcoffset() == timedelta(hours=9)
    assert until - since == timedelta(hours=2)
    assert abs(until - datetime.now(UTC)) < timedelta(minutes=1)

    finished = next(r for r in caplog.records if r.message == "g2b job finished")
    assert finished.window_start == since.isoformat(timespec="minutes")
    assert finished.window_end.endswith("+09:00")


def test_run_failure_logs_the_window_and_error_type(monkeypatch, caplog):
    def boom(**kwargs):
        raise RuntimeError("G2B API is down")

    monkeypatch.setattr(g2b_job, "G2BCollector", boom)

    with caplog.at_level(logging.ERROR):
        g2b_job.run()

    failed = next(r for r in caplog.records if "g2b job failed entirely" in r.message)
    assert failed.error_type == "RuntimeError"
    assert failed.window_start.endswith("+09:00")
    assert failed.window_end.endswith("+09:00")
