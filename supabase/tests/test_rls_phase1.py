"""RLS smoke test for the Phase 1 schema, run against the real linked Supabase project.

Not part of `pytest worker/tests` (those must run offline). This script creates two
throw-away auth users, exercises the RLS cases from the original spec (section 30:
user A can see own company, cannot see user B's, service-role-only writes are blocked
for anon/authenticated), and always deletes what it created - even on failure.

Usage: python supabase/tests/test_rls_phase1.py
Requires SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY (.env.worker) and
NEXT_PUBLIC_SUPABASE_ANON_KEY (apps/web/.env.local).
"""

from __future__ import annotations

import os
import sys
import uuid

import httpx
from dotenv import dotenv_values

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

worker_env = dotenv_values(os.path.join(ROOT, ".env.worker"))
web_env = dotenv_values(os.path.join(ROOT, "apps", "web", ".env.local"))

SUPABASE_URL = worker_env["SUPABASE_URL"]
SERVICE_ROLE_KEY = worker_env["SUPABASE_SERVICE_ROLE_KEY"]
ANON_KEY = web_env["NEXT_PUBLIC_SUPABASE_ANON_KEY"]

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def admin_create_user(email: str, password: str) -> str:
    resp = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers={"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"},
        json={"email": email, "password": password, "email_confirm": True},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def admin_delete_user(user_id: str) -> None:
    httpx.delete(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
        headers={"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"},
        timeout=30,
    )


def sign_in(email: str, password: str) -> str:
    resp = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY},
        json={"email": email, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def rest(method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
    headers = {"apikey": ANON_KEY, "Content-Type": "application/json", **kwargs.pop("headers", {})}
    headers["Authorization"] = f"Bearer {token}" if token else f"Bearer {ANON_KEY}"
    return httpx.request(method, f"{SUPABASE_URL}/rest/v1/{path}", headers=headers, timeout=30, **kwargs)


def service_rest(method: str, path: str, **kwargs) -> httpx.Response:
    headers = {
        "apikey": SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        **kwargs.pop("headers", {}),
    }
    return httpx.request(method, f"{SUPABASE_URL}/rest/v1/{path}", headers=headers, timeout=30, **kwargs)


def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    email_a = f"bizradar-rls-test-a-{suffix}@example.com"
    email_b = f"bizradar-rls-test-b-{suffix}@example.com"
    password = f"Test-{uuid.uuid4().hex}!A1"

    user_a_id = user_b_id = None
    company_a_id = company_b_id = None

    try:
        user_a_id = admin_create_user(email_a, password)
        user_b_id = admin_create_user(email_b, password)
        token_a = sign_in(email_a, password)
        token_b = sign_in(email_b, password)

        # A creates and joins Company A. The client generates the id and does NOT
        # request return=representation: an INSERT...RETURNING implicitly re-checks the
        # table's SELECT policy on the new row, and companies_select_own depends on
        # auth_company_id(), which is only non-null once company_members exists - a
        # chicken-and-egg RLS violation on the very first insert otherwise. See
        # docs/TROUBLESHOOTING.md.
        company_a_id = str(uuid.uuid4())
        resp = rest(
            "POST", "companies", token=token_a,
            json={"id": company_a_id, "name": "RLS Test Co A", "size_band": "1-5"},
        )
        check("A can create a company", resp.status_code == 201, resp.text)

        resp = rest(
            "POST", "company_members", token=token_a,
            json={"user_id": user_a_id, "company_id": company_a_id, "role": "owner"},
        )
        check("A can join own company", resp.status_code == 201, resp.text)

        # B creates and joins Company B
        company_b_id = str(uuid.uuid4())
        resp = rest(
            "POST", "companies", token=token_b,
            json={"id": company_b_id, "name": "RLS Test Co B", "size_band": "6-10"},
        )
        check("B can create a company", resp.status_code == 201, resp.text)

        resp = rest(
            "POST", "company_members", token=token_b,
            json={"user_id": user_b_id, "company_id": company_b_id, "role": "owner"},
        )
        check("B can join own company", resp.status_code == 201, resp.text)

        # A can see own company, not B's
        resp = rest("GET", f"companies?id=eq.{company_a_id}", token=token_a)
        check("A can read own company", resp.status_code == 200 and len(resp.json()) == 1, resp.text)

        resp = rest("GET", f"companies?id=eq.{company_b_id}", token=token_a)
        check("A cannot read B's company", resp.status_code == 200 and len(resp.json()) == 0, resp.text)

        # B cannot see A's company
        resp = rest("GET", f"companies?id=eq.{company_a_id}", token=token_b)
        check("B cannot read A's company", resp.status_code == 200 and len(resp.json()) == 0, resp.text)

        # A cannot read B's membership row
        resp = rest("GET", f"company_members?user_id=eq.{user_b_id}", token=token_a)
        check(
            "A cannot read B's company_members row",
            resp.status_code == 200 and len(resp.json()) == 0,
            resp.text,
        )

        # Public opportunity-style table: authenticated can read, anon write is blocked
        resp = rest("GET", "worker_heartbeats", token=token_a)
        check("Authenticated user can read worker_heartbeats", resp.status_code == 200, resp.text)

        resp = rest("POST", "worker_heartbeats", token=None, json={"worker_name": "rls-hack", "status": "x"})
        check(
            "Anon insert into worker_heartbeats is rejected",
            resp.status_code in (401, 403),
            f"got {resp.status_code}: {resp.text}",
        )

        resp = rest(
            "POST", "worker_heartbeats", token=token_a,
            json={"worker_name": "rls-hack-2", "status": "x"},
        )
        check(
            "Authenticated (non-service-role) insert into worker_heartbeats is rejected",
            resp.status_code in (401, 403),
            f"got {resp.status_code}: {resp.text}",
        )

        # Service role can write (bypasses RLS)
        resp = service_rest(
            "POST", "worker_heartbeats",
            headers={"Prefer": "return=representation"},
            json={"worker_name": f"rls-test-{suffix}", "status": "ok"},
        )
        check("Service role can write worker_heartbeats", resp.status_code == 201, resp.text)

    finally:
        # Cleanup, best-effort, in dependency order.
        if company_a_id:
            service_rest("DELETE", f"company_members?company_id=eq.{company_a_id}")
            service_rest("DELETE", f"companies?id=eq.{company_a_id}")
        if company_b_id:
            service_rest("DELETE", f"company_members?company_id=eq.{company_b_id}")
            service_rest("DELETE", f"companies?id=eq.{company_b_id}")
        service_rest("DELETE", f"worker_heartbeats?worker_name=eq.rls-test-{suffix}")
        if user_a_id:
            admin_delete_user(user_a_id)
        if user_b_id:
            admin_delete_user(user_b_id)

    print()
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("All RLS checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
