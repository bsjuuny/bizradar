from datetime import datetime

from worker.repositories.match_scores import _parse_datetime


def test_parses_a_real_postgrest_timestamptz_string():
    # Exact shape PostgREST returned live and crashed on before this was added.
    parsed = _parse_datetime("2026-08-19T10:00:00+00:00")
    assert parsed == datetime.fromisoformat("2026-08-19T10:00:00+00:00")


def test_none_and_empty_string_both_map_to_none():
    assert _parse_datetime(None) is None
    assert _parse_datetime("") is None
