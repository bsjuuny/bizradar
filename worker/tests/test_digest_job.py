import logging

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


def test_all_matches_are_listed_across_messages_without_truncation(monkeypatch):
    # 예전 동작: 상위 10건만 싣고 "...외 N건"으로 뭉갠 뒤 전체를 mark_sent에 넘겨,
    # 잘린 건들이 한 번도 안 보인 채 발송 완료로 기록됐다.
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
    for n in range(40):
        assert f"공고 {n} " in body
    assert "...외" not in body
    assert sorted(marked) == sorted(o["id"] for o in opportunities)
    assert all(len(text) <= digest_job.MAX_MESSAGE_CHARS for text in sent_messages)


def test_a_single_oversized_item_still_gets_its_own_message(monkeypatch):
    # 한 건이 통째로 상한을 넘어도 분할 루프가 전진해야 한다(무한 루프 방지).
    huge = _opp(id_="opp-1", title="가" * (digest_job.MAX_MESSAGE_CHARS + 500))
    messages = digest_job._format_messages("Acme", [(huge, ["W"])])

    assert len(messages) == 1
    assert messages[0][1] == ["opp-1"]


def test_partial_delivery_only_marks_the_messages_that_were_sent(monkeypatch):
    # 2개로 쪼개진 뒤 두 번째가 실패하면, 첫 번째분만 발송 완료로 남아야 한다.
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
