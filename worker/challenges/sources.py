"""Registry for Challenge sources. Keep source metadata out of collector logic."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChallengeSource:
    source_id: str
    source_name: str
    source_type: str
    base_url: str
    enabled: bool
    priority: int
    collection_method: str
    schedule: str
    timeout_seconds: float
    max_retries: int


DATA_GO_KR = ChallengeSource(
    source_id="data-go-kr-notices",
    source_name="공공데이터포털 공지사항",
    source_type="OFFICIAL_HTML",
    base_url="https://www.data.go.kr",
    enabled=True,
    priority=10,
    collection_method="PUBLIC_HTML",
    schedule="0 */6 * * *",
    timeout_seconds=15.0,
    max_retries=3,
)

CHALLENGE_SOURCES = (DATA_GO_KR,)


def get_source(source_id: str) -> ChallengeSource:
    for source in CHALLENGE_SOURCES:
        if source.source_id == source_id:
            return source
    raise KeyError(f"Unknown challenge source: {source_id}")
