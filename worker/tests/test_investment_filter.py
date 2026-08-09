from worker.ai.investment_filter import is_investment_linked


def test_tips_program_is_investment_linked():
    assert is_investment_linked("2026년 웰컴 투 팁스 1차 참가기업 모집 (충청권)") is True


def test_angel_investment_pitching_room_is_investment_linked():
    assert is_investment_linked("2026-10회 호남권 엔젤투자 피칭룸 in 제주") is True


def test_keyword_in_description_counts_too():
    # Real live example: the title alone has no investment keyword, but the
    # description explicitly describes 투자유치 support - found while validating this
    # filter against 100 real collected announcements.
    title = "2026 지역창업 페스티벌 연계 제106회 대전창업포럼(AI・로봇) 참가 모집"
    description = "AI・로봇 분야 유망 스타트업의 투자유치 및 사업화 연계를 지원하기 위하여..."
    assert is_investment_linked(title) is False
    assert is_investment_linked(title, description) is True


def test_plain_networking_event_is_not_investment_linked():
    assert is_investment_linked("2026년 창업진흥원 대전 스타트업스쿨 네트워킹 데이") is False


def test_no_description_defaults_safely():
    assert is_investment_linked("일반 창업교육 프로그램 모집", None) is False
