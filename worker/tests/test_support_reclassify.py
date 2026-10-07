import pytest

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
        "raw_payload": {
            "biz_pbanc_nm": "2026 경기AI기업 글로벌 공동연구ㆍ해외진출 예비참여기업 공개모집",
            "pbanc_ntrp_nm": "차세대융합기술연구원",
            "supt_biz_clsfc": "기술개발(R&amp;D)",
        },
    }
    row.update(overrides)
    return row


def _bizinfo_row(row_id, title, it_related=False, investment_linked=False):
    return {
        "id": row_id,
        "title": title,
        "description": None,
        "it_related": it_related,
        "investment_linked": investment_linked,
    }


class FakeRepo:
    DERIVED_COLUMNS = DERIVED_COLUMNS

    def __init__(self, kstartup, bizinfo):
        self.rows = {"kstartup": kstartup, "bizinfo": bizinfo}
        self.updates = []

    def fetch_programs_for_reclassify(self, source):
        return self.rows[source]

    def update_program(self, row_id, changes):
        self.updates.append((row_id, dict(changes)))


@pytest.fixture
def repo(monkeypatch):
    fake = FakeRepo(
        kstartup=[_kstartup_row()],
        bizinfo=[
            _bizinfo_row("bz-1", "2026년 인천 블록체인 바우처 지원사업 수요기업 모집 공고"),
            _bizinfo_row("bz-2", "2026년 소상공인 온라인판로 지원사업 참여기업 모집공고"),
            _bizinfo_row("bz-3", "2026년 데이터 품질인증 지원사업 공고", it_related=True),
            # A closed posting the collector will never re-send: its investment flag is
            # stale (데모데이 is an investment keyword) and only reclassify can fix it.
            _bizinfo_row(
                "bz-4", "[경기] 부천시 2026년 스타트업포럼(IR데모데이) 참가기업 모집 공고"
            ),
        ],
    )
    monkeypatch.setattr(support_reclassify, "support_programs", fake)
    return fake


def test_writes_only_changed_columns_of_changed_rows(repo):
    result = support_reclassify.run()

    assert repo.updates == [
        ("ks-1", {"category": "기술개발(R&D)", "it_related": True}),
        ("bz-1", {"it_related": True}),
        ("bz-4", {"investment_linked": True}),
    ]
    assert result == {"rows": 3, "category": 1, "it_related": 2, "investment_linked": 1}


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
