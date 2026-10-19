"""Deployment gate for support normalization changes; never applies without a reviewed plan."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib.util import resolve_name
from pathlib import Path
from typing import Any

from worker.jobs import support_reclassify

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / ".support-refresh"
logger = logging.getLogger(__name__)


# Follow support implementation imports, including helpers imported inside normalize().
FINGERPRINT_ROOTS = (
    "worker.collectors.kstartup",
    "worker.collectors.bizinfo",
    "worker.jobs.support_reclassify",
    "worker.jobs.support_refresh",
    "worker.repositories.support_programs",
)


def fingerprint() -> str:
    pending = list(FINGERPRINT_ROOTS)
    visited: dict[str, str] = {}
    while pending:
        module = pending.pop()
        relative = module.replace(".", "/")
        path = ROOT / (relative + ".py")
        if not path.is_file():
            path = ROOT / relative / "__init__.py"
        if not path.is_file() or path.relative_to(ROOT).as_posix() in visited:
            continue
        name = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        visited[name] = source
        # Package initialization can affect imports too.
        pending.extend(".".join(module.split(".")[:i]) for i in range(1, len(module.split("."))))
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        for node in ast.walk(ast.parse(source)):
            imports: list[str] = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    base = resolve_name("." * node.level + base, package)
                imports = [base, *(base + "." + alias.name for alias in node.names)]
            pending.extend(name for name in imports if name.startswith("worker."))
    digest = hashlib.sha256()
    for name, source in sorted(visited.items()):
        digest.update(name.encode() + b"\0" + source.encode() + b"\0")
    return digest.hexdigest()


LOADED_FINGERPRINT = fingerprint()


def identity() -> dict[str, str]:
    from worker.config import get_settings

    if fingerprint() != LOADED_FINGERPRINT:
        raise RuntimeError(
            "Worker code changed on disk; restart the process before refresh/collection"
        )
    settings = get_settings()
    if not settings.supabase_url:
        raise RuntimeError("SUPABASE_URL is required for support refresh")
    return {
        "target": settings.supabase_url.rstrip("/"),
        "mode": settings.data_mode,
        "fingerprint": LOADED_FINGERPRINT,
    }


def state_path(info: dict[str, str]) -> Path:
    target = hashlib.sha256((info["target"] + ":" + info["mode"]).encode()).hexdigest()
    return STATE_DIR / (target + ".json")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(path)


@contextmanager
def exclusive(info: dict[str, str]) -> Iterator[None]:
    """Kernel lock shared by collectors/CLI; released even if a process crashes.

    Keep the lock file: unlinking a locked inode permits another process to lock a
    replacement file while the original holder is still running (POSIX).
    """
    path = state_path(info).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if sys.platform == "win32":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def ready(info: dict[str, str]) -> bool:
    try:
        return json.loads(state_path(info).read_text(encoding="utf-8")) == info
    except (OSError, ValueError):
        return False


def collect_if_ready(job: Callable[[], Any]) -> None:
    try:
        info = identity()
        with exclusive(info):
            if not ready(info):
                logger.error(
                    "support refresh required: run --dry-run --plan, review, then --apply-plan",
                    extra=info,
                )
                return
            job()
    except Exception:
        logger.exception("support collection blocked or failed")


def refresh(*, plan_path: Path, apply: bool = False) -> dict[str, Any]:
    info = identity()
    with exclusive(info):
        prepared = support_reclassify.prepare()
        if identity() != info:
            raise RuntimeError("Code or target changed while preparing; create and review again")
        plan = {
            **info,
            "snapshot": prepared.snapshot,
            "counts": dict(prepared.counts),
            "sources": prepared.sources,
        }
        if not apply:
            write_json(plan_path, plan)
            return plan
        approved = json.loads(plan_path.read_text(encoding="utf-8"))
        if approved != plan:
            raise RuntimeError(
                "Plan is stale or targets different code/database; create and review again"
            )
        if prepared.counts["failed"]:
            raise RuntimeError("Plan contains failed rows; fix them before applying")
        # An unsuccessful explicit re-apply must not retain an older success marker.
        state_path(info).unlink(missing_ok=True)
        result = support_reclassify.apply(prepared)
        if result["failed"]:
            raise RuntimeError(f"Refresh incomplete; no checkpoint written: {dict(result)}")
        verified = support_reclassify.prepare()
        if verified.counts["rows"] or verified.counts["failed"]:
            raise RuntimeError(
                f"Post-write verification failed; no checkpoint written: {dict(verified.counts)}"
            )
        if identity() != info:
            raise RuntimeError("Code changed during refresh; no checkpoint written")
        write_json(state_path(info), info)
        return {**plan, "applied": dict(result), "verified": dict(verified.counts)}


def main() -> None:
    from worker.logging_config import configure_logging
    from worker.secrets_loader import load_github_secrets

    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply-plan", type=Path)
    parser.add_argument("--plan", type=Path, default=STATE_DIR / "plan.json")
    args = parser.parse_args()
    load_github_secrets()
    configure_logging()
    print(
        json.dumps(
            refresh(plan_path=args.apply_plan or args.plan, apply=args.apply_plan is not None),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
