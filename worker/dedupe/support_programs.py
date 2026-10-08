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
- when both sides have a deadline it must be the same day, plus overlap >= 0.8 and
  Jaccard >= 0.55. The same day is strong evidence but not proof - month-end deadlines
  are common, and a short generic title is nearly a subset of a longer unrelated one
  ("2026년 멘토링 프로그램" vs "[부산] 2026년 해양 멘토링 프로그램 참여기업 모집 공고":
  overlap 0.91, Jaccard 0.50). The weakest true dated pair measured 0.62.
- when either side has no deadline (65% of 기업마당 postings say "예산 소진시까지"),
  overlap >= 0.9 and Jaccard >= 0.65: the one false pair scored overlap 0.95 but Jaccard
  0.59, the weakest true date-less pair 0.70.
- a specific region on either side must be matched by an overlapping specific region on
  the other: generic titles recur in every region ("[대전] 2026년 창업보육센터 입주기업
  모집 공고" vs a Seoul incubator's "2026년 창업보육센터 입주기업 모집" scores 1.0/1.0).
  전국 doesn't count as a match - it is K-Startup's default (113 of ~175 open rows on
  2026-10-07, local incubators included), so it says nothing about where a program is.
  Measured on the 17 true pairs: 6 name the same region on both sides, the other 11 have
  no region on either (기업마당 untagged, K-Startup 전국) - none pairs a region with 전국,
  so the rule keeps all 17. Two regionless titles still pair. Organization names are not
  used: they differ in 7 of the 17 true pairs (e.g. 수행기관 "창업진흥원" vs K-Startup's
  "중소벤처기업부 장관").
- a 기업마당 copy whose leading [tag] can't be read as a region ("[경기 성남]") is never
  hidden: normalize_title drops the tag, so the copy would otherwise compare as
  region-less and pair with a 전국 K-Startup posting from anywhere. Every tag on the
  1,473 기업마당 titles of 2026-10-08 was readable; K-Startup's own "[한국도로공사]"-style
  organization tags are fine on the kept side.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from worker.regions import covered_provinces, has_unreadable_tag

OVERLAP_WITH_SAME_DEADLINE = 0.8
JACCARD_WITH_SAME_DEADLINE = 0.55
OVERLAP_WITHOUT_DEADLINE = 0.9
JACCARD_WITHOUT_DEADLINE = 0.65

_LEADING_TAGS = re.compile(r"^\s*(\[[^\]]*\]\s*)+")
# "\W" misses 기업마당's favourite middle dot: 'ㆍ' (U+318D) is a Hangul letter (category
# Lo), unlike '·' (U+00B7, Po). Without this "원전ㆍ에너지" and "원전·에너지" normalize
# differently.
_NON_WORD = re.compile(r"[\s\W_ㆍ]+")
_TRAILING_NOTICE = re.compile(r"(재|수정|변경|연장)?공고(문)?$")
_NUMBERS = re.compile(r"\d+")
_THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
# Apostrophe forms seen before an abbreviated year: ASCII ', curly ‘ ’, full-width ＇.
_SHORT_YEAR = re.compile(r"['‘’＇](\d{2})(?=\s*년)")


def _title_numbers(title: str) -> frozenset[str]:
    # The same number written two ways must compare equal: "1,000만원" vs "1000만원",
    # "'26년" vs "2026년".
    text = _THOUSANDS_SEPARATOR.sub("", title)
    text = _SHORT_YEAR.sub(lambda match: "20" + match.group(1), text)
    return frozenset(_NUMBERS.findall(text))


@dataclass(frozen=True)
class ProgramTitle:
    id: str
    title: str
    application_end: date | None
    region: str | None = None
    bigrams: frozenset[str] = field(init=False, compare=False)
    numbers: frozenset[str] = field(init=False, compare=False)
    regions: frozenset[str] = field(init=False, compare=False)
    # False when the title starts with a [tag] that isn't a readable region (see the module
    # docstring) - such a row is never hidden as a copy.
    may_be_hidden: bool = field(init=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bigrams", _bigrams(normalize_title(self.title)))
        object.__setattr__(self, "numbers", _title_numbers(self.title))
        object.__setattr__(self, "regions", covered_provinces(self.region))
        object.__setattr__(self, "may_be_hidden", not has_unreadable_tag(self.title))


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


def match_score(a: ProgramTitle, b: ProgramTitle) -> tuple[float, float] | None:
    """(overlap, Jaccard) when the two rows are the same program, else None."""
    if a.numbers != b.numbers:
        return None
    if (a.regions or b.regions) and not (a.regions & b.regions):
        return None
    if a.application_end is not None and b.application_end is not None:
        if a.application_end != b.application_end:
            return None
        min_overlap, min_jaccard = OVERLAP_WITH_SAME_DEADLINE, JACCARD_WITH_SAME_DEADLINE
    else:
        min_overlap, min_jaccard = OVERLAP_WITHOUT_DEADLINE, JACCARD_WITHOUT_DEADLINE
    overlap, jaccard = similarity(a, b)
    if overlap >= min_overlap and jaccard >= min_jaccard:
        return overlap, jaccard
    return None


def best_matches(
    keep: Iterable[ProgramTitle], hide: Iterable[ProgramTitle]
) -> dict[str, tuple[tuple[float, float], str]]:
    """Map each `hide` row that is the same program as some `keep` row to (score, that
    row's id) - the best-scoring one if several qualify: by overlap, then Jaccard, since a
    longer title that merely contains the candidate ties on overlap. `keep` rows are never
    hidden."""
    keep_rows = list(keep)
    duplicates: dict[str, tuple[tuple[float, float], str]] = {}
    for candidate in hide:
        if not candidate.may_be_hidden:
            continue
        best: tuple[tuple[float, float], str] | None = None
        for original in keep_rows:
            score = match_score(candidate, original)
            if score is not None and (best is None or score > best[0]):
                best = (score, original.id)
        if best is not None:
            duplicates[candidate.id] = best
    return duplicates


def plan_duplicate_marks(
    keep: Iterable[ProgramTitle],
    hide: Iterable[ProgramTitle],
    marked: Iterable[tuple[ProgramTitle, ProgramTitle]],
    current: Mapping[str, str | None],
) -> dict[str, str | None]:
    """The duplicate_of changes of one dedupe pass (see plan_updates).

    `hide` rows (open 기업마당 rows) are paired with the best `keep` row (open K-Startup
    rows). An existing mark - (copy, its original) in `marked` - that found no open
    original stays as long as the pair still matches under the current rule: the original
    closing is no reason to un-pair them - un-pairing would list the program twice under
    "마감 포함 전체". A mark only decides which row stands for the pair in a listing
    (list_support_programs: the original, unless only the copy is open); it never changes
    either row's 모집 status. So a mark moves only to a strictly better-scoring original,
    and is cleared only when the rule no longer matches."""
    best = best_matches(keep, hide)
    for copy, original in marked:
        existing = match_score(copy, original) if copy.may_be_hidden else None
        if existing is not None and (copy.id not in best or best[copy.id][0] <= existing):
            best[copy.id] = (existing, original.id)
    return plan_updates(current, {row_id: original for row_id, (_, original) in best.items()})


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
