"""Cross-source duplicate rule. Every title pair below is real: K-Startup titles from the
support_programs table, 기업마당 titles from the public list page, both 2026-10-07 - the
same data the thresholds were chosen on (see worker/dedupe/support_programs.py)."""

from datetime import date

import pytest

from worker.dedupe.support_programs import (
    ProgramTitle,
    best_matches,
    match_score,
    normalize_title,
    plan_duplicate_marks,
    plan_updates,
)


def find_duplicates(keep, hide):
    """best_matches without the scores - what most tests compare."""
    return {row_id: original for row_id, (_, original) in best_matches(keep, hide).items()}


def _same(a: ProgramTitle, b: ProgramTitle) -> bool:
    return match_score(a, b) is not None


def _p(title: str, end: date | None, id_: str = "x") -> ProgramTitle:
    return ProgramTitle(id_, title, end)


# (기업마당, its deadline, K-Startup, its deadline) - the same announcement on both sites.
SAME = [
    (
        "2026년 한수원 우문현답 현장 클리닉센터 지원사업 원전ㆍ에너지 분야 선택형 과제 "
        "참여기업 모집 공고",
        date(2026, 10, 8),
        "2026년 한수원 우문현답 현장 클리닉센터 지원사업 「원전·에너지 분야 선택형 과제」"
        "참여기업 모집 공고",
        date(2026, 10, 8),
    ),
    (
        "2026년 4차 과학기술분야 R&D 대체인력 활용 지원사업 모집 공고",
        date(2026, 10, 13),
        "2026년 과학기술분야 R&D 대체인력 활용 지원사업 4차 모집 공고",
        date(2026, 10, 13),
    ),
    (
        "[서울] 2026년 서울창업센터 관악 × SK에코플랜트 오픈이노베이션 참여기업 모집 공고",
        date(2026, 10, 11),
        "2026년 서울창업센터 관악 X SK에코플랜트 오픈이노베이션 프로그램 참여기업 모집",
        date(2026, 10, 11),
    ),
    (
        "2026년 한국도로공사 상생형 창업ㆍ벤처기업 지원사업 모집 공고",
        date(2026, 10, 28),
        "[한국도로공사] 2026년 상생형 창업, 벤처기업 지원사업",
        date(2026, 10, 28),
    ),
    (
        "싱가포르 현지 진출 지원 국내 블록체인 기업 모집 공고",
        date(2026, 10, 8),
        "싱가포르 현지 진출 지원 국내 블록체인 기업 모집 재공고",
        date(2026, 10, 8),
    ),
    # 기업마당 says "예산 소진시까지" etc. -> no deadline on that side.
    (
        "[서울] 서대문구 2026년 청년창업기업 및 사회연대경제기업 수시 전문상담 경영컨설팅 "
        "신청 기업 모집 공고",
        None,
        "2026년 서대문구 청년창업기업 및 사회연대경제기업 수시 전문상담 경영컨설팅 "
        "신청 기업 모집 공고",
        date(2026, 11, 30),
    ),
    (
        "2026년 강원창조경제혁신센터 창업-BuS 프로그램 강원브릿지 화요IR 참여기업 모집 공고",
        None,
        "2026년 창업-Bus 프로그램「강원브릿지 화요IR」 참여기업 모집",
        date(2026, 11, 30),
    ),
    (
        "[서울] 2026년 중동상황 대응 물류지원금 지원사업 모집 공고",
        None,
        "2026년 중동상황 대응 「수출위기 극복 물류지원금」 지원사업 모집",
        date(2026, 12, 31),
    ),
]

