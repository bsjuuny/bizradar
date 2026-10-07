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

# Official long forms, read as the short word. None were among the 2026-10-07 title tags
# (all short), but they are how a 시·도 is usually spelled out in full.
ALIASES = {
    "서울특별시": "서울",
    "서울시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "경기도": "경기",
    "강원도": "강원",
    "강원특별자치도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전라북도": "전북",
    "전북특별자치도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주도": "제주",
    "제주특별자치도": "제주",
}

REGION_WORDS = PROVINCES | GROUPS.keys() | NON_SPECIFIC

# Middle dots, commas, slashes - or just spaces ("[대구 경북]").
SEPARATORS = re.compile(r"\s*[ㆍ·・,/]\s*|\s+")


_LEADING_TAG = re.compile(r"^\s*\[([^\]]+)\]")


def split_region(value: str) -> list[str]:
    parts = (part for part in SEPARATORS.split(value.strip()) if part)
    return [ALIASES.get(part, part) for part in parts]


def title_tag_region(title: str) -> str | None:
    """The region named by a title's leading [tag] ("[대구ㆍ경북] ..." -> "대구·경북"), or
    None when there is no tag or any part of it isn't a region word - "[한국도로공사]" is
    an organization (K-Startup titles carry those)."""
    match = _LEADING_TAG.match(title)
    if not match:
        return None
    parts = split_region(match.group(1))
    if not parts or any(part not in REGION_WORDS for part in parts):
        return None
    return "·".join(parts)


def has_unreadable_tag(title: str) -> bool:
    """A leading [tag] that title_tag_region can't read ("[서울 강남구]", "[경기 성남]")."""
    return _LEADING_TAG.match(title) is not None and title_tag_region(title) is None


def covered_provinces(region: str | None) -> frozenset[str]:
    """The 시·도 a region value covers; an empty set when it says nothing specific (no
    value, 전국, 비수도권).

    A word outside the vocabulary is not "nationwide": next to a known 시·도 it is taken
    as a place inside it ("경기 성남" -> 경기); on its own the value stays specific but
    unreadable - a set holding just the raw value, which overlaps only the same value, so
    the dedupe region guard blocks rather than waves through. All 18 K-Startup values of
    2026-10-08 are in the vocabulary."""
    if not region:
        return frozenset()
    covered: set[str] = set()
    unknown = False
    for word in split_region(region):
        if word in GROUPS:
            covered |= GROUPS[word]
        elif word in PROVINCES:
            covered.add(word)
        elif word not in NON_SPECIFIC:
            unknown = True
    if unknown and not covered:
        return frozenset({"?" + region.strip()})
    return frozenset(covered)
