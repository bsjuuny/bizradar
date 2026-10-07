"""IT rule for support programs. The parametrized titles are real 2026-10-07 postings
(K-Startup or 기업마당), read by hand when the keyword list was chosen - see the module
docstring of worker/ai/support_it_filter.py. The single-purpose tests at the bottom
(ministry name, word boundaries, entities) use constructed titles."""

import pytest

from worker.ai.support_it_filter import is_it_related


@pytest.mark.parametrize(
    "title",
    [
        "[충북] 2026년 SW제품 경쟁력 강화 지원사업 모집 공고",
        "2026년 소프트웨어 지식재산권(IP) 평가보증 지원사업 공고",
        "[대전ㆍ충청] 2026년 중소기업 AI훈련확산 지원사업 참여기업 모집 공고",
        "[광주] 인공지능 유치기업 보조금 지원사업 모집 공고",
        "2026년 데이터 품질인증 지원사업 공고",
        "2026년 SaaS 전환지원센터xAWS SaaS 현대화 교육 4회차 참가자 모집 공고",
        "[경북] 정보보호 스타트업 육성사업 참여기업 모집 공고",
        "[경남] 동남형 사이버 복원 패키지 사업 수요기업 모집 공고",
        "2026년 인천 블록체인 바우처 지원사업 수요기업 모집 공고",
        "2026년 3차 ICT 비즈니스 파트너십(중동) 참가기업 모집 공고",
        "2026년 DXㆍAX 컨설팅 지원사업 모집 공고",
        "[경남] 2026년 스마트공장 컨설팅 지원사업 참여기업 추가모집 공고",
        "스마트 공장 수준 확인(2026년 스마트 제조혁신 지원사업 통합 공고)",
        "[전북] 2026년 게임기업 컨설팅 지원사업 신청 게임기업(예비창업자) 모집 공고",
        "2026년 부산 핀테크허브 입주기업 모집공고",
        # Recovered by reading the non-matches: IT programs named without obvious words.
        "2026년 3차 디지털혁신기술국제공동연구사업 신규지원 대상과제 공고",
        "[충남] 2026년 디지털품질역량강화사업 크라우드 테스팅 희망기업 모집 공고",
        "[강원] 2026년 지역 디지털 품질역량강화사업 컨설팅 및 테스팅 지원사업 모집 공고",
        "[부산] 2026년 가명정보활용지원센터 컨설팅 지원사업 모집 공고",
        "2026년 위치정보 맞춤형 컨설팅 참여기업 모집 공고",
        "2026년 전자문서 유공 포상 계획 연장 공고",
        "AIoT융합부품 성능검증시스템 고도화사업 수혜기업모집 수시 공고",
        "ETRI 기술활용 신사업 모델 공모전",
        "[온라인] chatGPT로 만드는 내 퍼스널 브랜딩 플랫폼 만들기 | 바이브코딩 실전 클래스",
        # The trailing parenthetical names an IT-industry program, so it is kept.
        "[충남] 2027년 지역선도기업사업화지원 공고(지역디지털기업성장지원사업)",
        # A trailing field marker (not a funding project) counts.
        "「제24차 세계한상대회 스타트업 경연대회-시애틀 진출 연계」 참여기업 모집 공고(AI 분야)",
        "2026년 초기창업패키지 로켓십 IR 경진대회 참가기업 모집 (1회차: AI·빅데이터)",
        # Stored HTML-escaped by K-Startup before the decoding fix.
        "2026 경기AI기업 글로벌 공동연구ㆍ해외진출 예비참여기업 공개모집",
    ],
)
def test_it_programs(title):
    assert is_it_related(title)


@pytest.mark.parametrize(
    "title",
    [
        # IoT / 사물인터넷: environmental-emission sensors for small workplaces.
        "[강원] 홍천군 2026년 사물인터넷(IoT) 측정기기 부착 지원사업 공고",
        "[충북] 충주시 2026년 3차 소규모 사업장 방지시설(사물인터넷 측정기기) 설치 지원사업 공고",
        # "전산" as a substring of 안전산업 / 가전산업.
        "[울산] 2026년 재난안전산업 육성지원사업 기업지원(대한민국 안전산업 박람회(BEXCO)) "
        "상시모집 공고",
        "[광주] 2026년 융ㆍ복합 가전산업 고용 안착 활성화 지원 사업 참여기업(참여자) 모집 공고",
        # 데이터홈쇼핑 is a TV shopping channel.
        "2026년 TV홈쇼핑 및 데이터홈쇼핑 입점지원사업 소상공인 모집 공고",
        # 소상공인 online sales channels.
        "2026년 2차 해외 온라인 플랫폼 입점지원 사업 참여 소상공인 모집 공고",
        "2026년 디지털커머스 전문기관(소담스퀘어 in 광주) 모집 공고",
        "2026년 찾아가는 1:1 디지털 교육 소상공인 모집 공고",
        "[경기] 부천시 2026년 공공배달앱 배달특급 개별 가맹점 홍보물 제작 지원 공고",
        # Hardware / manufacturing.
        "2026년 로봇 재제조산업 기업지원사업(기술 자문) 공고",
        "2026년 자동차용 반도체 기능안전ㆍ신뢰성 산업혁신기반구축사업 기업지원 모집 공고",
        # IT-sounding funding project only in the trailing parenthetical.
        "[경남] 창원시 2026년 2차 의료기기 부품ㆍ모듈 국산화 및 기술개발 지원사업 "
        "공고(AI 빅데이터 기반 의료바이오 첨단기기 연구제조센터 구축사업)",
        # Trade-secret protection, not infosec.
        "[경기] 2026년 기술보호 전문교육 및 산업보안 컨설팅 지원 참여기업(기관) 모집 공고",
        # Plain 소상공인/general support.
        "2026년 중소벤처기업부 소상공인 정책자금 융자사업 5차 변경 공고",
        "2026년 디캠프 배치 9기 모집 공고",
    ],
)
def test_non_it_programs(title):
    assert not is_it_related(title)


def test_ministry_name_alone_does_not_make_it_it():
    assert not is_it_related("과학기술정보통신부 2026년 바이오 소재 실증 지원사업 공고")
    # ...but the program's own IT word still counts.
    assert is_it_related(
        "[부산] 2026년 블록체인 기업 글로벌(싱가포르) 사업화 지원사업 참가기업 추가모집 "
        "공고(과학기술정보통신부 블록체인 특화 클러스터 조성사업)"
    )


def test_latin_keywords_need_word_boundaries():
    assert not is_it_related("MAIN STREET 상권 활성화 지원사업")
    assert not is_it_related("SAINT 프로그램 참가자 모집")
    assert is_it_related("AI 올라운더(기획,개발,마케팅) 창업가육성과정 8기 모집")


def test_game_changer_buzzword_is_not_the_game_industry():
    assert not is_it_related("2026년 지역 게임체인저 기업 육성사업 공고")
    assert not is_it_related("미래 게임 체인저 스타트업 모집")


def test_html_entities_are_decoded_before_matching():
    assert is_it_related("2026년 &apos;AI 바우처&apos; 공급기업 모집")
