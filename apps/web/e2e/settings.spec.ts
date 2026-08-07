import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { SERVICE_ROLE_KEY, SUPABASE_URL, cleanupUser, createConfirmedUser } from "./helpers";

let userId: string;
let companyId: string;
let email: string;
let password: string;

test.beforeAll(async ({ request }) => {
  email = `bizradar-e2e-settings-${randomUUID().slice(0, 8)}@example.com`;
  password = `Test-${randomUUID()}!A1`;
  userId = await createConfirmedUser(request, email, password);

  companyId = randomUUID();
  const headers = {
    apikey: SERVICE_ROLE_KEY,
    Authorization: `Bearer ${SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
  };
  await request.post(`${SUPABASE_URL}/rest/v1/companies`, {
    headers,
    data: { id: companyId, name: "Settings E2E Co", size_band: "1-5" },
  });
  await request.post(`${SUPABASE_URL}/rest/v1/company_members`, {
    headers,
    data: { user_id: userId, company_id: companyId, role: "owner" },
  });
});

test.afterAll(async ({ request }) => {
  await cleanupUser(request, userId);
});

test.beforeEach(async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인" }).click();
  await page.waitForURL(/\/dashboard$/);
});

test("saving Company Match profile persists budget, experience, qualifications, and tech stack", async ({
  page,
}) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "회사 설정" })).toBeVisible();

  await page.getByLabel("희망 예산 (최소, 원)").fill("100000000");
  await page.getByLabel("희망 예산 (최대, 원)").fill("500000000");
  await page.getByLabel("경력 연수").fill("5");
  await page.getByLabel("보유 자격/인증 (쉼표로 구분)").fill("SW사업자 등록, ISO 27001");
  await page.getByRole("checkbox", { name: "Python", exact: true }).check();
  await page.getByRole("checkbox", { name: "AWS", exact: true }).check();

  await page.getByRole("button", { name: "저장" }).click();
  await expect(page.getByText("저장되었습니다.")).toBeVisible();

  // Reload from the server (not just client state) to confirm it actually persisted.
  await page.reload();
  await expect(page.getByLabel("희망 예산 (최소, 원)")).toHaveValue("100000000");
  await expect(page.getByLabel("희망 예산 (최대, 원)")).toHaveValue("500000000");
  await expect(page.getByLabel("경력 연수")).toHaveValue("5");
  await expect(page.getByLabel("보유 자격/인증 (쉼표로 구분)")).toHaveValue(
    "SW사업자 등록, ISO 27001",
  );
  await expect(page.getByRole("checkbox", { name: "Python", exact: true })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "AWS", exact: true })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Java", exact: true })).not.toBeChecked();
});

test("rejects a budget minimum greater than the maximum", async ({ page }) => {
  await page.goto("/settings");
  await page.getByLabel("희망 예산 (최소, 원)").fill("500000000");
  await page.getByLabel("희망 예산 (최대, 원)").fill("100000000");
  await page.getByRole("button", { name: "저장" }).click();
  await expect(page.getByText("최소 예산이 최대 예산보다 클 수 없습니다.")).toBeVisible();
});
