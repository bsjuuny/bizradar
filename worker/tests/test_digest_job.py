import logging
from types import SimpleNamespace

from worker.jobs import digest_job


def _opp(
    id_="opp-1", title="Test project", category="LIKELY_IT", organization="Org", budget_amount=100
):
    return {
        "id": id_,
        "title": title,
        "category": category,
        "organization": organization,
        "budget_amount": budget_amount,
        "posted_at": "2026-09-13T00:00:00+00:00",
        "bid_close_at": None,
    }


def _watch(name="My Watch", **overrides):
    watch = {
        "id": "watch-1",
        "name": name,
        "keyword": None,
        "category": None,
        "min_budget": None,
        "max_budget": None,
        "min_match_score": None,
        "active": True,
    }
    watch.update(overrides)
    return watch


def _patch_settings(monkeypatch, web_base_url=None):
    """run()이 로컬 .env.worker를 읽지 않도록 고정한다.

    WEB_BASE_URL은 개발자 머신마다 다르게 채워져 있어서, 그대로 두면 "그 외 N건"
    문구가 로컬 파일 내용에 따라 달라지고 테스트가 환경에 의존하게 된다.
    """
    monkeypatch.setattr(
        digest_job, "get_settings", lambda: SimpleNamespace(web_base_url=web_base_url)
    )


class TestMatchesWatch:
    def test_category_mismatch_excludes(self):
        opp = _opp(category="NON_IT")
        watch = _watch(category="LIKELY_IT")
        assert digest_job._matches_watch(opp, watch, None) is False

    def test_budget_below_min_excludes(self):
        opp = _opp(budget_amount=50)
        watch = _watch(min_budget=100)
        assert digest_job._matches_watch(opp, watch, None) is False

    def test_budget_above_max_excludes(self):
        opp = _opp(budget_amount=500)
        watch = _watch(max_budget=100)
        assert digest_job._matches_watch(opp, watch, None) is False

    def test_score_below_min_excludes(self):
        opp = _opp()
        watch = _watch(min_match_score=80)
        assert digest_job._matches_watch(opp, watch, 50) is False

    def test_keyword_not_in_title_or_org_excludes(self):
        opp = _opp(title="AI 시스템 구축", organization="서울시")
        watch = _watch(keyword="부산")
        assert digest_job._matches_watch(opp, watch, None) is False

    def test_keyword_matches_case_insensitively(self):
        opp = _opp(title="AI Platform Build", organization="Seoul")
        watch = _watch(keyword="ai platform")
        assert digest_job._matches_watch(opp, watch, None) is True

    def test_no_conditions_set_does_not_match_anything(self):
        assert digest_job._matches_watch(_opp(), _watch(), None) is False

    def test_inactive_watch_never_matches(self):
        # get_active_watch_conditions() already filters active=true at the query
        # level, so this only matters if _matches_watch is ever called with a stale
        # or hand-built watch dict - kept as a true port of matchesWatch regardless.
        watch = _watch(active=False)
        assert digest_job._matches_watch(_opp(), watch, None) is False

    def test_watch_missing_active_key_does_not_match(self):
        # Mirrors matchesWatch's `if (!watch.active) return false` - undefined/missing
        # is falsy in TS, so a dict without the key must behave the same way here.
        watch = _watch()
        del watch["active"]
        assert digest_job._matches_watch(_opp(), watch, None) is False


