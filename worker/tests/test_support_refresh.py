import subprocess
import sys
from collections import Counter

import pytest

from worker.config import Settings
from worker.jobs import support_reclassify, support_refresh


@pytest.fixture
def gate(tmp_path, monkeypatch):
    info = {"target": "https://test.supabase.co", "mode": "live", "fingerprint": "v1"}
    monkeypatch.setattr(support_refresh, "STATE_DIR", tmp_path)
    monkeypatch.setattr(support_refresh, "identity", lambda: dict(info))
    prepared = support_reclassify.Prepared(
        Counter(scanned=3, rows=2, unchanged=1),
        {"x": ({"it_related": True}, ["a", "b"])},
        "snapshot1",
    )
    calls = []
    monkeypatch.setattr(
        support_reclassify,
        "prepare",
        lambda: (
            support_reclassify.Prepared(Counter(scanned=3, unchanged=3), {}, "updated")
            if calls
            else prepared
        ),
    )
    monkeypatch.setattr(
        support_reclassify.support_programs,
        "update_programs",
        lambda ids, changes: calls.append((ids, changes)),
    )
    return info, prepared, calls, tmp_path / "plan.json"


def test_first_deploy_blocks_without_any_database_call(gate, monkeypatch):
    info, _, calls, _ = gate
    monkeypatch.setattr(support_reclassify, "prepare", lambda: pytest.fail("database read"))
    support_refresh.collect_if_ready(lambda: calls.append("collect"))
    assert calls == []
    assert not support_refresh.ready(info)


def test_dry_run_then_approved_apply_and_noop_collection_gate(gate):
    info, _, calls, path = gate
    plan = support_refresh.refresh(plan_path=path)
    assert plan["target"] == info["target"]
    assert plan["counts"] == {"scanned": 3, "rows": 2, "unchanged": 1}
    assert calls == []
    assert not support_refresh.ready(info)
    result = support_refresh.refresh(plan_path=path, apply=True)
    assert result["applied"]["written"] == 2
    assert support_refresh.ready(info)
    support_refresh.collect_if_ready(lambda: calls.append("collect"))
    assert calls[-1] == "collect"


@pytest.mark.parametrize("change", ["fingerprint", "target", "mode", "snapshot", "counts"])
def test_stale_code_target_or_data_cannot_apply(gate, change):
    info, prepared, calls, path = gate
    support_refresh.refresh(plan_path=path)
    if change in info:
        info[change] = "different"
    elif change == "snapshot":
        prepared.snapshot = "snapshot2"
    else:
        prepared.counts["rows"] += 1
    with pytest.raises(RuntimeError, match="stale"):
        support_refresh.refresh(plan_path=path, apply=True)
    assert calls == []
    assert not support_refresh.ready(info)


def test_normalization_failures_prevent_all_apply_writes(gate):
    info, prepared, calls, path = gate
    prepared.counts["failed"] = 1
    support_refresh.refresh(plan_path=path)
    with pytest.raises(RuntimeError, match="failed rows"):
        support_refresh.refresh(plan_path=path, apply=True)
    assert calls == []
    assert not support_refresh.ready(info)


def test_write_failure_never_checkpoints_and_retry_replans(gate, monkeypatch):
    info, _, _, path = gate
    support_refresh.refresh(plan_path=path)
    monkeypatch.setattr(support_reclassify, "apply", lambda _: Counter(failed=1, written=1))
    with pytest.raises(RuntimeError, match="incomplete"):
        support_refresh.refresh(plan_path=path, apply=True)
    assert not support_refresh.ready(info)
    with support_refresh.exclusive(info):
        pass


def test_change_after_success_blocks_until_next_approval(gate):
    info, _, calls, path = gate
    support_refresh.refresh(plan_path=path)
    support_refresh.refresh(plan_path=path, apply=True)
    calls.clear()
    info["fingerprint"] = "v2"
    support_refresh.collect_if_ready(lambda: calls.append("collect"))
    assert not calls


def test_collectors_and_apply_share_exclusive_lock(gate):
    info, _, calls, path = gate
    with support_refresh.exclusive(info):
        support_refresh.collect_if_ready(lambda: calls.append("collect"))
        with pytest.raises(OSError):
            support_refresh.refresh(plan_path=path)
    assert not calls
    with support_refresh.exclusive(info):
        pass


