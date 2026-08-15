"""Rule filter: buckets a G2B title into NON_IT / LIKELY_IT / UNKNOWN before any LLM
call touches it (section 21 of the original spec - the full feed never goes to Ollama).

Biased toward inclusion on purpose: a false positive here costs one wasted ~60s Ollama
call; a false negative means a real IT opportunity never reaches a user at all, which is
the worse failure mode for a product whose whole point is "find IT projects". So an IT
keyword match wins even if a non-IT keyword also matches, and the non-IT list only
contains terms specific enough that they're essentially never IT-related (school trips,
facility cleaning, catering, ...) - not generic contract words like "유지보수" or "구축"
that show up in both IT and non-IT announcements.

Verified against every title in fixtures/g2b/bid_list_servc_sample.json (real G2B data,
not synthetic) before this shipped - see worker/tests/test_rule_filter.py.
"""

Category = str  # "NON_IT" | "LIKELY_IT" | "UNKNOWN"

_IT_KEYWORDS = [
    "시스템",
    "소프트웨어",
    "정보화",
    "플랫폼",
    "애플리케이션",
    "웹사이트",
    "웹개발",
    "홈페이지",
    "포털",
    "클라우드",
    "인공지능",
    "AI",
    "빅데이터",
    "데이터베이스",
    "네트워크",
    "보안",
    "암호",
    "전산",
    "ICT",
    "사이버",
    "자율주행",
    "스마트시티",
    "챗봇",
    "디지털전환",
    "ERP",
    "CRM",
    "블록체인",
    "메타버스",
    "IoT",
    "사물인터넷",
    "머신러닝",
    "딥러닝",
    "전자정부",
    "정보시스템",
    "앱개발",
    "모바일앱",
    "GIS",
    "정보보호",
]

