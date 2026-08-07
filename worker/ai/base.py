"""AI provider interface. Default implementation is OllamaProvider (Phase 4, local-only -
see docs/ARCHITECTURE.md for why Railway's web tier never calls this directly).
Additional providers (Groq, OpenRouter, OpenAI, Claude) can be added by implementing
this same interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from worker.ai.schemas import ProjectExtraction


class AIProviderError(Exception):
    """Raised when a provider call fails after its single repair attempt."""


class AIProvider(ABC):
    @abstractmethod
    async def classify_project(self, text: str) -> str:
        """Return a ProjectType label for the given announcement text."""

    @abstractmethod
    async def extract_project(self, text: str) -> ProjectExtraction:
        """Extract structured project details. Raises AIProviderError on repair failure.

        Returns content only - the caller (not the provider) attaches provenance
        (model/model_version/prompt_version/analyzed_at) when persisting, since that's
        a pipeline-level concern, not something every provider implementation should
        have to know about.
        """

    @abstractmethod
    async def summarize_project(self, text: str) -> str:
        """Return a short human-readable summary of the announcement."""

    @abstractmethod
    async def extract_support_conditions(self, text: str) -> dict[str, Any]:
        """Structure free-text eligibility conditions from a support program announcement."""