def test_run_sends_one_message_per_company_with_a_match(monkeypatch, caplog):
    companies = [{"id": "company-1", "name": "Acme", "telegram_chat_id": "111"}]
    watches_by_company = {"company-1": [_watch(name="IT watch", category="LIKELY_IT")]}
    opportunities = [_opp(id_="opp-1", category="LIKELY_IT")]

    monkeypatch.setattr(digest_job, "get_companies_with_telegram", lambda: companies)
    monkeypatch.setattr(digest_job, "get_active_watch_conditions", lambda ids: watches_by_company)
    monkeypatch.setattr(digest_job, "get_recent_opportunities", lambda since: opportunities)
    monkeypatch.setattr(digest_job, "get_match_scores", lambda cids, oids: {})
    monkeypatch.setattr(digest_job, "get_already_sent", lambda cid, oids: set())

    sent_messages = []
    monkeypatch.setattr(
        digest_job,
        "send_telegram_message",
        lambda chat_id, text: sent_messages.append((chat_id, text)) or True,
    )
    marked = []
    monkeypatch.setattr(digest_job, "mark_sent", lambda cid, oids: marked.append((cid, oids)))

    with caplog.at_level(logging.INFO):
        digest_job.run()

    assert len(sent_messages) == 1
    assert sent_messages[0][0] == "111"
    assert "Test project" in sent_messages[0][1]
    assert marked == [("company-1", ["opp-1"])]
    assert any("digest job finished" in r.message for r in caplog.records)


def test_run_skips_already_sent_opportunities(monkeypatch):
    companies = [{"id": "company-1", "name": "Acme", "telegram_chat_id": "111"}]
    watches_by_company = {"company-1": [_watch()]}
    opportunities = [_opp(id_="opp-1")]

    monkeypatch.setattr(digest_job, "get_companies_with_telegram", lambda: companies)
    monkeypatch.setattr(digest_job, "get_active_watch_conditions", lambda ids: watches_by_company)
    monkeypatch.setattr(digest_job, "get_recent_opportunities", lambda since: opportunities)
    monkeypatch.setattr(digest_job, "get_match_scores", lambda cids, oids: {})
    monkeypatch.setattr(digest_job, "get_already_sent", lambda cid, oids: {"opp-1"})

    monkeypatch.setattr(
        digest_job,
        "send_telegram_message",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError()),
    )

    digest_job.run()  # must not raise / must not send


def test_run_does_not_send_for_watch_without_criteria(monkeypatch):
    companies = [{"id": "company-1", "name": "Acme", "telegram_chat_id": "111"}]
    watches_by_company = {"company-1": [_watch(name="전체 알림 (테스트용)")]}
    opportunities = [_opp(id_="opp-1")]

    monkeypatch.setattr(digest_job, "get_companies_with_telegram", lambda: companies)
    monkeypatch.setattr(digest_job, "get_active_watch_conditions", lambda ids: watches_by_company)
    monkeypatch.setattr(digest_job, "get_recent_opportunities", lambda since: opportunities)
    monkeypatch.setattr(digest_job, "get_match_scores", lambda cids, oids: {})
    monkeypatch.setattr(digest_job, "get_already_sent", lambda cid, oids: set())
    monkeypatch.setattr(
        digest_job,
        "send_telegram_message",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError()),
    )

    digest_job.run()


def test_run_no_companies_with_telegram_is_a_noop(monkeypatch, caplog):
    monkeypatch.setattr(digest_job, "get_companies_with_telegram", lambda: [])
    monkeypatch.setattr(
        digest_job,
        "get_active_watch_conditions",
        lambda ids: (_ for _ in ()).throw(AssertionError()),
    )

    with caplog.at_level(logging.INFO):
        digest_job.run()

    assert any("no companies with telegram_chat_id" in r.message for r in caplog.records)


def test_run_does_not_raise_when_repository_fails(monkeypatch, caplog):
    def boom():
        raise RuntimeError("Supabase is unreachable")

    monkeypatch.setattr(digest_job, "get_companies_with_telegram", boom)

    with caplog.at_level(logging.ERROR):
        digest_job.run()  # must not raise

    assert any("digest job failed entirely" in r.message for r in caplog.records)


