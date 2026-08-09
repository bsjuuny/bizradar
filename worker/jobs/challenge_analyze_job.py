"""Challenge AI analysis with conservative rule fallback and per-item isolation."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from worker.ai.ollama_provider import CHALLENGE_PROMPT_VERSION, OllamaProvider
from worker.challenges.ai_policy import analyze_ai_policy
from worker.config import get_settings
from worker.repositories.challenges import get_pending_challenges, update_challenge_analysis

logger = logging.getLogger(__name__)
DEFAULT_BATCH_SIZE = 5
AI_TERMS = ("ai", "인공지능", "생성형", "chatgpt", "claude", "gemini", "llm")


def _has_ai_terms(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in AI_TERMS)


async def _analyze(batch_size: int) -> tuple[int, int]:
    pending = get_pending_challenges(batch_size)
    if not pending:
        return 0, 0

    succeeded = 0
    failed = 0
    provider: OllamaProvider | None = None
    try:
        for challenge in pending:
            text = f"공모전명: {challenge['title']}\n\n{challenge['original_text']}"
            if not _has_ai_terms(text):
                fallback = analyze_ai_policy(challenge["title"], challenge["original_text"])
                update_challenge_analysis(
                    challenge["id"],
                    fallback,
                    status="SKIPPED",
                    error=None,
                    model=None,
                    prompt_version=CHALLENGE_PROMPT_VERSION,
                )
                succeeded += 1
                continue
            if provider is None:
                provider = OllamaProvider()
            try:
                analysis = await provider.analyze_challenge(text)
                update_challenge_analysis(
                    challenge["id"],
                    analysis,
                    status="SUCCESS",
                    error=None,
                    model=provider.settings.ollama_model,
                    prompt_version=CHALLENGE_PROMPT_VERSION,
                )
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 - rule fallback is the safety boundary
                fallback = analyze_ai_policy(challenge["title"], challenge["original_text"])
                update_challenge_analysis(
                    challenge["id"],
                    fallback,
                    status="FAILED",
                    error=str(exc),
                    model=None,
                    prompt_version=CHALLENGE_PROMPT_VERSION,
                )
                failed += 1
                logger.warning(
                    "challenge AI failed; saved conservative rule fallback",
                    extra={
                        "job": "challenge:reanalyze",
                        "challenge_id": challenge["id"],
                        "status": "fallback",
                        "error_code": type(exc).__name__,
                    },
                )
    finally:
        if provider is not None:
            provider.close()
    return succeeded, failed


def run(batch_size: int = DEFAULT_BATCH_SIZE) -> tuple[int, int]:
    settings = get_settings()
    if not settings.feature_challenge or not settings.challenge_ai_analysis_enabled:
        return 0, 0
    started = datetime.now(UTC)
    try:
        result = asyncio.run(_analyze(batch_size))
    except Exception:
        logger.exception(
            "challenge AI job failed entirely; collected records remain available",
            extra={"job": "challenge:reanalyze", "status": "failed"},
        )
        return 0, 0
    logger.info(
        "challenge AI job finished",
        extra={
            "job": "challenge:reanalyze",
            "status": "ok" if result[1] == 0 else "partial",
            "succeeded": result[0],
            "failed": result[1],
            "duration": (datetime.now(UTC) - started).total_seconds(),
        },
    )
    return result
