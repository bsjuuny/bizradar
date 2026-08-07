import logging
from typing import Any

import pytest

from worker.ai.base import AIProviderError
from worker.ai.schemas import ProjectExtraction
from worker.jobs import analyze_job

OPP_A: dict[str, Any] = {
    "id": "aaaaaaaa-0000-0000-0000-000000000001",
    "title": "AI 챗봇 구축 용역",
    "organization": "테스트기관",
    "demand_organization": None,
    "budget_amount": 50_000_000,
    "content_hash": "hash-a",
}
OPP_B: dict[str, Any] = {
    "id": "bbbbbbbb-0000-0000-0000-000000000002",
    "title": "정보시스템 유지보수 용역",
    "organization": "테스트기관2",
    "demand_organization": None,
    "budget_amount": None,
    "content_hash": "hash-b",
}


class FakeProvider:
    def __init__(self, *, results: dict[str, ProjectExtraction | Exception]):
        self._results = results
        self.settings = type("S", (), {"ollama_model": "qwen3:8b"})()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def get_model_digest(self):
        return "abc123def456"

    async def extract_project(self, text: str) -> ProjectExtraction:
        for opp in (OPP_A, OPP_B):
            if opp["title"] in text:
                result = self._results[opp["id"]]
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"unexpected prompt text: {text}")


def _extraction(project_type: str = "AI_ML") -> ProjectExtraction:
    return ProjectExtraction(project_type=project_type, summary="요약")


def test_build_prompt_text_includes_available_fields():
    text = analyze_job._build_prompt_text(OPP_A)
    assert "공고명: AI 챗봇 구축 용역" in text
    assert "발주기관: 테스트기관" in text
    assert "배정예산: 50,000,000원" in text
    assert "수요기관" not in text  # None fields are omitted, not shown as "수요기관: None"


def test_run_no_pending_opportunities_logs_zero_and_does_not_error(monkeypatch, caplog):
    monkeypatch.setattr(analyze_job, "get_pending_opportunities", lambda category, limit: [])
    monkeypatch.setattr(analyze_job, "upsert_success", lambda *a, **kw: pytest.fail("unexpected"))
    monkeypatch.setattr(analyze_job, "upsert_failure", lambda *a, **kw: pytest.fail("unexpected"))

    with caplog.at_level(logging.INFO):
        analyze_job.run()

    finished = [r for r in caplog.records if "analyze job finished" in r.message]
    assert len(finished) == 1
    assert finished[0].succeeded == 0
    assert finished[0].failed == 0


def test_run_persists_success_for_each_opportunity(monkeypatch, caplog):
    monkeypatch.setattr(
        analyze_job, "get_pending_opportunities", lambda category, limit: [OPP_A, OPP_B]
    )
    monkeypatch.setattr(
        analyze_job,
        "OllamaProvider",
        lambda: FakeProvider(results={OPP_A["id"]: _extraction(), OPP_B["id"]: _extraction()}),
    )
    successes = []
    monkeypatch.setattr(
        analyze_job,
        "upsert_success",
        lambda opp_id, content_hash, extraction, **kw: successes.append(opp_id),
    )
    monkeypatch.setattr(analyze_job, "upsert_failure", lambda *a, **kw: pytest.fail("unexpected"))

    with caplog.at_level(logging.INFO):
        analyze_job.run()

    assert successes == [OPP_A["id"], OPP_B["id"]]
    assert any("analyze job finished" in r.message for r in caplog.records)


def test_run_isolates_per_item_failure(monkeypatch, caplog):
    monkeypatch.setattr(
        analyze_job, "get_pending_opportunities", lambda category, limit: [OPP_A, OPP_B]
    )
    monkeypatch.setattr(
        analyze_job,
        "OllamaProvider",
        lambda: FakeProvider(
            results={
                OPP_A["id"]: AIProviderError("validation failed twice"),
                OPP_B["id"]: _extraction(),
            }
        ),
    )
    successes, failures = [], []
    monkeypatch.setattr(
        analyze_job,
        "upsert_success",
        lambda opp_id, content_hash, extraction, **kw: successes.append(opp_id),
    )
    monkeypatch.setattr(
        analyze_job, "upsert_failure", lambda opp_id, content_hash, error: failures.append(opp_id)
    )

    with caplog.at_level(logging.WARNING):
        analyze_job.run()

    assert successes == [OPP_B["id"]]
    assert failures == [OPP_A["id"]]
    assert any(
        "per-item errors" in r.message or "extraction failed" in r.message for r in caplog.records
    )


def test_run_does_not_raise_when_provider_setup_fails(monkeypatch, caplog):
    monkeypatch.setattr(analyze_job, "get_pending_opportunities", lambda category, limit: [OPP_A])

    def boom():
        raise RuntimeError("Ollama is not reachable")

    monkeypatch.setattr(analyze_job, "OllamaProvider", boom)

    with caplog.at_level(logging.ERROR):
        analyze_job.run()  # must not raise

    assert any("analyze job failed entirely" in r.message for r in caplog.records)