def test_digest_is_capped_and_uncapped_items_are_not_marked_sent(monkeypatch):
    """상한을 넘긴 건은 "그 외 N건"으로만 알리고 발송 완료로 기록하지 않는다.

    예전 구현은 10건만 싣고 매칭 전체를 mark_sent에 넘겨서, 못 본 건이 다음 회차에
    already_sent로 걸러지며 영구 유실됐다. 상한을 다시 도입하면서 같은 실수를
    반복하지 않는지가 이 테스트의 핵심이다.
    """
    monkeypatch.setattr(digest_job, "MAX_ITEMS_PER_DIGEST", 5)
    _patch_settings(monkeypatch)
    companies = [{"id": "company-1", "name": "Acme", "telegram_chat_id": "111"}]
    watches_by_company = {"company-1": [_watch(name="IT watch", category="LIKELY_IT")]}
    opportunities = [
        _opp(id_=f"opp-{n}", title=f"공고 {n}", category="LIKELY_IT") for n in range(28)
    ]

    monkeypatch.setattr(digest_job, "get_companies_with_telegram", lambda: companies)
    monkeypatch.setattr(digest_job, "get_active_watch_conditions", lambda ids: watches_by_company)
    monkeypatch.setattr(digest_job, "get_recent_opportunities", lambda since: opportunities)
    monkeypatch.setattr(digest_job, "get_match_scores", lambda cids, oids: {})
    monkeypatch.setattr(digest_job, "get_already_sent", lambda cid, oids: set())

    sent_messages: list[str] = []
    monkeypatch.setattr(
        digest_job,
        "send_telegram_message",
        lambda chat_id, text: sent_messages.append(text) or True,
    )
    marked: list[str] = []
    monkeypatch.setattr(digest_job, "mark_sent", lambda cid, oids: marked.extend(oids))

    digest_job.run()

    body = "\n".join(sent_messages)
    assert body.count("▸ ") == 5
    assert "23건 더 있어요" in body
    # 못 실은 23건은 어디에도 기록되지 않아야 한다 - 기록되면 다시는 안 나온다.
    assert len(marked) == 5


def test_open_to_all_items_are_ranked_into_the_capped_digest(monkeypatch):
    # 진입장벽 없는 공고가 상한 안에 들어와야 후킹 포인트가 실제로 보인다.
    monkeypatch.setattr(digest_job, "MAX_ITEMS_PER_DIGEST", 2)
    restricted = [(_opp(id_=f"limited-{n}", title=f"제한 {n}"), ["W"]) for n in range(5)]
    for opportunity, _ in restricted:
        opportunity["industry_limited"] = True
    open_one = _opp(id_="open-1", title="누구나 가능")
    open_one["industry_limited"] = False
    open_one["region_restriction"] = None

    ranked = sorted([*restricted, (open_one, ["W"])], key=digest_job._rank_key)

    assert ranked[0][0]["id"] == "open-1"


def test_all_matches_are_listed_across_messages_without_truncation(monkeypatch):
    # 상한 안에서는 길이 때문에 잘리는 일이 없어야 한다 - 상한을 올려 분할만 검증한다.
    monkeypatch.setattr(digest_job, "MAX_ITEMS_PER_DIGEST", 100)
    companies = [{"id": "company-1", "name": "Acme", "telegram_chat_id": "111"}]
    watches_by_company = {"company-1": [_watch(name="IT watch", category="LIKELY_IT")]}
    opportunities = [
        _opp(id_=f"opp-{n}", title=f"공고 {n}", category="LIKELY_IT") for n in range(40)
    ]

    monkeypatch.setattr(digest_job, "get_companies_with_telegram", lambda: companies)
    monkeypatch.setattr(digest_job, "get_active_watch_conditions", lambda ids: watches_by_company)
    monkeypatch.setattr(digest_job, "get_recent_opportunities", lambda since: opportunities)
    monkeypatch.setattr(digest_job, "get_match_scores", lambda cids, oids: {})
    monkeypatch.setattr(digest_job, "get_already_sent", lambda cid, oids: set())

    sent_messages = []
    monkeypatch.setattr(
        digest_job,
        "send_telegram_message",
        lambda chat_id, text: sent_messages.append(text) or True,
    )
    marked = []
    monkeypatch.setattr(digest_job, "mark_sent", lambda cid, oids: marked.extend(oids))

    digest_job.run()

    body = "\n".join(sent_messages)
    # 부분 문자열로 세면 "공고 1"이 "공고 10"에도 걸려 모호하다. 항목 접두사 개수로 센다.
    assert body.count("▸ ") == 40
    assert "...외" not in body
    assert sorted(marked) == sorted(o["id"] for o in opportunities)
    assert all(len(text) <= digest_job.MAX_MESSAGE_CHARS for text in sent_messages)


