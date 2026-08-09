"""Official data.go.kr public-notice Challenge collector.

The source exposes public server-rendered HTML; no login, browser automation, CAPTCHA,
or access-control bypass is used. Search results are followed to official detail pages.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from worker.challenges.ai_policy import analyze_ai_policy
from worker.challenges.models import ChallengeAttachment, ChallengeNormalized
from worker.challenges.parsers import (
    calculate_status,
    canonicalize_url,
    classify_eligibility,
    classify_participation,
    html_to_text,
    make_dedupe_key,
    normalize_whitespace,
    parse_date_range,
    parse_prize,
    parse_team_size,
)
from worker.challenges.resilience import get_text_with_retry
from worker.challenges.sources import DATA_GO_KR, ChallengeSource
from worker.collectors.base import BaseCollector, CollectorError, RawRecord
from worker.config import Settings, get_settings

LIST_PATH = "/bbs/ntc/selectNoticeListView.do"
DETAIL_PATH = "/bbs/ntc/selectNotice.do"
SEARCH_TERMS = ("공모전", "경진대회", "해커톤", "챌린지")
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "challenges"


def _strip_tags(value: str) -> str:
    return normalize_whitespace(html_to_text(value))


def parse_notice_list(html: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, flags=re.I | re.S):
        link = re.search(
            r"fn_view\(\s*[\"']([^\"']+)[\"']\s*,\s*[\"']([^\"']*)[\"']\s*\)",
            row,
            flags=re.I,
        )
        title_cell = re.search(
            r"<a\b[^>]*class=[\"'][^\"']*title[^\"']*[\"'][^>]*>(.*?)</a>",
            row,
            flags=re.I | re.S,
        )
        date_cell = re.search(
            r"<td\b[^>]*data-label=[\"']등록일[\"'][^>]*>(.*?)</td>",
            row,
            flags=re.I | re.S,
        )
        if not link or not title_cell:
            continue
        title = _strip_tags(title_cell.group(1).replace("첨부파일", ""))
        if not title:
            continue
        records.append(
            {
                "external_id": link.group(1),
                "attachment_id": link.group(2),
                "title": title,
                "posted_date": _strip_tags(date_cell.group(1)) if date_cell else "",
            }
        )
    return records


def _extract_div(html: str, class_name: str) -> str | None:
    match = re.search(
        rf"<(?:div|article)\b[^>]*class=[\"'][^\"']*{re.escape(class_name)}[^\"']*[\"'][^>]*>(.*?)</(?:div|article)>",
        html,
        flags=re.I | re.S,
    )
    return match.group(1) if match else None


def parse_notice_detail(html: str, *, source_url: str) -> dict[str, Any]:
    title_html = _extract_div(html, "viw-title")
    body_html = _extract_div(html, "viw-box")
    if not title_html or not body_html:
        raise CollectorError("data.go.kr detail is missing title or body")

    title = _strip_tags(title_html)
    original_text = html_to_text(body_html)
    if not title or not original_text:
        raise CollectorError("data.go.kr detail contains empty title or body")

    attachments: list[dict[str, str | None]] = []
    file_names = re.findall(
        r"<div\b[^>]*class=[\"'][^\"']*file-name[^\"']*[\"'][^>]*>(.*?)</div>",
        html,
        flags=re.I | re.S,
    )
    file_refs = re.findall(
        r"fn_fileDownload\(\s*[\"']([^\"']+)[\"']\s*,\s*[\"']([^\"']+)[\"']\s*\)",
        html,
        flags=re.I,
    )
    for index, raw_name in enumerate(file_names):
        name = _strip_tags(raw_name)
        file_url = None
        if index < len(file_refs):
            attachment_id, serial = file_refs[index]
            file_url = (
                "https://www.data.go.kr/cmm/cmm/fileDownload.do?"
                f"atchFileId={attachment_id}&fileDetailSn={serial}"
            )
        media_type = name.rsplit(".", 1)[-1].lower() if "." in name else None
        attachments.append({"name": name, "url": file_url, "media_type": media_type})

    application_url = None
    for href in re.findall(r"href=[\"']([^\"']+)[\"']", body_html, flags=re.I):
        candidate = unescape(href).strip()
        if candidate.startswith("http") and "data.go.kr" not in candidate:
            try:
                application_url = canonicalize_url(candidate)
            except ValueError:
                continue
            break

    posted = re.search(r"등록일\s*:\s*(20\d{2}-\d{2}-\d{2})", html)
    return {
        "title": title,
        "original_text": original_text,
        "posted_date": posted.group(1) if posted else None,
        "attachments": attachments,
        "application_url": application_url,
        "source_url": source_url,
    }


def _line_value(text: str, *labels: str) -> str | None:
    for line in text.splitlines():
        normalized = normalize_whitespace(line)
        for label in labels:
            match = re.search(rf"(?:□|○|ㅇ|-)?\s*{re.escape(label)}\s*[:：]\s*(.+)", normalized)
            if match:
                return match.group(1).strip()
    return None


def _organizer_from_title(title: str) -> str | None:
    match = re.match(r"\[([^]]+)]|\(([^)]+)\)", title)
    return (match.group(1) or match.group(2)).strip() if match else None


def _technology_keywords(text: str) -> list[str]:
    vocabulary = (
        "AI",
        "LLM",
        "공공데이터",
        "빅데이터",
        "웹",
        "앱",
        "API",
        "오픈소스",
        "클라우드",
        "IoT",
        "블록체인",
    )
    lowered = text.lower()
    return [keyword for keyword in vocabulary if keyword.lower() in lowered]


class DataGoKrChallengeCollector(BaseCollector[ChallengeNormalized]):
    source = DATA_GO_KR.source_id

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        *,
        source_config: ChallengeSource = DATA_GO_KR,
        max_records: int | None = None,
        fixture_dir: Path = FIXTURE_DIR,
    ) -> None:
        self.settings = settings or get_settings()
        self.source_config = source_config
        self.max_records = max_records
        self.fixture_dir = fixture_dir
        self._client = client
        self._owns_client = client is None

    def __enter__(self) -> DataGoKrChallengeCollector:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.settings.challenge_request_timeout,
                headers={"User-Agent": "BizRadar/1.0 (+challenge-public-notice-collector)"},
            )
        return self._client

    def _request(self, path: str, params: dict[str, str | int]) -> str:
        return get_text_with_retry(
            self._get_client(),
            urljoin(self.source_config.base_url, path),
            params=params,
            source=self.source,
            max_retries=self.settings.challenge_max_retries,
        )

    def _mock_records(self) -> Iterable[RawRecord]:
        list_html = (self.fixture_dir / "data_go_kr_list.html").read_text(encoding="utf-8")
        detail_html = (self.fixture_dir / "data_go_kr_detail.html").read_text(encoding="utf-8")
        notices = parse_notice_list(list_html)
        if not notices:
            raise CollectorError("Challenge mock list fixture contains no notices")
        for notice in notices[: self.max_records]:
            source_url = urljoin(
                self.source_config.base_url,
                f"{DETAIL_PATH}?originId={notice['external_id']}",
            )
            detail = parse_notice_detail(detail_html, source_url=source_url)
            yield RawRecord(
                source=self.source,
                external_id=notice["external_id"],
                fetched_at=datetime.now(UTC),
                payload={**notice, **detail},
            )

    def collect(self) -> Iterable[RawRecord]:
        if self.settings.data_mode == "mock":
            yield from self._mock_records()
            return

        seen: set[str] = set()
        yielded = 0
        for term in SEARCH_TERMS:
            list_html = self._request(
                LIST_PATH,
                {
                    "pageIndex": 1,
                    "pageUnit": 30,
                    "searchOrder": "REGIST_DT",
                    "nttApiYn": "N",
                    "searchCondition2": "2",
                    "searchKeyword1": term,
                },
            )
            notices = parse_notice_list(list_html)
            if not notices:
                raise CollectorError(f"data.go.kr search returned no parseable rows for {term}")
            for notice in notices:
                if notice["external_id"] in seen:
                    continue
                seen.add(notice["external_id"])
                source_url = canonicalize_url(
                    urljoin(
                        self.source_config.base_url,
                        f"{DETAIL_PATH}?originId={notice['external_id']}",
                    )
                )
                detail_html = self._request(
                    DETAIL_PATH,
                    {
                        "originId": notice["external_id"],
                        "atchFileId": notice["attachment_id"],
                        "nttApiYn": "N",
                    },
                )
                detail = parse_notice_detail(detail_html, source_url=source_url)
                yield RawRecord(
                    source=self.source,
                    external_id=notice["external_id"],
                    fetched_at=datetime.now(UTC),
                    payload={**notice, **detail},
                )
                yielded += 1
                if self.max_records is not None and yielded >= self.max_records:
                    return

    def normalize(self, raw: RawRecord) -> ChallengeNormalized:
        payload = raw.payload
        title = normalize_whitespace(str(payload["title"]))
        original_text = normalize_whitespace(str(payload["original_text"]), preserve_lines=True)
        organizer = _organizer_from_title(title)
        host = _line_value(original_text, "주관", "주관기관")
        sponsor = _line_value(original_text, "후원", "후원기관")
        apply_period = _line_value(original_text, "접수기간", "신청기간", "공모접수")
        apply_start, apply_end = parse_date_range(apply_period)
        event_period = _line_value(original_text, "행사기간", "대회기간", "대회일정")
        start_date, end_date = parse_date_range(event_period)
        _, result_date = parse_date_range(
            _line_value(original_text, "결과발표", "수상작 발표", "발표일")
        )
        eligibility = _line_value(original_text, "공모대상", "참가자격", "지원자격")
        region = _line_value(original_text, "지역", "참가지역")
        prize_text = _line_value(original_text, "시상내역", "시상규모", "총 상금", "상금")
        total_prize, prize_description = parse_prize(prize_text)
        team_min, team_max = parse_team_size(eligibility)
        ai = analyze_ai_policy(title, original_text)
        required_documents = []
        document_text = _line_value(original_text, "제출서류", "제출물")
        if document_text:
            required_documents = [document_text]
        submission = _line_value(original_text, "참가방법", "접수방법", "제출방법")
        submission_requirements = [submission] if submission else []
        category = _line_value(original_text, "공모분야", "공모부문")
        categories = [category] if category else []
        source_url = canonicalize_url(str(payload["source_url"]))
        canonical_payload = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        content_hash = hashlib.sha256(canonical_payload.encode()).hexdigest()
        now = raw.fetched_at
        search_text = " ".join(
            part
            for part in (
                title,
                organizer,
                original_text,
                " ".join(categories),
                " ".join(_technology_keywords(original_text)),
            )
            if part
        )
        return ChallengeNormalized(
            source_id=self.source_config.source_id,
            source_name=self.source_config.source_name,
            source_type=self.source_config.source_type,
            source_priority=self.source_config.priority,
            external_id=raw.external_id,
            dedupe_key=make_dedupe_key(title, organizer, apply_end),
            content_hash=content_hash,
            title=title,
            summary=original_text[:300],
            description=original_text,
            challenge_type=ai.challenge_type,
            organizer=organizer,
            host=host,
            sponsor=sponsor,
            start_date=start_date,
            end_date=end_date,
            apply_start_date=apply_start,
            apply_end_date=apply_end,
            result_date=result_date,
            eligibility=eligibility,
            eligibility_type=classify_eligibility(eligibility),
            team_min=team_min,
            team_max=team_max,
            region=region,
            participation_type=classify_participation(original_text),
            prize=prize_text,
            total_prize_amount=total_prize,
            prize_description=prize_description,
            source_url=source_url,
            application_url=payload.get("application_url"),
            required_documents=required_documents,
            submission_requirements=submission_requirements,
            technology_keywords=_technology_keywords(original_text),
            categories=categories,
            tags=_technology_keywords(f"{title} {original_text}"),
            attachments=[
                ChallengeAttachment.model_validate(item) for item in payload["attachments"]
            ],
            ai_policy=ai.ai_policy,
            generative_ai_policy=ai.generative_ai.status,
            ai_coding_policy=ai.ai_coding.status,
            llm_policy=ai.generative_ai.status,
            ai_image_policy=ai.ai_image.status,
            ai_video_policy=ai.ai_video.status,
            ai_audio_policy=ai.ai_audio.status,
            external_ai_api_policy=ai.external_ai_api.status,
            prompt_disclosure_required=ai.prompt_disclosure_required,
            ai_usage_disclosure_required=ai.ai_usage_disclosure_required,
            analysis_status=(
                "PENDING" if self.settings.challenge_ai_analysis_enabled else "RULE_ONLY"
            ),
            external_api_policy=_line_value(original_text, "외부 API", "External API"),
            open_source_policy=_line_value(original_text, "오픈소스", "Open Source"),
            copyright_policy=_line_value(original_text, "저작권"),
            ownership_policy=_line_value(original_text, "소유권", "결과물 귀속"),
            original_text=original_text,
            search_text=search_text,
            status=calculate_status(apply_start, apply_end, now=now),
            raw_payload=payload,
            collected_at=now,
            last_checked_at=now,
        )

    def validate(self, normalized: ChallengeNormalized) -> bool:
        return bool(normalized.title and normalized.original_text and normalized.source_url)

    def persist(self, normalized: ChallengeNormalized) -> None:
        from worker.repositories.challenges import upsert_challenge

        upsert_challenge(normalized)