# A narrow, explicit exception list - NOT a general word-boundary rule for "AI" and
# friends. That was tried and reverted: tested live against 3,634 real collected titles,
# a boundary heuristic ("AI" not fused to Hangul) fixed the one confirmed false positive
# below but also flipped ~15 genuinely AI-relevant titles to non-IT ("의료AI", "제조AI
# 서비스 개발", "비전AI 기반 지능형 문화관람 서비스 시범 구축", "Physical AI용 3D LiDAR",
# "미래 AI반도체 기술개발 로드맵", ...) - formal 공공기관 titles fuse "AI" directly onto
# real technology terms just as often as onto unrelated proper nouns, so the two cases
# aren't structurally distinguishable by boundary alone. Given false negatives are the
# worse failure mode here, only specific, confirmed non-tech phrases are excluded.
_IT_KEYWORD_EXCEPTIONS = [
    "AI타워",  # a building name at a 한국해양과학기술원-adjacent site, not AI technology -
    # confirmed live: "AI타워ㆍ지하주차장 신축공사 폐기물처리용역" is a waste-disposal
    # service for the building's construction, unrelated to AI.
    "AIDed",  # a childcare/education-center program brand name ("에이드") in
    # Yeoncheon-gun, not AI technology - confirmed live: "2026 연천 AIDed[에이드]
    # 온동네돌봄・교육센터 제2권역[전곡초] 통학차량 임차용역" is a school shuttle rental
    # service. A general "AI not fused to another Latin letter" rule was considered for
    # this one too (would also catch it) and rejected the same way as the Hangul rule
    # above: tested against the same real dataset, it also flips "AIDC" (a real "AI Data
    # Center" industry term) to non-IT.
    "AI·디지털 사회 대국민 인식조사",  # an academic 대국민 인식조사 (public perception
    # survey) research service about AI/digital society as a *topic* - not a system being
    # built. Confirmed live (id f18403b6): the title is exactly this phrase, no IT
    # deliverable involved. Kept as an exact-phrase exception rather than a general
    # "인식조사" non-IT rule since only this one confirmed case has been seen so far -
    # a survey/analysis *system* genuinely being built could plausibly also use this word.
    "GIST",  # 광주과학기술원 (Gwangju Institute of Science and Technology) and, as a
    # substring, its sister institute "DGIST" (대구경북과학기술원) - both university names
    # that happen to contain the "GIS" keyword added below. Confirmed live: "2026년도 GIST
    # 딥데크 창업도약(Scale-up) 투자연계 프로그램" is a startup investment program, and
    # "DGIST 산업AX혁신허브 조성사업 설계 용역" is a research-hub design contract - neither
    # is about geographic information systems.
    "보안 및 미화",  # a bundled building-security-guard + cleaning service, not
    # information security - confirmed live: "트라이보울 보안 및 미화 용역" (트라이보울 is a
    # cultural-complex building in Songdo) is facility management, the same category as
    # "경비용역"/"시설관리" already in the non-IT list below, just phrased with "보안"
    # instead of "경비".
    "인문도시네트워크",  # "세계인문도시네트워크(WHCN)" - a policy/cultural alliance of
    # cities, not a computer network. Confirmed live: "｢세계인문도시네트워크(WHCN) 총회｣
    # 운영 용역 입찰공고" is a conference-operations service.
    "산학협력 네트워크",  # an industry-academia collaboration alliance, not a computer
    # network - confirmed live: "참여기업 발굴 및 산학협력 네트워크 확대 용역".
    "산학연 네트워크",  # same pattern as "산학협력 네트워크" above, confirmed live in a
    # separate title: "기후변화 대응 산학연 네트워크 구축 및 운영을 통한 정책 발굴 연구".
    "정보화 화장실",  # a school-facilities naming convention for a renovated/modernized
    # restroom, not an information system - confirmed live (id 7c877ae3): "서울동의초
    # 교사동 및 정보화 화장실 개선 전기공사 재해예방기술지도용역" is a disaster-prevention
    # technical guidance service for electrical construction work, unrelated to IT.
    "자동파종 시스템",  # "시스템" fused onto a mechanical seed-sowing rig, not a computer
    # system - confirmed live: "잘피종자 신속조성용 기계식 자동파종 시스템 제작 용역(전자
    # 수의시담)" is a mechanical device for seagrass-seed propagation, unrelated to IT.
    "보안등",  # a street/security light ("가로등"과 같은 조명 설비), not information
    # security - "보안" fuses onto "등" (lamp) in routine municipal electrical/lighting
    # contracts like "가로등·보안등 교체공사", unrelated to "보안" as in infosec.
    "플랫폼스크린도어",  # a subway Platform Screen Door - physical safety barrier
    # installation/maintenance work, not a software platform. "플랫폼" here means a train
    # station platform, the everyday sense of the word, not a tech platform.
    "정보화마을",  # "정보화마을" is a fixed brand name from a 2001-era rural-development
    # program (특산물 판매·지역축제 운영 용역 등), not an information system being built -
    # "정보화" fuses onto the program's name, not a description of IT work.
    "대전산성초",  # the school name contains "전산" only across the word boundary
    # 대[전산]성초. Confirmed live (id 2f54d3ef): the notice is for supervising solar-
    # panel electrical work at three schools, not for an IT system.
    "안전산업",  # the industry term contains "전산" only across 안전 + 산업. Confirmed
    # live (id 2f780151): "안전산업박람회 전시관 설치 용역" is exhibition installation,
    # not computer work. A separate real IT keyword elsewhere in the title still wins.
    "전산편집",  # exam-paper editing/illustration services, not system development -
    # confirmed live in both teacher-employment and CSAT exam notices.
    "전산출력",  # printing, enclosing, and mailing giro forms, not an IT deliverable -
    # confirmed live (id 110baf78) with procurement category 우편발송서비스.
    "항공보안",  # physical aviation-security policy/planning, not information security -
    # confirmed live (id 5e6032e0): a five-year aviation-security master-plan study.
    "첨단보안협동조합",  # an organization name in a marketing/keyword-advertising
    # contract (id 9c9f16d6), not a cybersecurity deliverable.
    "데이터보안·활용융합분야 CO-SHOW",  # the topic/brand of an event-planning contract,
    # not implementation of data-security software (live original + re-notice pair).
    "농식품 분야 글로벌 R&D 전략 수립 및 네트워크",  # a research/collaboration network,
    # not a computer network (id 8face869, procurement category 기타연구조사서비스).
]

_NON_IT_KEYWORDS = [
    "수학여행",
    "현장체험학습",
    "체험학습",
    "교육여행",
    "수련회",
    "급식",
    "청소용역",
    "경비용역",
    "시설관리",
    "조경",
    "도서구입",
    "공연",
    "축제",
    "행사대행",
    "행사 진행",
    "인쇄용역",
    "차량임차",
    "청사관리",
    "방역",
    "보험",
]


def classify(title: str) -> Category:
    stripped = title
    for exception in _IT_KEYWORD_EXCEPTIONS:
        stripped = stripped.replace(exception, "")

    if any(keyword in stripped for keyword in _IT_KEYWORDS):
        return "LIKELY_IT"
    if any(keyword in title for keyword in _NON_IT_KEYWORDS):
        return "NON_IT"
    return "UNKNOWN"