def test_single_watch_name_moves_to_the_header_instead_of_every_line():
    # Watch가 하나뿐이면 항목마다 같은 이름이 반복될 뿐 정보가 없다(실측 28건 전부 동일).
    matches = [(_opp(id_=f"opp-{n}", title=f"공고 {n}"), ["IT watch"]) for n in range(5)]
    body, _ = digest_job._format_messages("Acme", matches)[0]

    assert "🔔 Watch: IT watch" in body
    assert body.count("IT watch") == 1


def test_multiple_watch_names_stay_on_each_line():
    # 여러 Watch가 걸리면 어느 조건에 걸렸는지가 항목마다 실제 정보가 된다.
    matches = [
        (_opp(id_="opp-1", title="공고 1"), ["IT watch"]),
        (_opp(id_="opp-2", title="공고 2"), ["예산 watch"]),
    ]
    body, _ = digest_job._format_messages("Acme", matches)[0]

    assert "🔔 Watch:" not in body
    assert "🔔 IT watch" in body
    assert "🔔 예산 watch" in body


def test_open_to_all_badge_only_when_both_limits_are_explicitly_absent():
    # null은 "공고에 명시 안 됨"이지 "제한 없음"이 아니다 - 명시되지 않은 것을 누구나
    # 지원 가능으로 보여주면 자격이 안 되는 공고를 권하게 된다.
    assert digest_job._is_open_to_all({"industry_limited": False, "region_restriction": None})
    assert not digest_job._is_open_to_all({"industry_limited": None, "region_restriction": None})
    assert not digest_job._is_open_to_all({"industry_limited": True, "region_restriction": None})
    assert not digest_job._is_open_to_all(
        {"industry_limited": False, "region_restriction": "본사소재지"}
    )


def test_a_single_oversized_item_still_gets_its_own_message(monkeypatch):
    # 한 건이 통째로 상한을 넘어도 분할 루프가 전진해야 한다(무한 루프 방지).
    huge = _opp(id_="opp-1", title="가" * (digest_job.MAX_MESSAGE_CHARS + 500))
    messages = digest_job._format_messages("Acme", [(huge, ["W"])])

    assert len(messages) == 1
    assert messages[0][1] == ["opp-1"]


def test_partial_delivery_only_marks_the_messages_that_were_sent(monkeypatch):
    # 2개로 쪼개진 뒤 두 번째가 실패하면, 첫 번째분만 발송 완료로 남아야 한다.
    monkeypatch.setattr(digest_job, "MAX_ITEMS_PER_DIGEST", 100)
    companies = [{"id": "company-1", "name": "Acme", "telegram_chat_id": "111"}]
    watches_by_company = {"company-1": [_watch(name="IT watch", category="LIKELY_IT")]}
    opportunities = [
        _opp(id_=f"opp-{n}", title=f"공고 {n} " + "가" * 200, category="LIKELY_IT")
        for n in range(40)
    ]

    monkeypatch.setattr(digest_job, "get_companies_with_telegram", lambda: companies)
    monkeypatch.setattr(digest_job, "get_active_watch_conditions", lambda ids: watches_by_company)
    monkeypatch.setattr(digest_job, "get_recent_opportunities", lambda since: opportunities)
    monkeypatch.setattr(digest_job, "get_match_scores", lambda cids, oids: {})
    monkeypatch.setattr(digest_job, "get_already_sent", lambda cid, oids: set())

    calls = {"n": 0}

    def send(chat_id, text):
        calls["n"] += 1
        return calls["n"] == 1

    monkeypatch.setattr(digest_job, "send_telegram_message", send)
    marked = []
    monkeypatch.setattr(digest_job, "mark_sent", lambda cid, oids: marked.extend(oids))

    digest_job.run()

    assert calls["n"] == 2  # 첫 실패에서 멈춘다
    assert 0 < len(marked) < len(opportunities)


