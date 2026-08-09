"""Conservative rule fallback for Challenge AI-use policies."""

from __future__ import annotations

import re

from worker.challenges.models import ChallengeAIAnalysis, PolicyAssessment, PolicyStatus
from worker.challenges.parsers import classify_challenge_type, normalize_whitespace

_PATTERNS: dict[PolicyStatus, tuple[str, ...]] = {
    "PROHIBITED": (
        r"(?:생성형\s*)?AI\s*(?:도구\s*)?(?:사용|활용)\s*(?:을\s*)?(?:금지|불허)",
        r"ChatGPT|Claude|Gemini",
    ),
    "REQUIRED": (
        r"(?:생성형\s*)?AI\s*(?:도구\s*)?(?:사용|활용)\s*(?:이\s*)?필수",
        r"AI\s*(?:를\s*)?활용한\s*(?:작품|서비스|결과물)",
    ),
    "LIMITED": (
        r"AI\s*(?:사용|활용).{0,30}(?:범위|도구|내역).{0,20}(?:명시|제출|공개)",
        r"AI\s*(?:사용|활용).{0,20}(?:일부|제한|조건부)",
    ),
    "ALLOWED": (
        r"(?:ChatGPT|Claude|Gemini)(?:\s*등)?\s*(?:생성형\s*)?AI\s*(?:사용|활용)\s*(?:이\s*)?(?:가능|허용)",
        r"(?:생성형\s*)?AI\s*(?:도구\s*)?(?:사용|활용)\s*(?:이\s*)?(?:가능|허용)",
    ),
}


def _sentences(text: str) -> list[str]:
    return [
        normalize_whitespace(part)
        for part in re.split(r"[\n。]|(?<=[.!?])\s+", text)
        if part.strip()
    ]


def _assess(text: str, *, topic: str | None = None) -> PolicyAssessment:
    candidates = _sentences(text)
    if topic:
        topic_re = re.compile(topic, re.I)
        candidates = [line for line in candidates if topic_re.search(line)]
    for status in ("PROHIBITED", "REQUIRED", "LIMITED", "ALLOWED"):
        for pattern in _PATTERNS[status]:
            compiled = re.compile(pattern, re.I)
            for line in candidates:
                # Tool names alone are not evidence of a policy. The first prohibited
                # pattern intentionally needs explicit 금지/불허 wording.
                if (
                    status == "PROHIBITED"
                    and pattern == r"ChatGPT|Claude|Gemini"
                    and not re.search(r"(?:사용|활용).{0,12}(?:금지|불허)", line)
                ):
                    continue
                if compiled.search(line):
                    section = line.split(":", 1)[0] if ":" in line else None
                    return PolicyAssessment(
                        status=status,
                        confidence=0.95,
                        evidence=line[:500],
                        source_section=section[:100] if section else None,
                        reason="명시적 규정 문구와 일치",
                    )
    return PolicyAssessment()


def analyze_ai_policy(title: str, original_text: str) -> ChallengeAIAnalysis:
    text = f"{title}\n{original_text}"
    overall = _assess(text)
    ai_coding = _assess(text, topic=r"AI\s*(?:코딩|coding)|코드\s*생성|Copilot")
    generative = _assess(text, topic=r"생성형\s*AI|ChatGPT|Claude|Gemini")
    image = _assess(text, topic=r"AI\s*(?:이미지|그림)|이미지\s*생성")
    video = _assess(text, topic=r"AI\s*(?:영상|비디오)|영상\s*생성")
    audio = _assess(text, topic=r"AI\s*(?:음성|오디오|음악)|음성\s*생성")
    external_api = _assess(text, topic=r"외부\s*(?:AI\s*)?API|OpenAI\s*API")
    disclosure = bool(re.search(r"AI\s*(?:사용|활용).{0,30}(?:명시|공개|제출)", text, re.I))
    prompt_disclosure = bool(re.search(r"프롬프트.{0,20}(?:명시|공개|제출)", text, re.I))
    return ChallengeAIAnalysis(
        challenge_type=classify_challenge_type(title, original_text),
        ai_policy=overall,
        ai_coding=ai_coding,
        generative_ai=generative,
        ai_image=image,
        ai_video=video,
        ai_audio=audio,
        external_ai_api=external_api,
        prompt_disclosure_required=prompt_disclosure,
        ai_usage_disclosure_required=disclosure,
    )
