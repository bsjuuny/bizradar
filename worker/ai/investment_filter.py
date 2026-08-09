"""Rule filter for K-Startup announcements: flags programs linked to private
investment (TIPS, angel investment, VC-run demo days, ...) vs. plain government support
programs with no investment component. Same keyword-substring approach as
worker/ai/rule_filter.py (see docs/DATA_PIPELINE.md#support-programs), applied to the
title and free-text description together.

Short, ambiguous 2-3 letter Latin acronyms ("VC", "IR") are deliberately left out -
rule_filter.py's "AI" false positives (AI타워, AIDed - see its module docstring) already
showed this class of keyword is unsafe as a plain substring match. Every keyword here is
a distinctive, multi-syllable Korean term or an unambiguous English phrase unlikely to
appear as an accidental substring.
"""

_INVESTMENT_KEYWORDS = [
    "팁스",
    "TIPS",
    "엔젤투자",
    "벤처투자",
    "투자유치",
    "투자연계",
    "투자자",
    "투자심사",
    "투자설명회",
    "투자상담",
    "데모데이",
    "액셀러레이터",
    "크라우드펀딩",
    "시드투자",
    "후속투자",
    "프리시리즈",
    "시리즈A",
    "임팩트투자",
]


def is_investment_linked(title: str, description: str | None = None) -> bool:
    text = f"{title} {description or ''}"
    return any(keyword in text for keyword in _INVESTMENT_KEYWORDS)
