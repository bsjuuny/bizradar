"""Cross-source duplicate detection for support_programs: the same 지원사업 공고 posted on
both K-Startup and 기업마당. Rule-based and deterministic, like the rest of the pipeline.
See docs/SUPPORT_PROGRAMS.md.

Measured 2026-10-07 against real data (157 open K-Startup rows from the DB, 1,442
announcements from the public 기업마당 list): the two sources barely overlap - most
K-Startup postings are private incubators and university 창업보육센터 programs that
기업마당 doesn't carry. 18 candidate pairs, all read by hand: 17 were the same announcement,
1 was not (기업마당 "스타트업 법률지원사업 참여기업 모집" vs. K-Startup "같은 사업의 대전
법률상담회 참가 안내"). The thresholds below keep all 17 and drop that one.

Titles differ in predictable ways between the two sites, which is why exact matching
finds 0 of the 17: 기업마당 prefixes "[지역]" and suffixes "공고", K-Startup wraps names
in 「」 or moves "4차" to the end, and spacing/punctuation varies ("관악 × SK" vs
"관악 X SK", "원전ㆍ에너지" vs "원전·에너지"). So titles are normalized, then compared
as character-bigram sets:
- overlap coefficient (|A∩B| / min(|A|,|B|)) tolerates one side adding words;
- the set of numbers in the title must be identical - this is what separates
  "2026년 2차" from "2026년 3차" of the same recurring program, which otherwise score
  0.85+ (seen in the data: 용인시 해외진출 종합지원사업 2차 vs 3차);
- when both sides have a deadline it must be the same day, which is strong evidence on
  its own (overlap >= 0.8). When either side has none (65% of 기업마당 postings say
  "예산 소진시까지" instead of a date), Jaccard >= 0.65 is required on top of overlap
  >= 0.9: the one false pair scored overlap 0.95 but Jaccard 0.59, the weakest true
  date-less pair 0.70.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

OVERLAP_WITH_SAME_DEADLINE = 0.8
OVERLAP_WITHOUT_DEADLINE = 0.9
JACCARD_WITHOUT_DEADLINE = 0.65

_LEADING_TAGS = re.compile(r"^\s*(\[[^\]]*\]\s*)+")
_NON_WORD = re.compile(r"[\s\W_]+")
_TRAILING_NOTICE = re.compile(r"(재|수정|변경|연장)?공고(문)?$")
_NUMBERS = re.compile(r"\d+")


@dataclass(frozen=True)
class ProgramTitle:
    id: str
    title: str
    application_end: date | None
    normalized: str = field(init=False, compare=False)
    bigrams: frozenset[str] = field(init=False, compare=False)
    numbers: frozenset[str] = field(init=False, compare=False)

    def __post_init__(self) -> None:
        normalized = normalize_title(self.title)
        object.__setattr__(self, "normalized", normalized)
        object.__setattr__(self, "bigrams", _bigrams(normalized))
        object.__setattr__(self, "numbers", frozenset(_NUMBERS.findall(self.title)))


def normalize_title(title: str) -> str:
    text = _LEADING_TAGS.sub("", title)
    text = _NON_WORD.sub("", text)
    return _TRAILING_NOTICE.sub("", text).lower()


def _bigrams(text: str) -> frozenset[str]:
    if len(text) < 2:
        return frozenset({text}) if text else frozenset()
    return frozenset(text[i : i + 2] for i in range(len(text) - 1))


def similarity(a: ProgramTitle, b: ProgramTitle) -> tuple[float, float]:
    """(overlap coefficient, Jaccard) of the two titles' bigram sets."""
    if not a.bigrams or not b.bigrams:
        return 0.0, 0.0
    shared = len(a.bigrams & b.bigrams)
    return shared / min(len(a.bigrams), len(b.bigrams)), shared / len(a.bigrams | b.bigrams)


def is_same_program(a: ProgramTitle, b: ProgramTitle) -> bool:
    if a.numbers != b.numbers:
        return False
    overlap, jaccard = similarity(a, b)
    if a.application_end is not None and b.application_end is not None:
        return a.application_end == b.application_end and overlap >= OVERLAP_WITH_SAME_DEADLINE
    return overlap >= OVERLAP_WITHOUT_DEADLINE and jaccard >= JACCARD_WITHOUT_DEADLINE


def find_duplicates(keep: Iterable[ProgramTitle], hide: Iterable[ProgramTitle]) -> dict[str, str]:
    """Map each `hide` row that is the same program as some `keep` row to that row's id
    (the best-scoring one if several qualify - by overlap, then Jaccard, since a longer
    title that merely contains the candidate ties on overlap). `keep` rows are never
    hidden."""
    keep_rows = list(keep)
    duplicates: dict[str, str] = {}
    for candidate in hide:
        best: tuple[tuple[float, float], str] | None = None
        for original in keep_rows:
            if not is_same_program(candidate, original):
                continue
            score = similarity(candidate, original)
            if best is None or score > best[0]:
                best = (score, original.id)
        if best is not None:
            duplicates[candidate.id] = best[1]
    return duplicates


def plan_updates(
    current: Mapping[str, str | None], duplicates: Mapping[str, str]
) -> dict[str, str | None]:
    """Only the rows whose duplicate_of actually changes: newly found duplicates, ones
    now pointing elsewhere, and stale marks to clear (row no longer matches)."""
    changes: dict[str, str | None] = {}
    for row_id, existing in current.items():
        wanted = duplicates.get(row_id)
        if wanted != existing:
            changes[row_id] = wanted
    return changes
