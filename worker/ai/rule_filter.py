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
