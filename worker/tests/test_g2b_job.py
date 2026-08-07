import logging

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
