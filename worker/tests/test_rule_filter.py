from worker.ai.rule_filter import classify


def test_likely_it_smart_city_autonomous_driving():
    title = "[수의시담] 2026년 횡성군 스마트시티 자율주행 시범운행 운영 용역"
    assert classify(title) == "LIKELY_IT"


def test_likely_it_cryptography_project_missed_by_official_classification():
    # Real example: data.go.kr's own pubPrcrmntLrgClsfcNm tagged this "학술연구 및
    # 기타 서비스 용역" (research/other), not ICT - the keyword filter catches it anyway.
    title = "양자내성암호 시범전환 사업 공인시험 위탁"
    assert classify(title) == "LIKELY_IT"


def test_non_it_school_trip():
    title = "2026학년도 명덕여자중학교 3학년 소규모테마형교육여행 위탁용역"
    assert classify(title) == "NON_IT"


def test_non_it_field_trip_with_parenthetical():
    title = (
        "2026학년도 명호고등학교 2학년 현장체험학습(수학여행) 위탁용역 소액수의 견적제출 안내공고"
    )
    assert classify(title) == "NON_IT"


def test_non_it_event_execution():
    title = "2026학년도 전남대학교 용봉대동풀이 행사 진행 용역"
    assert classify(title) == "NON_IT"


def test_unknown_when_no_keyword_matches():
    assert classify("2026년 도로 포장 공사 감리 용역") == "UNKNOWN"


def test_it_keyword_wins_over_non_it_keyword():
    # A false positive here just costs one wasted AI call; a false negative drops a
    # real IT opportunity entirely - so an IT match takes priority.
    title = "학교 정보시스템 유지보수 및 급식 지원 통합 용역"
    assert classify(title) == "LIKELY_IT"


def test_empty_title_is_unknown():
    assert classify("") == "UNKNOWN"
