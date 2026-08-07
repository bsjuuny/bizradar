"""Structured output schema for AI project analysis. See docs/DATA_PIPELINE.md."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProjectType = Literal[
    "SYSTEM_BUILD",
    "MAINTENANCE",
    "CONSULTING",
    "DATA_ANALYTICS",
    "AI_ML",
    "INFRASTRUCTURE",
    "OTHER",
]


class TechnologyMatch(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str


class ProjectAnalysis(BaseModel):
    project_type: ProjectType
    technologies: list[TechnologyMatch] = []
    required_roles: list[str] = []
    requirements: list[str] = []
    risks: list[str] = []
    summary: str = ""

    model: str
    model_version: str
    prompt_version: str
    analyzed_at: datetime
