import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { SERVICE_ROLE_KEY, SUPABASE_URL, cleanupUser, createConfirmedUser } from "./helpers";

// Email confirmation is on for this Supabase project (see docs/VERIFICATION_REPORT.md),
// so signup can't be driven end-to-end without a real inbox. This test pre-creates and
// confirms a throw-away user via the Admin API (same approach as
// supabase/tests/test_rls_phase1.py) and drives everything from login onward through a
// real browser against the real linked project.
let userId: string;
let email: string;
let password: string;

test.beforeAll(async ({ request }) => {
  email = `bizradar-e2e-${randomUUID().slice(0, 8)}@example.com`;
  password = `Test-${randomUUID()}!A1`;
  userId = await createConfirmedUser(request, email, password);
});

test.afterAll(async ({ request }) => {
  await cleanupUser(request, userId);
});

test("login -> onboarding -> dashboard -> logout, plus unauthenticated redirect", async ({
  page,
}) => {
  // Unauthenticated access to a protected route redirects to /login (proxy.ts).
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);

  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인" }).click();

  // No company yet -> /dashboard's requireCompany() bounces to /onboarding.
  await expect(page).toHaveURL(/\/onboarding$/);

  const companyName = `E2E Test Co ${randomUUID().slice(0, 6)}`;
  await page.getByLabel("회사명").fill(companyName);
  await page.getByLabel("직원 규모").selectOption("6-10");
  await page.getByLabel("업종").fill("IT 서비스");
  await page.getByRole("button", { name: "시작하기" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: companyName })).toBeVisible();
  await expect(page.getByText("6-10")).toBeVisible();
  await expect(page.getByText("IT 서비스")).toBeVisible();

  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // Session is actually gone, not just client-side navigation.
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
});

test("signup calls Supabase Auth and surfaces the result", async ({ page, request }) => {
  // This project has email domain validation on: signUp() rejects any address whose
  // domain doesn't resolve (example.com, made-up domains, ...), while admin-created
  // users bypass that check - which is why beforeAll's user works fine. A real Gmail
  // plus-alias is the only address guaranteed to pass validation without owning a
  // throwaway domain.
  const signupEmail = `bsjuuny+bizradar-e2e-${randomUUID().slice(0, 8)}@gmail.com`;

  await page.goto("/signup");
  await page.getByLabel("이메일").fill(signupEmail);
  await page.getByLabel("비밀번호").fill(`Test-${randomUUID()}!A1`);
  await page.getByLabel(/개인정보 수집 및 이용/).check();
  await page.getByRole("button", { name: "회원가입" }).click();

  // Two legitimate outcomes, both proving the round-trip to Supabase Auth happened
  // and was handled: (a) success -> check-email state (mailer_autoconfirm=false means
  // signUp() never returns a session), or (b) Supabase's shared dev mailer is rate
  // limited (a real, expected-to-occur constraint on the free tier, not a bug) -> our
  // error handling must surface it instead of crashing. An uncaught exception would
  // fail both branches below.
  const checkEmail = page.getByRole("heading", { name: "이메일을 확인해주세요" });
  const errorMessage = page.getByText("email rate limit exceeded");
  await expect(checkEmail.or(errorMessage)).toBeVisible();

  if (await checkEmail.isVisible()) {
    const headers = { apikey: SERVICE_ROLE_KEY, Authorization: `Bearer ${SERVICE_ROLE_KEY}` };
    const listResp = await request.get(
      `${SUPABASE_URL}/auth/v1/admin/users?page=1&per_page=200`,
      { headers },
    );
    const { users } = await listResp.json();
    const created = users.find((u: { email: string }) => u.email === signupEmail);
    expect(created, "signUp() should have created an auth user").toBeTruthy();
    if (created) {
      await request.delete(`${SUPABASE_URL}/auth/v1/admin/users/${created.id}`, { headers });
    }
  } else {
    test.info().annotations.push({
      type: "known-limitation",
      description:
        "Supabase's shared dev mailer hit its rate limit during this run - signup's " +
        "happy path (check-email state) was not exercised this time. See docs/VERIFICATION_REPORT.md.",
    });
  }
});
