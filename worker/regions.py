"""Region vocabulary shared by the 기업마당 collector (which [지역] title tags count as a
region) and the cross-source dedupe (which 시·도 a region value covers). One list, so a word
the collector starts accepting can't be unknown to the dedupe region guard.

Words seen as 기업마당 title tags on 2026-10-07 (1,442 postings), plus K-Startup's
supt_regin values; several regions are joined with a middle dot ("대구ㆍ경북").
"""

from __future__ import annotations

import re

# 시·도 (and the merged 전남광주) - a region value naming one of these is specific.
PROVINCES = frozenset(
    {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원"}
    | {"충북", "충남", "전북", "전남", "경북", "경남", "제주", "전남광주"}
)

# Group words, expanded to the 시·도 they cover. Only the merged label 전남광주 expands to
# its parts; 광주 and 전남 stay themselves - mapping both onto 전남광주 would make every
# 광주/전남 pair "overlap".
GROUPS: dict[str, frozenset[str]] = {
    "수도권": frozenset({"서울", "인천", "경기"}),
    "충청": frozenset({"대전", "세종", "충북", "충남"}),
    "충청권": frozenset({"대전", "세종", "충북", "충남"}),
    "호남권": frozenset({"광주", "전남", "전북", "전남광주"}),
    "영남권": frozenset({"부산", "대구", "울산", "경북", "경남"}),
    "전남광주": frozenset({"전남광주", "전남", "광주"}),
}

# Valid region words that say nothing specific.
NON_SPECIFIC = frozenset({"전국", "비수도권"})

REGION_WORDS = PROVINCES | GROUPS.keys() | NON_SPECIFIC

SEPARATORS = re.compile(r"\s*[ㆍ·・,/]\s*")


def split_region(value: str) -> list[str]:
    return [part for part in SEPARATORS.split(value.strip()) if part]


def covered_provinces(region: str | None) -> frozenset[str]:
    """The 시·도 a region value covers, or an empty set when it isn't specific (전국,
    비수도권, or any word outside REGION_WORDS)."""
    if not region:
        return frozenset()
    covered: set[str] = set()
    for word in split_region(region):
        if word in GROUPS:
            covered |= GROUPS[word]
        elif word in PROVINCES:
            covered.add(word)
        else:
            return frozenset()
    return frozenset(covered)
