from worker.collectors.bizinfo import parse_region
from worker.regions import GROUPS, NON_SPECIFIC, PROVINCES, REGION_WORDS, covered_provinces


def test_every_region_word_the_collector_accepts_is_known_to_the_dedupe_guard():
    # A word parse_region accepts but covered_provinces doesn't know would silently turn
    # the region guard off for those rows. One vocabulary keeps them in step.
    for word in REGION_WORDS:
        assert parse_region(f"[{word}] 공고") == word
        assert covered_provinces(word) or word in NON_SPECIFIC


def test_groups_only_cover_provinces():
    for covered in GROUPS.values():
        assert covered <= PROVINCES


def test_gwangju_and_jeonnam_do_not_overlap_but_the_merged_label_covers_both():
    assert not covered_provinces("광주") & covered_provinces("전남")
    assert covered_provinces("전남광주") >= {"광주", "전남"}
    assert covered_provinces("전국") == frozenset()
    assert covered_provinces("[unknown]") == frozenset()
