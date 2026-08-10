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


def test_public_perception_survey_about_ai_is_not_likely_it():
    # Real live example (user-reported, id f18403b6): "AI" here names the survey's
    # *topic*, not a system being built - the notice is a 대국민 인식조사 (public
    # perception survey) academic research service, unrelated to IT development.
    title = "AI·디지털 사회 대국민 인식조사"
    assert classify(title) == "UNKNOWN"


def test_gis_database_construction_is_likely_it():
    # Real live examples: GIS DB construction for sewage/water infrastructure is a
    # genuine IT/geospatial-systems deliverable, previously missed entirely since "GIS"
    # wasn't in the keyword list.
    titles = [
        "창평처리분구 하수관로 정비사업 GIS DB 구축용역(입찰대행)",
        "서초구 노후불량 하수관로 정비공사 GIS DB 구축 용역",
    ]
    for title in titles:
        assert classify(title) == "LIKELY_IT", title


def test_gist_and_dgist_university_names_are_not_likely_it_via_gis():
    # "GIST"/"DGIST" (두 과학기술원 이름) contain "GIS" as a substring, which would
    # otherwise false-positive now that "GIS" is a keyword. Confirmed live: neither
    # title is about geographic information systems.
    assert classify("2026년도 GIST 딥데크 창업도약(Scale-up) 투자연계 프로그램") == "UNKNOWN"
    assert classify("DGIST 산업AX혁신허브 조성사업 설계 용역") == "UNKNOWN"


def test_information_protection_consulting_is_likely_it():
    # Real live examples: "정보보호" (information protection) consulting/certification
    # work is a distinct term from "보안" and was previously missed.
    titles = [
        "KERIS 정보보호 및 개인정보보호 관리체계(ISMS-P) 인증 사전 컨설팅",
        "2026년 정보보호 취약점 진단 용역",
    ]
    for title in titles:
        assert classify(title) == "LIKELY_IT", title


def test_bundled_building_security_and_cleaning_is_not_likely_it():
    # Real live example (id found while auditing the "보안" keyword): "트라이보울 보안 및
    # 미화 용역" - 트라이보울 is a cultural-complex building in Songdo; "보안" here means
    # a physical security guard, bundled with cleaning ("미화"), not information security.
    title = "트라이보울 보안 및 미화 용역"
    assert classify(title) == "UNKNOWN"


def test_policy_or_collaboration_alliances_named_network_are_not_likely_it():
    # Real live examples: Korean formal titles commonly use "네트워크" for a policy or
    # industry-academia *alliance*, not a computer network - found while auditing the
    # "네트워크" keyword against all 428 LIKELY_IT titles in the live dataset.
    titles = [
        "｢세계인문도시네트워크(WHCN) 총회｣ 운영 용역 입찰공고",
        "참여기업 발굴 및 산학협력 네트워크 확대 용역",
        "기후변화 대응 산학연 네트워크 구축 및 운영을 통한 정책 발굴 연구",
    ]
    for title in titles:
        assert classify(title) == "UNKNOWN", title


def test_genuine_computer_network_titles_stay_likely_it():
    # Guards against the "네트워크" exceptions above being made too broad.
    titles = [
        "네트워크 보안 시뮬레이션 환경 구축 및 공격 시나리오 생성 도구 개발",
        "정보시스템 이전 및 네트워크 인프라 환경 구축",
    ]
    for title in titles:
        assert classify(title) == "LIKELY_IT", title
