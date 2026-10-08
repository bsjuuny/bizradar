from worker.collectors.bizinfo import title_tag_region
from worker.regions import (
    ALIASES,
    GROUPS,
    NON_SPECIFIC,
    PROVINCES,
    REGION_WORDS,
    covered_provinces,
    has_unreadable_tag,
)


def test_every_region_word_the_collector_accepts_is_known_to_the_dedupe_guard():
    # A word title_tag_region accepts but covered_provinces doesn't know would silently turn
    # the region guard off for those rows. One vocabulary keeps them in step.
    for word in REGION_WORDS:
        assert title_tag_region(f"[{word}] 공고") == word
        assert covered_provinces(word) or word in NON_SPECIFIC


def test_groups_only_cover_provinces():
    for covered in GROUPS.values():
        assert covered <= PROVINCES


def test_gwangju_and_jeonnam_do_not_overlap_but_the_merged_label_covers_both():
    assert not covered_provinces("광주") & covered_provinces("전남")
    assert covered_provinces("전남광주") >= {"광주", "전남"}
    assert covered_provinces("전국") == frozenset()


def test_unknown_words_are_not_read_as_nationwide():
    # Next to a known 시·도: a place inside it.
    assert covered_provinces("경기 성남") == frozenset({"경기"})
    assert covered_provinces("경기도 성남시") == frozenset({"경기"})
    # On their own: specific but unreadable - overlaps only the same value.
    assert covered_provinces("성남") == frozenset({"?성남"})
    assert not covered_provinces("성남") & covered_provinces("부산")
    # Still nothing specific.
    assert covered_provinces("전국") == frozenset()
    assert covered_provinces(None) == frozenset()


def test_official_long_forms_read_as_the_short_word():
    assert title_tag_region("[부산광역시] 2026년 창업보육센터 입주기업 모집 공고") == "부산"
    assert title_tag_region("[서울특별시ㆍ경기도] ...") == "서울·경기"
    for alias, word in ALIASES.items():
        assert word in PROVINCES, alias


def test_unreadable_tag_is_told_apart_from_no_tag():
    assert has_unreadable_tag("[경기 성남] 2026년 창업 지원 공고")
    assert has_unreadable_tag("[한국도로공사] 2026년 상생형 창업, 벤처기업 지원사업")
    assert not has_unreadable_tag("[부산] 2026년 창업 지원 공고")
    assert not has_unreadable_tag("2026년 창업 지원 공고")