def test_run_does_not_mark_sent_when_telegram_send_fails(monkeypatch):
    companies = [{"id": "company-1", "name": "Acme", "telegram_chat_id": "111"}]
    watches_by_company = {"company-1": [_watch()]}
    opportunities = [_opp(id_="opp-1")]

    monkeypatch.setattr(digest_job, "get_companies_with_telegram", lambda: companies)
    monkeypatch.setattr(digest_job, "get_active_watch_conditions", lambda ids: watches_by_company)
    monkeypatch.setattr(digest_job, "get_recent_opportunities", lambda since: opportunities)
    monkeypatch.setattr(digest_job, "get_match_scores", lambda cids, oids: {})
    monkeypatch.setattr(digest_job, "get_already_sent", lambda cid, oids: set())
    monkeypatch.setattr(digest_job, "send_telegram_message", lambda *a, **kw: False)

    marked = []
    monkeypatch.setattr(digest_job, "mark_sent", lambda cid, oids: marked.append((cid, oids)))

    digest_job.run()

    assert marked == []


def test_remaining_notice_links_to_the_web_list_when_configured():
    matches = [(_opp(id_="opp-1", title="공고 1"), ["W"])]
    body, _ = digest_job._format_messages(
        "Acme", matches, remaining=23, web_url="https://example.test/opportunities"
    )[0]

    assert "23건 더 있어요" in body
    assert "전체 목록 보기: https://example.test/opportunities" in body


def test_remaining_notice_omits_the_link_when_not_configured():
    # 주소 설정이 비어 있으면 죽은 링크를 매일 보내는 대신 문구만 남긴다.
    matches = [(_opp(id_="opp-1", title="공고 1"), ["W"])]
    body, _ = digest_job._format_messages("Acme", matches, remaining=23)[0]

    assert "23건 더 있어요" in body
    assert "http" not in body


def test_run_passes_the_configured_web_url_through_to_the_message(monkeypatch):
    """설정값이 실제 발송 경로까지 도달하는지 검증한다.

    설정 필드를 추가하고 정작 그 값을 쓰는 지점에 연결하지 않아 조용히 None으로
    남는 실수를 이 저장소 밖에서 이미 한 번 했다. 문구만 보는 테스트는 그걸 못 잡아서
    run() 경로로 확인하고, 끝의 슬래시가 중복되지 않는지도 함께 본다.
    """
    _patch_settings(monkeypatch, "https://example.test/")
    monkeypatch.setattr(digest_job, "MAX_ITEMS_PER_DIGEST", 1)
    companies = [{"id": "company-1", "name": "Acme", "telegram_chat_id": "111"}]
    watches_by_company = {"company-1": [_watch(name="IT watch", category="LIKELY_IT")]}
    opportunities = [
        _opp(id_=f"opp-{n}", title=f"공고 {n}", category="LIKELY_IT") for n in range(3)
    ]

    monkeypatch.setattr(digest_job, "get_companies_with_telegram", lambda: companies)
    monkeypatch.setattr(digest_job, "get_active_watch_conditions", lambda ids: watches_by_company)
    monkeypatch.setattr(digest_job, "get_recent_opportunities", lambda since: opportunities)
    monkeypatch.setattr(digest_job, "get_match_scores", lambda cids, oids: {})
    monkeypatch.setattr(digest_job, "get_already_sent", lambda cid, oids: set())

    sent_messages: list[str] = []
    monkeypatch.setattr(
        digest_job,
        "send_telegram_message",
        lambda chat_id, text: sent_messages.append(text) or True,
    )
    monkeypatch.setattr(digest_job, "mark_sent", lambda cid, oids: None)

    digest_job.run()

    body = "\n".join(sent_messages)
    assert "2건 더 있어요" in body
    assert "전체 목록 보기: https://example.test/opportunities" in body