def test_fingerprint_covers_new_helpers_not_tests(tmp_path, monkeypatch):
    worker = tmp_path / "worker"
    worker.mkdir()
    helper = worker / "new_helper.py"
    (worker / "collectors").mkdir()
    (worker / "collectors" / "kstartup.py").write_text("from worker.new_helper import RULE")
    helper.write_text("RULE = 1")
    monkeypatch.setattr(support_refresh, "ROOT", tmp_path)
    first = support_refresh.fingerprint()
    (worker / "tests").mkdir()
    (worker / "tests" / "test_x.py").write_text("test")
    assert first == support_refresh.fingerprint()
    helper.write_text("RULE = 2")
    assert first != support_refresh.fingerprint()


def test_running_old_process_cannot_approve_new_files(monkeypatch):
    monkeypatch.setattr(support_refresh, "fingerprint", lambda: "new-disk-code")
    with pytest.raises(RuntimeError, match="restart"):
        support_refresh.identity()


def test_scheduler_wires_both_collectors_to_gate(monkeypatch):
    from worker.scheduler import main

    jobs = []

    class Scheduler:
        def add_job(self, func, *args, **kwargs):
            jobs.append((func, kwargs))

        def start(self):
            pass

    monkeypatch.setattr(main, "build_scheduler", Scheduler)
    monkeypatch.setattr(main, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(
        support_refresh,
        "identity",
        lambda: {"target": "test", "mode": "mock", "fingerprint": "test"},
    )
    monkeypatch.setattr(support_refresh, "ready", lambda _: False)
    main.main()
    support_jobs = [
        (func, kw) for func, kw in jobs if kw["id"] in ("kstartup-collect", "bizinfo-collect")
    ]
    assert len(support_jobs) == 2
    assert all(func is support_refresh.collect_if_ready for func, _ in support_jobs)
    assert {kw["args"][0] for _, kw in support_jobs} == {
        main.kstartup_job.run,
        main.bizinfo_job.run,
    }


def test_code_change_during_prepare_prevents_any_write(gate, monkeypatch):
    info, prepared, calls, path = gate

    def prepare():
        info["fingerprint"] = "v2"
        return prepared

    monkeypatch.setattr(support_reclassify, "prepare", prepare)
    with pytest.raises(RuntimeError, match="while preparing"):
        support_refresh.refresh(plan_path=path)
    assert not calls
    assert not path.exists()


def test_failed_reapply_invalidates_previous_checkpoint(gate, monkeypatch):
    info, _, _, path = gate
    support_refresh.refresh(plan_path=path)
    support_refresh.refresh(plan_path=path, apply=True)
    assert support_refresh.ready(info)
    support_refresh.refresh(plan_path=path)
    monkeypatch.setattr(support_reclassify, "apply", lambda _: Counter(failed=1))
    with pytest.raises(RuntimeError, match="incomplete"):
        support_refresh.refresh(plan_path=path, apply=True)
    assert not support_refresh.ready(info)


def test_unrelated_worker_edit_does_not_require_refresh(tmp_path, monkeypatch):
    path = tmp_path / "worker" / "jobs"
    path.mkdir(parents=True)
    (path / "support_refresh.py").write_text("VALUE = 1")
    monkeypatch.setattr(support_refresh, "ROOT", tmp_path)
    first = support_refresh.fingerprint()
    (path / "match_job.py").write_text("VALUE = 2")
    assert support_refresh.fingerprint() == first


def test_success_response_without_updated_data_is_not_completed(gate, monkeypatch):
    info, prepared, _, path = gate
    monkeypatch.setattr(support_reclassify, "prepare", lambda: prepared)
    support_refresh.refresh(plan_path=path)
    with pytest.raises(RuntimeError, match="verification"):
        support_refresh.refresh(plan_path=path, apply=True)
    assert not support_refresh.ready(info)


def test_process_crash_releases_lock(gate):
    info, _, _, path = gate
    script = (
        "import os; from pathlib import Path; "
        "from worker.jobs import support_refresh as refresh; "
        f"refresh.STATE_DIR = Path({str(path.parent)!r}); "
        f"lock = refresh.exclusive({info!r}); "
        "lock.__enter__(); os._exit(0)"
    )
    subprocess.run([sys.executable, "-c", script], check=True, timeout=15)
    with support_refresh.exclusive(info):
        pass


def test_relative_normalizer_import_is_fingerprinted(tmp_path, monkeypatch):
    path = tmp_path / "worker" / "collectors"
    path.mkdir(parents=True)
    (path / "kstartup.py").write_text("from .helper import RULE")
    helper = path / "helper.py"
    helper.write_text("RULE = 1")
    monkeypatch.setattr(support_refresh, "ROOT", tmp_path)
    first = support_refresh.fingerprint()
    helper.write_text("RULE = 2")
    assert first != support_refresh.fingerprint()
