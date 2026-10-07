from datetime import UTC, date, datetime

import pytest

from worker.collectors.base import RawRecord
from worker.collectors.bizinfo import BizInfoCollector
from worker.collectors.kstartup import KStartupCollector
from worker.config import Settings
from worker.jobs import support_reclassify
from worker.repositories.support_programs import DERIVED_COLUMNS


def _kstartup_row(**overrides):
    # Stored columns as the pre-fix collector wrote them for pbanc_sn 178949: entities left
    # in, it_related at the migration's default.
    row = {
        "id": "ks-1",
        "external_id": "178949",
        "title": "2026 경기AI기업 글로벌 공동연구ㆍ해외진출 예비참여기업 공개모집",
        "organization": "차세대융합기술연구원",
        "department": None,
        "supervising_type": None,
        "category": "기술개발(R&amp;D)",
        "region": None,
        "target": None,
        "description": None,
        "investment_linked": False,
        "it_related": False,
        "source_url": None,
        "raw_payload": {
            "biz_pbanc_nm": "2026 경기AI기업 글로벌 공동연구ㆍ해외진출 예비참여기업 공개모집",
            "pbanc_ntrp_nm": "차세대융합기술연구원",
            "supt_biz_clsfc": "기술개발(R&amp;D)",
        },
    }
    row.update(overrides)
    return row


def _bizinfo_payload(row_id, title):
    return {
        "pblancId": row_id,
        "pblancNm": title,
        "pblancUrl": f"https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId={row_id}",
        "jrsdInsttNm": "중소벤처기업부",
        "excInsttNm": "직접수행",
        "reqstBeginEndDe": "예산 소진시까지",
    }


def _current_hash(row_id, title):
    """content_hash the current collector computes for the payload."""
    collector = BizInfoCollector(settings=Settings(_env_file=None), today=date(2026, 10, 7))
    raw = RawRecord(
        source="bizinfo",
        external_id=row_id,
        fetched_at=datetime.now(UTC),
        payload=_bizinfo_payload(row_id, title),
    )
    return collector.normalize(raw).content_hash


def _bizinfo_row(row_id, payload_title, stale=False, **stored):
    """A 기업마당 row whose stored columns match what the current collector derives from
    its payload, except for the overrides in `stored`. A `stale` row was written by an older
    collector, so its content_hash (which covers the derived columns) is old too."""
    payload = _bizinfo_payload(row_id, payload_title)
    url = payload["pblancUrl"]
    row = {
        "id": row_id,
        "external_id": row_id,
        "title": payload_title,
        "organization": "중소벤처기업부",
        "department": "중소벤처기업부",
        "category": None,
        "region": None,
        "target": None,
        "description": None,
        "investment_linked": False,
        "it_related": False,
        "source_url": url,
        "application_period_text": "예산 소진시까지",
        "content_hash": "hash-from-an-older-collector"
        if stale
        else _current_hash(row_id, payload_title),
        "raw_payload": payload,
    }
    row.update(stored)
    return row


class FakeRepo:
    DERIVED_COLUMNS = DERIVED_COLUMNS

    def __init__(self, kstartup, bizinfo):
        self.rows = {"kstartup": kstartup, "bizinfo": bizinfo}
        self.updates = []
        self.requests = []

    def fetch_programs_for_reclassify(self, source):
        return self.rows[source]

    def update_programs(self, row_ids, changes):
        self.requests.append((list(row_ids), dict(changes)))
        self.updates.extend((row_id, dict(changes)) for row_id in row_ids)


@pytest.fixture
def repo(monkeypatch):
    fake = FakeRepo(
        kstartup=[_kstartup_row()],
        bizinfo=[
            # Stored before the IT rule existed: it_related (and so the hash) is stale.
            _bizinfo_row(
                "bz-1", "2026년 인천 블록체인 바우처 지원사업 수요기업 모집 공고", stale=True
            ),
            _bizinfo_row("bz-2", "2026년 소상공인 온라인판로 지원사업 참여기업 모집공고"),
            _bizinfo_row("bz-3", "2026년 데이터 품질인증 지원사업 공고", it_related=True),
            # A closed posting the collector will never re-send: stale investment flag
            # (데모데이 is an investment keyword) and a title the first collector version
            # stored with a double space.
            _bizinfo_row(
                "bz-4",
                "[경기] 부천시 2026년 스타트업포럼(IR데모데이) 참가기업 모집 공고",
                stale=True,
                title="[경기] 부천시  2026년 스타트업포럼(IR데모데이) 참가기업 모집 공고",
                region="경기",
            ),
        ],
    )
    settings = Settings(_env_file=None)
    monkeypatch.setattr(support_reclassify, "support_programs", fake)
    monkeypatch.setattr(
        support_reclassify, "KStartupCollector", lambda: KStartupCollector(settings=settings)
    )
    monkeypatch.setattr(
        support_reclassify,
        "BizInfoCollector",
        lambda: BizInfoCollector(settings=settings, today=date(2026, 10, 7)),
    )
    return fake


