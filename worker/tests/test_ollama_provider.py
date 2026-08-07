import json

import httpx
import pytest

from worker.ai.base import AIProviderError
from worker.ai.ollama_provider import OllamaProvider
from worker.config import Settings

VALID_EXTRACTION = {
    "project_type": "AI_ML",
    "technologies": [{"name": "Python", "confidence": 0.9, "evidence": "명시적으로 언급됨"}],
    "required_roles": ["백엔드 개발자"],
    "requirements": ["데이터 파이프라인 구축"],
    "risks": [],
    "summary": "테스트 요약",
}


def _settings() -> Settings:
    return Settings(_env_file=None, ollama_base_url="http://ollama.test", ollama_model="qwen3:8b")


def _provider(handler) -> OllamaProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaProvider(settings=_settings(), client=client)


@pytest.mark.asyncio
async def test_extract_project_success_first_try():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": json.dumps(VALID_EXTRACTION)})

    result = await _provider(handler).extract_project("테스트 공고 내용")

    assert result.project_type == "AI_ML"
    assert result.technologies[0].name == "Python"
    assert result.summary == "테스트 요약"


@pytest.mark.asyncio
async def test_extract_project_repairs_after_invalid_first_response():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"response": "not valid json"})
        return httpx.Response(200, json={"response": json.dumps(VALID_EXTRACTION)})

    result = await _provider(handler).extract_project("테스트 공고 내용")

    assert calls["n"] == 2
    assert result.project_type == "AI_ML"


@pytest.mark.asyncio
async def test_extract_project_raises_after_two_invalid_responses():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "still not valid json"})

    with pytest.raises(AIProviderError, match="failed validation twice"):
        await _provider(handler).extract_project("테스트 공고 내용")


@pytest.mark.asyncio
async def test_extract_project_raises_when_response_field_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with pytest.raises(AIProviderError, match="no 'response' field"):
        await _provider(handler).extract_project("테스트 공고 내용")


@pytest.mark.asyncio
async def test_classify_project_delegates_to_extract_project():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": json.dumps(VALID_EXTRACTION)})

    result = await _provider(handler).classify_project("테스트 공고 내용")

    assert result == "AI_ML"


@pytest.mark.asyncio
async def test_summarize_project_delegates_to_extract_project():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": json.dumps(VALID_EXTRACTION)})

    result = await _provider(handler).summarize_project("테스트 공고 내용")

    assert result == "테스트 요약"


@pytest.mark.asyncio
async def test_extract_support_conditions_not_implemented():
    provider = OllamaProvider(settings=_settings(), client=httpx.Client())
    with pytest.raises(NotImplementedError):
        await provider.extract_support_conditions("텍스트")
