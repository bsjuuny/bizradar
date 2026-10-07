"""Rule filter for support programs (K-Startup + 기업마당): is this announcement about
IT technology or the IT industry? Feeds `support_programs.it_related` and the "IT 관련만"
filter on Support Radar. See docs/SUPPORT_PROGRAMS.md#it-filter.

"IT 관련" here means the program's subject is IT - SW·AI·데이터·클라우드·정보보호·ICT·
블록체인·게임·핀테크 businesses, and digital/AI transformation programs (DX·AX·스마트공장),
whose vendors are exactly the IT/SI companies this product is for. It does not mean "uses
the internet somewhere" (online sales channels for 소상공인).

Deliberately separate from worker/ai/rule_filter.py (the G2B procurement filter): several
of its keywords mean something else in support-program titles. Measured 2026-10-07 on all
1,599 open support programs, reading every hit per keyword:
- "IoT"/"사물인터넷": all 7 hits were subsidies for fitting environmental-emission
  monitoring sensors at small workplaces (소규모 사업장 방지시설 측정기기).
- "전산": only ever a substring of 안전산업 / 가전산업.
- "플랫폼", "온라인", "디지털", "웹", "앱": overwhelmingly 소상공인 online-sales support
  (해외 온라인 플랫폼 입점, 디지털커머스 소담스퀘어, 공공배달앱 가맹점 홍보물).
- "로봇", "반도체", "양자", "딥테크", "모빌리티": hardware/manufacturing or physical science;
  the genuinely AI-flavoured ones ("시설농업 AI로봇") still match through "AI".
Titles only, not descriptions: a long 사업개요 mentions "온라인 접수" or "데이터" in passing,
so it would add noise faster than recall.

A trailing parenthetical naming a funding project ("...사업", "...구축") is ignored:
기업마당 appends the funding project there, and that name can be IT-sounding when the
program isn't - "의료기기 부품ㆍ모듈 국산화 및 기술개발 지원사업 공고(AI 빅데이터 기반
의료바이오 첨단기기 연구제조센터 구축사업)" is support for medical-device makers. Other
trailing parentheticals count - K-Startup puts the field there: "...참여기업 모집 공고(AI
분야)", "(1회차: AI·빅데이터)". One that names an IT-industry program is kept regardless
(_IT_INDUSTRY_PROGRAM).

Result on that data: 155 of 1,599 open programs. Every hit was read (no false positive
of the IoT-sensor / 홈쇼핑 kind; a few are AI-flavoured programs for other industries, e.g.
"AI 기반 공조부품 성능평가", kept because AI is their subject), then the 308 non-hits
containing weaker words (디지털·플랫폼·스마트·기술·온라인 ...) were read for misses - the
second block of _IT_PATTERNS is what that pass recovered (17 programs). The 98 hits among
closed K-Startup programs were read too. Tests: worker/tests/test_support_it_filter.py.
"""

from __future__ import annotations

import re

from worker.collectors.base import decode_entities

# Latin keywords need ASCII boundaries so "AI" doesn't match inside "MAIN" or "SAINT";
# Hangul next to them is fine ("AI훈련확산센터", "SW개발자").
_LATIN = r"(?<![A-Za-z]){}(?![A-Za-z])"

_IT_PATTERNS = [
    "소프트웨어",
    _LATIN.format(r"S/?W"),
    _LATIN.format("AI"),
    "인공지능",
    "생성형",
    "머신러닝",
    "딥러닝",
    "챗봇",
    "데이터",
    "클라우드",
    _LATIN.format("SaaS"),
    "정보통신",
    _LATIN.format("ICT"),
    "정보화",
    "정보보호",
    "보안",
    "사이버",
    "블록체인",
    "메타버스",
    _LATIN.format("XR"),
    "가상융합",
    "실감콘텐츠",
    r"디지털\s*트윈",
    r"디지털\s*전환",
    _LATIN.format("DX"),
    _LATIN.format("AX"),
    r"스마트\s*공장",
    r"스마트\s*제조",
    r"스마트\s*(?:시티|도시)",
    "핀테크",
    "게임",
    # Found by reading the non-matching titles: IT programs whose names avoid the
    # obvious words.
    "디지털혁신",  # 디지털혁신기술국제공동연구사업 (과기정통부 ICT R&D)
    r"디지털\s*품질",  # 디지털 품질역량강화사업 = SW 품질 컨설팅·테스팅
    "디지털기업",  # 지역디지털기업성장지원사업
    "가명정보",
    "위치정보",
    "개인정보",
    "전자문서",
    "방송통신",
    "코딩",
    _LATIN.format("AIoT"),
    _LATIN.format("ETRI"),
    _LATIN.format("(?i:chatgpt)"),
]
_IT = re.compile("|".join(f"(?:{pattern})" for pattern in _IT_PATTERNS))

# Only a trailing parenthetical that names a funding project or facility build-out is
# dropped ("...사업", "...구축"); a field marker like "(AI 분야)" stays. And one that names
# an IT-industry program is kept even so - "지역선도기업사업화지원 공고
# (지역디지털기업성장지원사업)" is for IT companies though the main title says nothing
# about IT.
_FUNDING_PROJECT = re.compile(r"사업|구축")
_IT_INDUSTRY_PROGRAM = re.compile(r"디지털기업|소프트웨어|정보보호|ICT|(?<![A-Za-z])SW(?![A-Za-z])")

# Removed from the title before matching - each a confirmed non-IT hit in the measurement.
_EXCEPTIONS = [
    # The ministry's name contains 정보통신; its non-IT programs would all match.
    "과학기술정보통신부",
    # TV 데이터홈쇼핑 is a broadcast shopping channel ("TV홈쇼핑 및 데이터홈쇼핑 입점지원").
    "데이터홈쇼핑",
    # 산업기술 유출 방지(기술보호) consulting - trade-secret protection, not infosec.
    "산업보안",
    # Street/security lighting, same exception as the G2B filter.
    "보안등",
    # Policy buzzword ("게임체인저 기업 육성"), not the game industry.
    "게임체인저",
    "게임 체인저",
]

_TRAILING_PARENTHETICAL = re.compile(r"\([^()]*\)\s*$")


def is_it_related(title: str) -> bool:
    text = decode_entities(title)
    trailing = _TRAILING_PARENTHETICAL.search(text)
    if (
        trailing
        and _FUNDING_PROJECT.search(trailing.group())
        and not _IT_INDUSTRY_PROGRAM.search(trailing.group())
    ):
        text = text[: trailing.start()]
    for phrase in _EXCEPTIONS:
        text = text.replace(phrase, " ")
    return _IT.search(text) is not None