def test_writes_only_changed_columns_of_changed_rows(repo):
    result = support_reclassify.run()

    bz4_title = "[경기] 부천시 2026년 스타트업포럼(IR데모데이) 참가기업 모집 공고"
    assert repo.updates == [
        ("ks-1", {"category": "기술개발(R&D)", "it_related": True}),
        # The hash is rewritten with the columns it covers, so the next hourly BizInfo run
        # doesn't see a mismatch and re-send the row.
        (
            "bz-1",
            {
                "it_related": True,
                "content_hash": _current_hash(
                    "bz-1", "2026년 인천 블록체인 바우처 지원사업 수요기업 모집 공고"
                ),
            },
        ),
        (
            "bz-4",
            {
                "title": bz4_title,
                "investment_linked": True,
                "content_hash": _current_hash("bz-4", bz4_title),
            },
        ),
    ]
    assert result == {
        "rows": 3,
        "category": 1,
        "it_related": 2,
        "title": 1,
        "investment_linked": 1,
        "content_hash": 2,
    }


def test_never_touches_recruiting_or_duplicate_of(repo):
    # Both depend on when a row was collected and on the closing/dedupe passes, not on the
    # payload. (Dates are re-derived: test_dates_are_re_derived_and_compared_as_instants.)
    for rows in repo.rows.values():
        for row in rows:
            row.update(recruiting=False, duplicate_of="some-original")

    support_reclassify.run()

    touched = {column for _, changes in repo.updates for column in changes}
    assert not {"recruiting", "duplicate_of"} & touched


def test_rows_needing_the_same_change_share_one_request(monkeypatch):
    # The usual shape after a rule change: many rows differ by the same value.
    rows = [_kstartup_row(), _kstartup_row(id="ks-2", external_id="178950")]
    fake = FakeRepo(kstartup=rows, bizinfo=[])
    settings = Settings(_env_file=None)
    monkeypatch.setattr(support_reclassify, "support_programs", fake)
    monkeypatch.setattr(
        support_reclassify, "KStartupCollector", lambda: KStartupCollector(settings=settings)
    )

    support_reclassify.run()

    assert fake.requests == [
        (["ks-1", "ks-2"], {"category": "기술개발(R&D)", "it_related": True}),
    ]


def test_dry_run_writes_nothing(repo):
    result = support_reclassify.run(dry_run=True)

    assert repo.updates == []
    assert result["rows"] == 3


def test_second_run_is_a_no_op(repo):
    support_reclassify.run()
    for row_id, changes in repo.updates:
        for source_rows in repo.rows.values():
            for row in source_rows:
                if row["id"] == row_id:
                    row.update(changes)
    repo.updates.clear()

    assert support_reclassify.run() == {}
    assert repo.updates == []


def test_dates_are_re_derived_and_compared_as_instants(monkeypatch):
    # bz-5: stored before its 신청기간 form was readable - dates NULL. bz-6: dates already
    # right, stored as PostgREST returns them (strings) - must count as unchanged.
    payload = _bizinfo_payload("bz-5", "2026년 SW 지원사업 공고")
    payload["reqstBeginEndDe"] = "2026. 10. 2.(목) 09:00 ~ 10. 16.(목) 18:00"
    unreadable_before = _bizinfo_row("bz-5", "2026년 SW 지원사업 공고", stale=True)
    unreadable_before.update(
        raw_payload=payload,
        application_period_text=payload["reqstBeginEndDe"],
        it_related=True,
        application_start=None,
        application_end=None,
    )
    already_right = _bizinfo_row("bz-6", "2026년 데이터 품질인증 지원사업 공고", it_related=True)
    fake = FakeRepo(kstartup=[], bizinfo=[unreadable_before, already_right])
    settings = Settings(_env_file=None)
    monkeypatch.setattr(support_reclassify, "support_programs", fake)
    monkeypatch.setattr(
        support_reclassify, "KStartupCollector", lambda: KStartupCollector(settings=settings)
    )
    monkeypatch.setattr(
        support_reclassify,
        "BizInfoCollector",
        lambda: BizInfoCollector(settings=settings, today=date(2026, 10, 7)),
    )

    support_reclassify.run()

    assert [row_id for row_id, _ in fake.updates] == ["bz-5"]
    changes = fake.updates[0][1]
    assert changes["application_start"] == "2026-10-02T00:00:00+00:00"
    assert changes["application_end"] == "2026-10-16T00:00:00+00:00"

    # Once stored (as PostgREST strings), a second run sees nothing to do.
    unreadable_before.update(changes)
    fake.updates.clear()
    assert support_reclassify.run() == {}
