"""Defensive, deterministic parsers for noisy Korean challenge announcements."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, time, timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from worker.challenges.models import (
    ChallengeStatus,
    ChallengeType,
    EligibilityType,
    ParticipationType,
)

SEOUL = ZoneInfo("Asia/Seoul")
CLOSING_SOON_DAYS = 7
_TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "tracking",
    "tracking_id",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")


def html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return normalize_whitespace(" ".join(parser.parts), preserve_lines=True)


def normalize_whitespace(value: str, *, preserve_lines: bool = False) -> str:
    if preserve_lines:
        lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
        return "\n".join(line for line in lines if line)
    return re.sub(r"\s+", " ", value).strip()


def _to_datetime(year: int, month: int, day: int, *, end: bool) -> datetime | None:
    try:
        return datetime.combine(
            datetime(year, month, day).date(),
            time(23, 59, 59) if end else time.min,
            tzinfo=SEOUL,
        )
    except ValueError:
        return None


def parse_date_range(
    value: str | None, *, reference: datetime | None = None
) -> tuple[datetime | None, datetime | None]:
    if not value:
        return None, None
    text = normalize_whitespace(value)
    if any(word in text for word in ("상시", "예산 소진", "선착순", "추후 공지", "미정")):
        return None, None

    now = reference.astimezone(SEOUL) if reference else datetime.now(SEOUL)
    d_day = re.search(r"D\s*-\s*(\d{1,3})", text, re.I)
    if d_day:
        deadline = now + timedelta(days=int(d_day.group(1)))
        return None, datetime.combine(deadline.date(), time(23, 59, 59), tzinfo=SEOUL)

    # Full start date followed by a full or month/day-only end date.
    full = re.findall(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})", text)
    if len(full) >= 2:
        start = _to_datetime(*map(int, full[0]), end=False)
        end = _to_datetime(*map(int, full[1]), end=True)
        return start, end
    if len(full) == 1:
        start_values = tuple(map(int, full[0]))
        remainder = text[text.find(full[0][2]) + len(full[0][2]) :]
        short_dates = re.findall(r"(?<!\d)(\d{1,2})\s*[.\-/월]\s*(\d{1,2})", remainder)
        if short_dates:
            month, day = map(int, short_dates[-1])
            return (
                _to_datetime(*start_values, end=False),
                _to_datetime(start_values[0], month, day, end=True),
            )
        # A lone explicit date in a "까지" expression is an end date, not a start date.
        parsed = _to_datetime(*start_values, end="까지" in text)
        return (None, parsed) if "까지" in text else (parsed, parsed)

    korean_end = re.search(r"(?:(20\d{2})년\s*)?(\d{1,2})월\s*(\d{1,2})일?\s*까지", text)
    if korean_end:
        year = int(korean_end.group(1) or now.year)
        return None, _to_datetime(
            year,
            int(korean_end.group(2)),
            int(korean_end.group(3)),
            end=True,
        )
    return None, None


def parse_prize(value: str | None) -> tuple[int | None, str | None]:
    if not value:
        return None, None
    text = normalize_whitespace(value)
    if any(word in text for word in ("상금 없음", "없음", "미정")):
        return (0, text) if "없음" in text else (None, text)

    matches: list[int] = []
    for raw_number, unit in re.findall(r"([\d,]+(?:\.\d+)?)\s*(억원|천만원|백만원|만원|원)", text):
        number = float(raw_number.replace(",", ""))
        multiplier = {
            "억원": 100_000_000,
            "천만원": 10_000_000,
            "백만원": 1_000_000,
            "만원": 10_000,
            "원": 1,
        }[unit]
        matches.append(round(number * multiplier))
    return (max(matches) if matches else None), text


def classify_challenge_type(title: str, description: str = "") -> ChallengeType:
    text = f"{title} {description}".lower()
    if "공공데이터" in text and any(word in text for word in ("공모", "경진", "대회")):
        return "PUBLIC_DATA_COMPETITION"
    if "해커톤" in text or "hackathon" in text:
        return "HACKATHON"
    if re.search(r"(?:ai|인공지능).{0,20}경진", text, re.I) or "ai competition" in text:
        return "AI_COMPETITION"
    if any(word in text for word in ("데이터 경진", "데이터 분석", "data competition")):
        return "DATA_COMPETITION"
    if any(word in text for word in ("개발 경진", "개발대회", "프로그래밍 대회")):
        return "DEV_COMPETITION"
    if "아이디어" in text:
        return "IDEA_COMPETITION"
    if any(word in text for word in ("창업경진", "창업 경진", "스타트업 경진")):
        return "STARTUP_COMPETITION"
    if any(word in text for word in ("award", "어워드", "시상")):
        return "AWARD"
    if any(word in text for word in ("경진대회", "경진 대회", "competition")):
        return "CONTEST"
    if any(word in text for word in ("공모전", "챌린지", "challenge")):
        return "CONTEST"
    return "OTHER"


def classify_eligibility(text: str | None) -> EligibilityType:
    if not text:
        return "UNKNOWN"
    lowered = text.lower()
    # Specific restrictions win over generic phrases such as "대학(원)생 누구나".
    # Treating that phrase as ANYONE would silently widen eligibility.
    if "대학원" in lowered:
        return "GRADUATE_STUDENT"
    if any(word in lowered for word in ("대학생", "대학(원)생", "대학교")):
        return "UNIVERSITY"
    if "학생" in lowered:
        return "STUDENT"
    if any(word in lowered for word in ("개발자", "프로그래머")):
        return "DEVELOPER"
    if any(word in lowered for word in ("예비창업", "창업기업", "스타트업")):
        return "STARTUP"
    if any(word in lowered for word in ("기업", "사업자", "법인")):
        return "COMPANY"
    if "팀" in lowered:
        return "TEAM"
    if re.search(r"\d{1,2}\s*세", lowered):
        return "AGE_LIMITED"
    if any(region in lowered for region in ("지역", "거주", "소재")):
        return "REGION_LIMITED"
    if any(word in lowered for word in ("누구나", "제한 없음", "전 국민", "전국민")):
        return "ANYONE"
    return "OTHER"


def parse_team_size(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    normalized = normalize_whitespace(text)
    range_match = re.search(
        r"(?:팀\s*)?(\d+)\s*(?:명|인)?\s*[~～\-]\s*(\d+)\s*(?:명|인)",
        normalized,
    )
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))
    max_match = re.search(r"(?:최대|팀당)\s*(\d+)\s*(?:명|인)", normalized)
    if max_match:
        return 1, int(max_match.group(1))
    solo = any(word in normalized for word in ("개인 참가", "개인 또는 팀", "개인/팀"))
    return (1, 1) if solo and "팀" not in normalized else ((1, None) if solo else (None, None))


def classify_participation(text: str | None) -> ParticipationType:
    if not text:
        return "UNKNOWN"
    online = any(word in text for word in ("온라인", "비대면", "이메일 제출", "웹 접수"))
    offline = any(word in text for word in ("오프라인", "현장", "방문 제출", "대면"))
    if online and offline:
        return "HYBRID"
    if online:
        return "ONLINE"
    if offline:
        return "OFFLINE"
    return "UNKNOWN"


def calculate_status(
    apply_start: datetime | None,
    apply_end: datetime | None,
    *,
    now: datetime | None = None,
) -> ChallengeStatus:
    current = (now or datetime.now(SEOUL)).astimezone(SEOUL)
    start = apply_start.astimezone(SEOUL) if apply_start else None
    end = apply_end.astimezone(SEOUL) if apply_end else None
    if start and current < start:
        return "UPCOMING"
    if end and current > end:
        return "CLOSED"
    if end and end - current <= timedelta(days=CLOSING_SOON_DAYS):
        return "CLOSING_SOON"
    if start or end:
        return "OPEN"
    return "UNKNOWN"


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only absolute HTTP(S) URLs are allowed")
    query = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    host = parsed.hostname.lower()
    port = parsed.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, urlencode(sorted(query)), ""))


def make_dedupe_key(title: str, organizer: str | None, apply_end: datetime | None) -> str:
    normalized_title = re.sub(r"[^0-9a-z가-힣]", "", title.lower())
    normalized_organizer = re.sub(r"[^0-9a-z가-힣]", "", (organizer or "").lower())
    date = apply_end.date().isoformat() if apply_end else "unknown"
    return hashlib.sha256(f"{normalized_title}|{normalized_organizer}|{date}".encode()).hexdigest()
