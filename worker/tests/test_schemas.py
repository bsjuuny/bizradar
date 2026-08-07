from worker.ai.schemas import ProjectExtraction


def test_deduplicates_repeated_list_entries_preserving_order():
    # Real failure mode from a live run: a local model repeated the same certification
    # name up to the schema's maxItems cap - see docs/DATA_PIPELINE.md.
    extraction = ProjectExtraction(
        project_type="AI_ML",
        summary="요약",
        required_qualifications=["SW사업자 등록", "정보보호관리체계 인증", "정보보호관리체계 인증"],
        requirements=["A", "B", "A"],
        risks=["위험1", "위험1", "위험2"],
        required_roles=["백엔드", "백엔드"],
    )

    assert extraction.required_qualifications == ["SW사업자 등록", "정보보호관리체계 인증"]
    assert extraction.requirements == ["A", "B"]
    assert extraction.risks == ["위험1", "위험2"]
    assert extraction.required_roles == ["백엔드"]


def test_leaves_already_unique_lists_unchanged():
    extraction = ProjectExtraction(
        project_type="OTHER",
        summary="",
        required_qualifications=["A", "B", "C"],
    )
    assert extraction.required_qualifications == ["A", "B", "C"]
