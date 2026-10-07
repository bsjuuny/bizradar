def test_service_client_is_per_thread(monkeypatch):
    import threading

    from worker.repositories import opportunities

    created = []
    monkeypatch.setattr(
        opportunities,
        "get_settings",
        lambda: type("S", (), {"supabase_url": "http://x", "supabase_service_role_key": "k"})(),
    )
    monkeypatch.setattr(
        opportunities, "create_client", lambda url, key: created.append(object()) or created[-1]
    )
    monkeypatch.setattr(opportunities, "_thread_local", threading.local())

    main_a = opportunities.get_service_client()
    main_b = opportunities.get_service_client()
    other = []
    worker_thread = threading.Thread(
        target=lambda: other.append(opportunities.get_service_client())
    )
    worker_thread.start()
    worker_thread.join()

    assert main_a is main_b  # reused within a thread
    assert other[0] is not main_a  # never shared across threads
    assert len(created) == 2