# Close-scoring pairs that are NOT the same announcement.
DIFFERENT = [
    # The one false candidate in the measurement: the program in general vs. one city's
    # consultation session under it (K-Startup also has 대구/... sessions as separate rows).
    (
        "2026년 스타트업 법률지원사업 참여기업 모집 수정 공고",
        None,
        "2026년 스타트업 법률지원사업 대전광역시 법률상담회 참여 기업 모집 안내",
        date(2026, 10, 13),
    ),
    # Recurring program, different round: 0.85+ similar but a different 차수.
    (
        "[경기] 용인시 2026년 3차 해외진출 종합지원사업(해외물류비) 공고",
        date(2026, 10, 20),
        "[경기] 용인시 2026년 2차 해외진출 종합지원사업(해외물류비) 공고",
        date(2026, 10, 20),
    ),
    # Same words, different deadline.
    (
        "2026년 제2회 반려동물 창업 아이디어 경진대회 참가자 모집 공고",
        date(2026, 10, 9),
        "2026 제2회 반려동물 창업 아이디어 경진대회 참가자 모집",
        date(2026, 10, 11),
    ),
    # Regional sibling programs of one national scheme.
    (
        "2026년 전남 창업BuS 프로그램 창업기업 모집 공고",
        None,
        "2026년 창업-Bus 프로그램「강원브릿지 화요IR」 참여기업 모집",
        date(2026, 11, 30),
    ),
]


@pytest.mark.parametrize(("bz", "bz_end", "ks", "ks_end"), SAME)
def test_same_announcement_on_both_sites_matches(bz, bz_end, ks, ks_end):
    assert _same(_p(bz, bz_end), _p(ks, ks_end))


@pytest.mark.parametrize(("bz", "bz_end", "ks", "ks_end"), DIFFERENT)
def test_different_announcements_do_not_match(bz, bz_end, ks, ks_end):
    assert not _same(_p(bz, bz_end), _p(ks, ks_end))


def test_normalize_title_strips_tags_punctuation_and_notice_suffix():
    assert normalize_title("[서울] 2026년 3차 B the B 팝업 참여기업 모집 재공고") == (
        "2026년3차btheb팝업참여기업모집"
    )
    assert (
        normalize_title("「민관협력 오픈이노베이션 지원」 모집공고")
        == "민관협력오픈이노베이션지원모집"
    )


def test_find_duplicates_maps_hidden_row_to_kept_row():
    keep = [
        _p(SAME[0][2], SAME[0][3], "ks-1"),
        _p(SAME[1][2], SAME[1][3], "ks-2"),
        _p(DIFFERENT[0][2], DIFFERENT[0][3], "ks-3"),
    ]
    hide = [
        _p(SAME[0][0], SAME[0][1], "bz-1"),
        _p(SAME[1][0], SAME[1][1], "bz-2"),
        _p(DIFFERENT[0][0], DIFFERENT[0][1], "bz-3"),
        _p("2026년 중소기업 수출지원사업 통합 공고", None, "bz-4"),
    ]

    assert find_duplicates(keep, hide) == {"bz-1": "ks-1", "bz-2": "ks-2"}


def test_find_duplicates_picks_best_scoring_original():
    exact = _p("2026년 대한민국 물산업 혁신 창업대전 참가자 모집", date(2026, 10, 19), "exact")
    looser = _p(
        "2026년 대한민국 물산업 혁신 창업대전 참가자 모집 및 부대행사 안내",
        date(2026, 10, 19),
        "looser",
    )
    hidden = _p("2026년 대한민국 물산업 혁신 창업대전 참가자 모집 공고", date(2026, 10, 19), "bz")

    assert find_duplicates([looser, exact], [hidden]) == {"bz": "exact"}


def test_plan_updates_only_returns_changes():
    current = {"a": None, "b": "ks-1", "c": "ks-2", "d": None}
    duplicates = {"a": "ks-9", "b": "ks-1", "c": "ks-3"}

    assert plan_updates(current, duplicates) == {"a": "ks-9", "c": "ks-3"}


def test_plan_updates_clears_marks_that_no_longer_hold():
    assert plan_updates({"a": "ks-1"}, {}) == {"a": None}


