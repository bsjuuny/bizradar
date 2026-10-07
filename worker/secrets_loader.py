"""Load the shared DPAPI vault (C:\\github\\.secrets) into the environment, ahead of
.env.worker. Values already in the environment win; .env.worker only fills what the vault
doesn't have. On a machine without the vault (another PC, CI) this silently does nothing,
and a vault that can't be opened only prints a warning.

Call it from process entry points only - the PM2 scheduler and CLI commands such as
worker.jobs.support_reclassify - and before anything calls worker.config.get_settings(),
which caches. Not from worker/config.py: tests import that, and real keys leaking into
them broke the "skips without a key" tests (2026-09-30).
"""

from __future__ import annotations

import importlib.util
import os
import sys

VAULT_LOADER = r"C:\github\.secrets\load.py"
WORKER_ENV_FILE = "bizradar/.env.worker"


def load_github_secrets(file_keys: list[str] | None = None) -> None:
    if not os.path.exists(VAULT_LOADER):
        return
    try:
        spec = importlib.util.spec_from_file_location("github_secrets_load", VAULT_LOADER)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {VAULT_LOADER}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.load_secrets(file_keys or [WORKER_ENV_FILE], optional=True)
    except Exception as exc:  # noqa: BLE001 - a broken vault must not stop the worker
        print(f"[secrets] 금고 로더를 불러오지 못했습니다: {exc}", file=sys.stderr)
