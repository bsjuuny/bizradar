import path from "node:path";
import { config as loadEnv } from "dotenv";
import type { APIRequestContext } from "@playwright/test";

loadEnv({ path: path.resolve(__dirname, "../../../.env.worker") });
loadEnv({ path: path.resolve(__dirname, "../.env.local") });

export const SUPABASE_URL = process.env.SUPABASE_URL!;
export const SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY!;

function serviceHeaders() {
  return { apikey: SERVICE_ROLE_KEY, Authorization: `Bearer ${SERVICE_ROLE_KEY}` };
}

export async function createConfirmedUser(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<string> {
  const resp = await request.post(`${SUPABASE_URL}/auth/v1/admin/users`, {
    headers: serviceHeaders(),
    data: { email, password, email_confirm: true },
  });
  if (!resp.ok()) {
    throw new Error(`admin create user failed: ${resp.status()} ${await resp.text()}`);
  }
  return (await resp.json()).id;
}

// Deletes the user and any company they own (company_members + companies rows) -
// mirrors supabase/tests/test_rls_phase1.py's cleanup so both suites leave the live
// project exactly as they found it.
export async function cleanupUser(request: APIRequestContext, userId: string | undefined) {
  if (!userId) return;
  const headers = serviceHeaders();

  const membersResp = await request.get(
    `${SUPABASE_URL}/rest/v1/company_members?user_id=eq.${userId}&select=company_id`,
    { headers },
  );
  const members: { company_id: string }[] = await membersResp.json();
  for (const { company_id } of members) {
    await request.delete(`${SUPABASE_URL}/rest/v1/company_members?company_id=eq.${company_id}`, {
      headers,
    });
    await request.delete(`${SUPABASE_URL}/rest/v1/companies?id=eq.${company_id}`, { headers });
  }

  await request.delete(`${SUPABASE_URL}/auth/v1/admin/users/${userId}`, { headers });
}