def test_hangul_and_latin_middle_dots_normalize_the_same():
    # 'ㆍ' (U+318D) is a Hangul letter to the regex engine, '·' (U+00B7) punctuation.
    assert normalize_title("원전ㆍ에너지ㆍ수소 창업ㆍ벤처") == normalize_title(
        "원전·에너지·수소 창업·벤처"
    )
    assert _same(
        _p("[경북] 2026년 원전ㆍ에너지ㆍ수소 창업ㆍ벤처 지원사업 모집 공고", None),
        _p("2026년 원전·에너지·수소 창업·벤처 지원사업 모집", date(2026, 11, 1)),
    )


@pytest.mark.parametrize(
    ("keep_title", "hide_title"),
    [
        # Constructed: a short generic title nearly contained in a longer unrelated one,
        # same (month-end) deadline. Overlap ~0.9 but Jaccard ~0.5.
        ("2026년 멘토링 프로그램", "[부산] 2026년 해양 멘토링 프로그램 참여기업 모집 공고"),
        ("2026년 수출바우처", "[전남] 2026년 농식품 수출바우처 지원사업 공고"),
    ],
)
def test_same_deadline_alone_does_not_make_a_short_title_a_duplicate(keep_title, hide_title):
    end = date(2026, 10, 31)
    assert not _same(_p(hide_title, end), _p(keep_title, end))


def test_generic_title_in_different_regions_is_not_the_same_program():
    # Constructed, per the review: one Seoul incubator vs a 대전 posting, same wording.
    seoul = ProgramTitle("ks", "2026년 창업보육센터 입주기업 모집", None, "서울")
    daejeon = ProgramTitle("bz", "[대전] 2026년 창업보육센터 입주기업 모집 공고", None, "대전")
    nationwide = ProgramTitle("ks2", "2026년 창업보육센터 입주기업 모집", None, "전국")
    metro = ProgramTitle(
        "bz2", "[서울ㆍ인천ㆍ경기] 2026년 창업보육센터 입주기업 모집 공고", None, "서울·인천·경기"
    )

    assert not _same(daejeon, seoul)
    # 전국 is K-Startup's default, also on local incubators' rows - it can't vouch for 대전.
    assert not _same(daejeon, nationwide)
    assert not _same(nationwide, daejeon)
    assert _same(metro, seoul)  # overlapping regions


@pytest.mark.parametrize(
    ("bizinfo_region", "kstartup_region"),
    # Every combination in the 17 true pairs of 2026-10-07: 11 x (untagged, 전국),
    # 5 x (서울, 서울), 1 x (경기, 경기).
    [(None, "전국"), ("서울", "서울"), ("경기", "경기")],
)
def test_region_combinations_of_the_measured_true_pairs_still_match(
    bizinfo_region, kstartup_region
):
    bizinfo = ProgramTitle("bz", "2026년 창업보육센터 입주기업 모집 공고", None, bizinfo_region)
    kstartup = ProgramTitle("ks", "2026년 창업보육센터 입주기업 모집", None, kstartup_region)

    assert _same(bizinfo, kstartup)


def test_numbers_written_differently_still_compare_equal():
    a = _p("2026년 1,000만원 지원 창업 프로그램", None)
    b = _p("2026년 1000만원 지원 창업 프로그램 모집 공고", None)
    c = _p("'26년 1000만원 지원 창업 프로그램 모집 공고", None)
    assert _same(a, b)
    assert a.numbers == c.numbers == frozenset({"2026", "1000"})


def test_full_width_apostrophe_year_is_unified_too():
    assert _p("＇26년 1차 창업 지원", None).numbers == frozenset({"2026", "1"})


def test_gwangju_and_jeonnam_are_different_regions():
    gwangju = ProgramTitle("bz", "[광주] 2026년 창업보육센터 입주기업 모집 공고", None, "광주")
    jeonnam = ProgramTitle("ks", "2026년 창업보육센터 입주기업 모집", None, "전남")
    merged = ProgramTitle("ks2", "2026년 창업보육센터 입주기업 모집", None, "전남광주")

    assert not _same(gwangju, jeonnam)
    assert _same(gwangju, merged)  # the merged 전남광주 covers 광주


