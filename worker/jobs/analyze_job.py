"""Scheduled AI analysis job. Runs the rule-filtered LIKELY_IT backlog through Ollama,
a handful at a time (each call is ~60s on CPU - see worker/ai/ollama_provider.py). A
total failure (e.g. Ollama not running) is caught and logged, not raised - existing
opportunities keep displaying without analysis rather than blocking anything else
(docs/DATA_PIPELINE.md#failure-isolation). Per-item failures are isolated and recorded
as FAILED rows, not retried indefinitely (section 23 of the original spec: one repair
attempt inside the provider, then FAILED - this job does not retry beyond that)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from worker.ai.base import AIProviderError
from worker.ai.ollama_provider import PROMPT_VERSION, OllamaProvider
from worker.repositories.project_analyses import (
    get_pending_opportunities,
    upsert_failure,
    upsert_success,
)

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5


def _build_prompt_text(opportunity: dict) -> str:
    lines = [f"공고명: {opportunity['title']}"]
    if opportunity.get("organization"):
        lines.append(f"발주기관: {opportunity['organization']}")
    if opportunity.get("demand_organization"):
        lines.append(f"수요기관: {opportunity['demand_organization']}")
    if opportunity.get("budget_amount"):
        lines.append(f"배정예산: {opportunity['budget_amount']:,.0f}원")
    return "\n".join(lines)


async def _analyze_batch(batch_size: int) -> tuple[int, int]:
    pending = get_pending_opportunities("LIKELY_IT", batch_size)
    if not pending:
        return 0, 0

    succeeded = 0
    failed = 0

    with OllamaProvider() as provider:
        model_version = provider.get_model_digest() or "unknown"

        for opportunity in pending:
            text = _build_prompt_text(opportunity)
            try:
                extraction = await provider.extract_project(text)
                upsert_success(
                    opportunity["id"],
                    opportunity["content_hash"],
                    extraction,
                    model=provider.settings.ollama_model,
                    model_version=model_version,
                    prompt_version=PROMPT_VERSION,
                )
                succeeded += 1
            except AIProviderError as exc:
                logger.warning(
                    "analyze: extraction failed",
                    extra={"opportunity_id": opportunity["id"], "error": str(exc)},
                )
                upsert_failure(opportunity["id"], opportunity["content_hash"], str(exc))
                failed += 1
            except Exception as exc:  # noqa: BLE001 - isolate per-item failures
                logger.warning(
                    "analyze: unexpected error",
                    extra={"opportunity_id": opportunity["id"], "error": str(exc)},
                )
                upsert_failure(opportunity["id"], opportunity["content_hash"], str(exc))
                failed += 1

    return succeeded, failed


def run(batch_size: int = DEFAULT_BATCH_SIZE) -> None:
    started_at = datetime.now(UTC)
    try:
        succeeded, failed = asyncio.run(_analyze_batch(batch_size))
    except Exception:
        logger.exception(
            "analyze job failed entirely - opportunities display without analysis",
            extra={"job": "analyze", "status": "failed"},
        )
        return

    duration_seconds = (datetime.now(UTC) - started_at).total_seconds()
    logger.info(
        "analyze job finished",
        extra={
            "job": "analyze",
            "status": "ok" if failed == 0 else "partial",
            "duration": duration_seconds,
            "succeeded": succeeded,
            "failed": failed,
        },
    )
