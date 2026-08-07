"""Ollama-backed AIProvider - local-only, never called from Railway (docs/ARCHITECTURE.md).

Methods are declared `async` to match the AIProvider interface, but the HTTP call
underneath is a plain sync httpx.Client, not httpx.AsyncClient: a local Ollama instance
serves one generation at a time regardless, so concurrent requests wouldn't be faster,
just queued - there's no real concurrency to gain by making the I/O actually async here.

Verified live before this shipped (2026-08-07): a single extract_project call against
qwen3:8b on CPU took ~61s and produced valid, schema-conforming JSON with correct Korean
text - see docs/DATA_PIPELINE.md and docs/VERIFICATION_REPORT.md.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from worker.ai.base import AIProvider, AIProviderError
from worker.ai.schemas import ProjectExtraction
from worker.config import Settings, get_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v4"  # v3 bounded array lengths; v4 dedupes list fields (schemas.py)
# A single call was observed at ~61s on CPU; leave generous headroom rather than
# guessing at a "safe" lower number that might flake on a slower run.
REQUEST_TIMEOUT_SECONDS = 300.0

# Every array field has maxItems. Without it, a live run produced a genuine repetition
# loop: required_qualifications came back with the same certification name duplicated
# ~15 times before the string got cut off mid-word - schema-valid (list[str] has no
# length constraint) but useless, and the next real item then timed out at 300s, almost
# certainly the same failure mode costing enough extra generation time to blow the
# budget. Bounding array length is a direct mitigation, not a guess.
_PROJECT_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "project_type": {
            "type": "string",
            "enum": [
                "SYSTEM_BUILD",
                "MAINTENANCE",
                "CONSULTING",
                "DATA_ANALYTICS",
                "AI_ML",
                "INFRASTRUCTURE",
                "OTHER",
            ],
        },
        "technologies": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "confidence", "evidence"],
            },
        },
        "required_roles": {"type": "array", "maxItems": 8, "items": {"type": "string"}},
        "requirements": {"type": "array", "maxItems": 8, "items": {"type": "string"}},
        "risks": {"type": "array", "maxItems": 8, "items": {"type": "string"}},
        "summary": {"type": "string"},
        "min_experience_years": {"type": ["integer", "null"]},
        "required_qualifications": {"type": "array", "maxItems": 8, "items": {"type": "string"}},
    },
    "required": ["project_type", "summary"],
}


class OllamaProvider(AIProvider):
    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    def __enter__(self) -> OllamaProvider:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
        return self._client

    def get_model_digest(self) -> str | None:
        """Short digest for the configured model, for provenance tracking
        (project_analyses.model_version) - not a semantic version, Ollama doesn't have
        one; a content digest is the closest honest equivalent."""
        try:
            resp = self._get_client().get(f"{self.settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            for model in resp.json().get("models", []):
                if model.get("name") == self.settings.ollama_model:
                    digest = model.get("digest", "")
                    return digest[:12] or None
        except httpx.HTTPError:
            logger.warning("ollama: could not fetch model digest", exc_info=True)
        return None

    def _generate(self, prompt: str, schema: dict[str, Any]) -> str:
        resp = self._get_client().post(
            f"{self.settings.ollama_base_url}/api/generate",
            json={
                "model": self.settings.ollama_model,
                "prompt": prompt,
                "format": schema,
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        response_text = data.get("response")
        if not response_text:
            raise AIProviderError(f"Ollama returned no 'response' field: {list(data.keys())}")
        return response_text

    def _extract_with_repair(self, prompt: str) -> ProjectExtraction:
        raw = self._generate(prompt, _PROJECT_EXTRACTION_SCHEMA)
        try:
            return ProjectExtraction.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as first_error:
            logger.warning(
                "ollama: validation failed, attempting one repair",
                extra={"error": str(first_error)},
            )
            repair_prompt = (
                f"{prompt}\n\n이전 응답이 스키마와 맞지 않았다 ({first_error}). "
                "다시 올바른 JSON으로만 답하라."
            )
            raw_retry = self._generate(repair_prompt, _PROJECT_EXTRACTION_SCHEMA)
            try:
                return ProjectExtraction.model_validate_json(raw_retry)
            except (ValidationError, json.JSONDecodeError) as second_error:
                raise AIProviderError(
                    f"Ollama output failed validation twice: {second_error}"
                ) from second_error

    async def extract_project(self, text: str) -> ProjectExtraction:
        prompt = (
            "다음 공공 입찰공고를 분석해서 JSON으로 답하라. "
            "기술 스택은 공고 내용에 명시적으로 언급되거나 강하게 암시된 것만 포함하라. "
            "요구 경력(예: '유사사업 수행실적 3년 이상')이 명시되어 있으면 "
            "min_experience_years에 숫자만 넣고, 없으면 null로 두라. "
            "요구 자격/인증(예: 'SW사업자 등록', '정보보호관리체계 인증')이 있으면 "
            "required_qualifications에 나열하고, 없으면 빈 배열로 두라. "
            "모든 배열 항목은 서로 중복되지 않아야 하며 각 배열은 최대 5개까지만 포함하라.\n\n"
            f"{text}"
        )
        return self._extract_with_repair(prompt)

    async def classify_project(self, text: str) -> str:
        # Delegates to extract_project rather than a separate prompt: nothing in this
        # pipeline calls classify_project standalone yet (the rule filter, not the LLM,
        # does NON_IT/LIKELY_IT/UNKNOWN - see worker/ai/rule_filter.py), so a second,
        # untested prompt/schema for a code path nothing exercises isn't worth building.
        extraction = await self.extract_project(text)
        return extraction.project_type

    async def summarize_project(self, text: str) -> str:
        extraction = await self.extract_project(text)
        return extraction.summary

    async def extract_support_conditions(self, text: str) -> dict[str, Any]:
        raise NotImplementedError(
            "extract_support_conditions is Phase 6 (BizInfo/K-Startup) - not implemented yet"
        )
