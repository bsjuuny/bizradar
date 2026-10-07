"""Cross-source duplicate rule. Every title pair below is real: K-Startup titles from the
support_programs table, 기업마당 titles from the public list page, both 2026-10-07 - the
same data the thresholds were chosen on (see worker/dedupe/support_programs.py)."""

from datetime import date

import pytest

from worker.dedupe.support_programs import (
    ProgramTitle,
    find_duplicates,
    match_score,
    normalize_title,
    plan_updates,
)


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
    assert _same(daejeon, nationwide)  # 전국 says nothing specific
    assert _same(metro, seoul)  # overlapping regions


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