KS = ProgramTitle(
    "ks-1",
    "2026년 서울창업센터 관악 X SK에코플랜트 오픈이노베이션 프로그램 참여기업 모집",
    date(2026, 10, 11),
)
BZ = ProgramTitle(
    "bz-1",
    "[서울] 2026년 서울창업센터 관악 × SK에코플랜트 오픈이노베이션 참여기업 모집 공고",
    date(2026, 10, 11),
)


def test_new_pair_is_marked():
    assert plan_duplicate_marks([KS], [BZ], [], {"bz-1": None}) == {"bz-1": "ks-1"}


def test_mark_survives_the_original_closing():
    # KS is no longer open (not in keep); BZ may or may not be open itself.
    assert plan_duplicate_marks([], [BZ], [(BZ, KS)], {"bz-1": "ks-1"}) == {}
    assert plan_duplicate_marks([], [], [(BZ, KS)], {"bz-1": "ks-1"}) == {}


def test_mark_is_cleared_once_the_rule_no_longer_matches():
    other = ProgramTitle("ks-9", "2026년 전혀 다른 지원사업", None)
    assert plan_duplicate_marks([], [BZ], [(BZ, other)], {"bz-1": "ks-9"}) == {"bz-1": None}


def test_mark_moves_only_to_a_strictly_better_original():
    # Scores against BZ (overlap, Jaccard): KS (0.94, 0.77); `weaker` (0.81, 0.66);
    # `better` (0.96, 0.76).
    end = date(2026, 10, 11)
    weaker = ProgramTitle(
        "ks-2", "2026년 서울창업센터 관악 SK 오픈이노베이션 프로그램 참여기업 모집", end
    )
    better = ProgramTitle("ks-3", "2026년 관악 SK에코플랜트 오픈이노베이션 참여기업 모집", end)

    # Marked to KS, which has closed (not among the open originals): a weaker open match
    # doesn't take the mark over.
    assert plan_duplicate_marks([weaker], [BZ], [(BZ, KS)], {"bz-1": "ks-1"}) == {}
    # A better one does.
    assert plan_duplicate_marks([better], [BZ], [(BZ, KS)], {"bz-1": "ks-1"}) == {"bz-1": "ks-3"}


def test_copy_with_an_unreadable_tag_is_never_hidden():
    # "[경기 성남]" isn't a region we can read; without its tag the title would compare as
    # region-less and pair with a 전국 incubator posting from anywhere.
    copy = ProgramTitle("bz-9", "[경기 성남] 2026년 창업보육센터 입주기업 모집 공고", None)
    nationwide = ProgramTitle("ks-9", "2026년 창업보육센터 입주기업 모집", None, "전국")

    assert find_duplicates([nationwide], [copy]) == {}
    assert plan_duplicate_marks([], [copy], [(copy, nationwide)], {"bz-9": "ks-9"}) == {
        "bz-9": None
    }
    # K-Startup's own organization tags stay fine on the kept side (a real pair, SAME).
    end = date(2026, 10, 28)
    tagged_original = ProgramTitle(
        "ks-1", "[한국도로공사] 2026년 상생형 창업, 벤처기업 지원사업", end
    )
    plain_copy = ProgramTitle(
        "bz-1", "2026년 한국도로공사 상생형 창업ㆍ벤처기업 지원사업 모집 공고", end
    )
    assert find_duplicates([tagged_original], [plain_copy]) == {"bz-1": "ks-1"}


def test_unreadable_region_on_the_kept_side_blocks_a_regionless_copy():
    original = ProgramTitle("ks-9", "2026년 창업보육센터 입주기업 모집", None, "성남")
    copy = ProgramTitle("bz-9", "2026년 창업보육센터 입주기업 모집 공고", None)

    assert not _same(copy, original)
