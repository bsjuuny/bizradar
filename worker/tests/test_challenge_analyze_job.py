import httpx
import pytest

from worker.jobs import challenge_analyze_job


class FakeProvider:
    def __init__(self, *args, **kwargs):
        self.settings = type("Settings", (), {"ollama_model": "test-model"})()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def close(self):
        return None

    async def analyze_challenge(self, text):
        raise httpx.ReadTimeout("LLM timed out")


@pytest.mark.asyncio
async def test_no_ai_terms_skip_llm_and_keep_unknown(monkeypatch):
    updates = []
    monkeypatch.setattr(
        challenge_analyze_job,
        "get_pending_challenges",
        lambda limit: [{"id": "1", "title": "아이디어 공모전", "original_text": "포스터 제출"}],
    )
    monkeypatch.setattr(
        challenge_analyze_job,
        "update_challenge_analysis",
        lambda *args, **kwargs: updates.append((args, kwargs)),
    )
    monkeypatch.setattr(
        challenge_analyze_job,
        "OllamaProvider",
        lambda: (_ for _ in ()).throw(AssertionError("LLM must not be created")),
    )

    assert await challenge_analyze_job._analyze(5) == (1, 0)
    assert updates[0][1]["status"] == "SKIPPED"
    assert updates[0][0][1].ai_policy.status == "UNKNOWN"


@pytest.mark.asyncio
async def test_llm_timeout_saves_conservative_failed_fallback(monkeypatch):
    updates = []
    monkeypatch.setattr(
        challenge_analyze_job,
        "get_pending_challenges",
        lambda limit: [{"id": "1", "title": "AI 공모전", "original_text": "결과물을 제출"}],
    )
    monkeypatch.setattr(challenge_analyze_job, "OllamaProvider", FakeProvider)
    monkeypatch.setattr(
        challenge_analyze_job,
        "update_challenge_analysis",
        lambda *args, **kwargs: updates.append((args, kwargs)),
    )

    assert await challenge_analyze_job._analyze(5) == (0, 1)
    assert updates[0][1]["status"] == "FAILED"
    assert updates[0][0][1].ai_policy.status == "UNKNOWN"
    assert "timed out" in updates[0][1]["error"]
