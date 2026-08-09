import json

import httpx
import pytest

from worker.ai.base import AIProviderError
from worker.ai.ollama_provider import OllamaProvider
from worker.config import Settings


def _provider(responses: list[str]) -> OllamaProvider:
    calls = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": next(calls)}, request=request)

    settings = Settings(
        _env_file=None,
        ollama_base_url="http://ollama.test",
        ollama_model="qwen3:8b",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaProvider(settings=settings, client=client)


def _analysis() -> dict:
    unknown = {"status": "UNKNOWN", "confidence": 0, "evidence": None}
    return {
        "challenge_type": "HACKATHON",
        "ai_policy": {"status": "ALLOWED", "confidence": 0.9, "evidence": "AI 활용 가능"},
        "ai_coding": unknown,
        "generative_ai": unknown,
        "ai_image": unknown,
        "ai_video": unknown,
        "ai_audio": unknown,
        "external_ai_api": unknown,
        "prompt_disclosure_required": False,
        "ai_usage_disclosure_required": False,
    }


@pytest.mark.asyncio
async def test_challenge_structured_output_accepts_markdown_wrapped_json():
    raw = f"설명\n```json\n{json.dumps(_analysis(), ensure_ascii=False)}\n```"
    result = await _provider([raw]).analyze_challenge("원문")

    assert result.challenge_type == "HACKATHON"
    assert result.ai_policy.status == "ALLOWED"
    assert result.ai_coding.status == "UNKNOWN"


@pytest.mark.asyncio
async def test_challenge_structured_output_repairs_once_then_fails():
    provider = _provider(["not json", "still not json"])
    with pytest.raises(AIProviderError, match="failed validation twice"):
        await provider.analyze_challenge("원문")
