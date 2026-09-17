"""Rule filter: buckets a G2B notice into NON_IT / LIKELY_IT / UNKNOWN before any LLM
call touches it (section 21 of the original spec - the full feed never goes to Ollama).

Two independent signals, checked in this order:

1. G2B's own procurement classification (`pubPrcrmntClsfcNm` -> `procurement_category`),
   when it is one of the unambiguously information-systems classes in
   `_IT_PROCUREMENT_CATEGORIES`. This is a structured field the agency itself picked from
   a controlled list, so it is far more reliable than guessing from the title - and it is
   the only signal that catches an IT project whose title contains no technology word at
   all ("전자결재 기안기 ActiveX 제거 사업", "2026년 소망챗 고도화", "K-에듀파인 운영환경
   고도화 및 재해복구 체계 구축").
2. Keyword substring matching on the title, for the many real IT notices whose official
   classification is a generic catch-all ("기타기술용역", "기타사업지원서비스") or is
   outright wrong - e.g. data.go.kr tagged "양자내성암호 시범전환 사업 공인시험 위탁" as
   "학술연구 및 기타 서비스 용역"; the title keywords catch it anyway.

Biased toward inclusion on purpose: a false positive here costs one wasted ~60s Ollama
call; a false negative means a real IT opportunity never reaches a user at all, which is
the worse failure mode for a product whose whole point is "find IT projects". So an IT
signal wins even if a non-IT keyword also matches, and the non-IT list only contains
terms specific enough that they're essentially never IT-related (school trips, facility
cleaning, catering, ...) - not generic contract words like "유지보수" or "구축" that show
up in both IT and non-IT announcements.

Verified against every title in fixtures/g2b/bid_list_servc_sample.json (real G2B data,
not synthetic) and, for the procurement-class signal, against all 15,944 live current
opportunities - see worker/tests/test_rule_filter.py.
"""

Category = str  # "NON_IT" | "LIKELY_IT" | "UNKNOWN"

# G2B 조달분류명 values that are unambiguously information-systems work, so the class
# alone is enough to route the notice to LIKELY_IT no matter how its title reads.
#
# Chosen from real data, not intuition: measured across all 15,944 live current
# opportunities (2026-09-17), every class below already classified 60-78% LIKELY_IT from
# title keywords alone with *zero* NON_IT rows, i.e. the keyword filter agrees with the
# class wherever it manages to fire at all - the remaining UNKNOWN rows in these classes
# are the filter's blind spot, not a genuinely different kind of contract.
#
# That statistic alone is NOT sufficient evidence, though - it was how 공간정보DB구축서비스
# (60% LIKELY_IT, 0 NON_IT) got in here at first, and a user then reported real non-IT
# results. Reading its actual promoted titles showed 토지적성평가용역, 공공측량 및
# 도로대장 작성, 지하시설물도 작성, 지적재조사 도면정비 - i.e. land-surveying work, the
# very thing 측량용역 is excluded for. Before adding a class, read the titles it would
# promote (see the audit approach in docs/DATA_PIPELINE.md#project-filtering), don't just
# check its LIKELY_IT rate.
#
# Classes deliberately LEFT OUT despite looking IT-ish, each checked against its real
# titles in the same dataset - all are genuinely mixed, so promoting them wholesale
# would import non-IT work rather than recover IT work:
#   측량용역              - physical land surveying (저수지 내용적, 배수개선 측량)
#   공간정보DB구축서비스     - same land-surveying work as 측량용역 above, just filed under
#                          a GIS-sounding class name. Was briefly included and removed
#                          after a user reported the false positives; of the 22 rows it
#                          promoted, the bulk were 토지적성평가/공공측량/지하시설물도
#                          작성/지적재조사. Genuine geospatial IT here still lands on
#                          LIKELY_IT through the "GIS" title keyword ("하수관로 정비사업
#                          GIS DB 구축용역"), so excluding the class loses nothing real.
#   디지털콘텐츠개발서비스   - video/exhibition/교육 콘텐츠 production, not software
#   데이터서비스           - largely 기록물 정리·스캔 digitization labor
#   정보화교육서비스        - 초등학교 컴퓨터교실 운영 (an education service)
#   정보통신설계용역/정보통신감리용역 - 정보통신공사업 cabling design/supervision, i.e.
#                          construction-adjacent rather than software (the single
#                          biggest excluded bucket, 27 rows - flip it if 정보통신공사
#                          counts as in-market)
#   유선통신서비스/무선통신서비스 - 회선 임차 (telecom line rental)
#   디지털인쇄물제작서비스/사무용기기임대서비스 - printing and copier leasing
_IT_PROCUREMENT_CATEGORIES = frozenset(
    {
        "정보시스템개발서비스",
        "정보시스템유지관리서비스",
        "정보시스템감리서비스",
        "정보인프라구축서비스",
        "정보화전략계획서비스",
        "정보화프로젝트관리서비스(PMO)",
        "패키지소프트웨어개발및도입서비스",
        "소프트웨어유지및지원서비스",
        "컴퓨터네트워크또는인터넷보안서비스",
        "인터넷지원개발서비스",
        "클라우드서비스",
        "클라우드지원서비스",
        "클라우드융합서비스",
        "정보통신연구조사서비스",
        "전산장비유지관리서비스",
    }
)

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
    "시스템에어컨",  # a retail product category for ceiling-cassette air conditioners -
    # "시스템" fuses onto HVAC equipment in routine facility contracts. Confirmed live in
    # 기타사업지원서비스: "부경대학교 창의관 시스템에어컨 통합시스템 구축".
    "무대시스템",  # festival/performance stage rigging (lighting, sound, truss), not
    # software - confirmed live across several 축제·행사 notices whose procurement class
    # is 축제기획및대행서비스 / 기타행사기획및대행서비스, e.g. "제72회 백제문화제
    # 「무대시스템 설치 및 주제공연 제작」운영 용역", "제16회 팔공산 승시 무대시스템 및
    # 부스설치".
    "무대 시스템",  # the spaced variant of 무대시스템 above - exceptions are plain
    # substrings, so both spellings have to be listed. Confirmed live: "2026 강경국가유산
    # 야행 무대 시스템 임차 및 운영 용역".
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


def _is_it_procurement_category(procurement_category: str | None) -> bool:
    if not procurement_category:
        return False
    # G2B sometimes pads or re-spaces these values; compare with all whitespace removed
    # so a stray space can't silently drop a notice back into UNKNOWN. Every entry in
    # _IT_PROCUREMENT_CATEGORIES is already space-free.
    return "".join(procurement_category.split()) in _IT_PROCUREMENT_CATEGORIES


def classify(title: str, procurement_category: str | None = None) -> Category:
    """Bucket a notice using G2B's own procurement class first, then title keywords.

    `procurement_category` is optional so callers that genuinely have no classification
    (non-G2B sources, older tests) keep the previous title-only behaviour unchanged.
    """
    # Checked before the keyword lists on purpose: an agency-assigned classification from
    # a controlled list beats anything inferred from title wording, and it must also beat
    # the non-IT keywords - a 정보시스템개발서비스 contract that happens to mention 급식
    # is still an IT contract.
    if _is_it_procurement_category(procurement_category):
        return "LIKELY_IT"

    stripped = title
    for exception in _IT_KEYWORD_EXCEPTIONS:
        stripped = stripped.replace(exception, "")

    if any(keyword in stripped for keyword in _IT_KEYWORDS):
        return "LIKELY_IT"
    if any(keyword in title for keyword in _NON_IT_KEYWORDS):
        return "NON_IT"
    return "UNKNOWN"
