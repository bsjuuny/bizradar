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


def test_ai_tower_building_name_is_not_likely_it():
    # Real live example (found while browsing 3,634 real collected rows): "AI타워" is a
    # building name at a 한국해양과학기술원-adjacent site, not a reference to AI
    # technology - the notice is a waste-disposal service for its construction. This is
    # an explicit, narrow exception (see rule_filter.py's module docstring for why a
    # general "AI" word-boundary rule was tried and reverted - it broke more real AI
    # titles than it fixed).
    title = "AI타워ㆍ지하주차장 신축공사 폐기물처리용역"
    assert classify(title) == "UNKNOWN"


def test_ai_fused_to_hangul_is_still_likely_it_when_genuinely_about_ai():
    # These all fuse "AI" directly onto surrounding Hangul with no space, exactly like
    # "AI타워" does - but unlike "AI타워", they're genuinely about AI technology. A
    # general word-boundary rule for "AI" would have wrongly demoted all of these (it was
    # tested against real data and reverted for exactly this reason).
    titles = [
        "2026년 의료AI 보건의료인 직무교육사업",
        "초거대 제조AI 서비스 개발·실증사업 관제센터 구축공사",
        "비전AI 기반 지능형 문화관람 서비스 시범 구축 사업",
        "미래 AI반도체 기술개발 로드맵 수립 연구",
    ]
    for title in titles:
        assert classify(title) == "LIKELY_IT", title


def test_aided_program_brand_name_is_not_likely_it():
    # Real live example (user-reported): "AIDed" is a childcare/education-center program
    # brand name in Yeoncheon-gun ("에이드"), not AI technology - the notice is a school
    # shuttle rental service. A general "AI not fused to another Latin letter" rule would
    # also catch this, but was rejected the same way as the Hangul-fusion rule: tested
    # against the real dataset, it also flips "AIDC" (a real "AI Data Center" term) to
    # non-IT - see rule_filter.py's module docstring.
    title = "2026 연천 AIDed[에이드] 온동네돌봄・교육센터 제2권역[전곡초] 통학차량 임차용역"
    assert classify(title) == "UNKNOWN"


def test_aidc_stays_likely_it_despite_looking_similar_to_aided():
    # The real title that made a general Latin-boundary rule unsafe: "AIDC" = "AI Data
    # Center", a genuine industry term, not a false positive like "AIDed" above.
    title = "온프레미스 AIDC 표준 모듈 개발 및 보급 기획 연구"
    assert classify(title) == "LIKELY_IT"
