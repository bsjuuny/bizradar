import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { SERVICE_ROLE_KEY, SUPABASE_URL, cleanupUser, createConfirmedUser } from "./helpers";

// Project Radar reads real, already-collected G2B data (see worker/collectors/g2b.py
// and docs/VERIFICATION_REPORT.md's Phase 2 section) - this suite doesn't seed its own
// opportunities, it exercises the UI against whatever is actually in the table.
let userId: string;
let companyId: string;
let email: string;
let password: string;

test.beforeAll(async ({ request }) => {
  email = `bizradar-e2e-opp-${randomUUID().slice(0, 8)}@example.com`;
  password = `Test-${randomUUID()}!A1`;
  userId = await createConfirmedUser(request, email, password);

  // Company is created directly via service role (bypasses RLS, so the
  // RETURNING/SELECT-policy chicken-and-egg from docs/TROUBLESHOOTING.md doesn't
  // apply here) - onboarding itself is already covered by core-flow.spec.ts.
  companyId = randomUUID();
  const headers = {
    apikey: SERVICE_ROLE_KEY,
    Authorization: `Bearer ${SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
  };
  await request.post(`${SUPABASE_URL}/rest/v1/companies`, {
    headers,
    data: { id: companyId, name: "Opportunities E2E Co", size_band: "1-5" },
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

test("unauthenticated access to /opportunities redirects to /login", async ({ browser }) => {
  const anonContext = await browser.newContext();
  const anonPage = await anonContext.newPage();
  await anonPage.goto("/opportunities");
  await expect(anonPage).toHaveURL(/\/login$/);
  await anonContext.close();
});

test("list renders real collected data, and detail navigation works", async ({ page }) => {
  await page.goto("/opportunities");
  await expect(page.getByRole("heading", { name: "Project Radar" })).toBeVisible();

  const firstRow = page.locator("table tbody tr").first();
  await expect(firstRow).toBeVisible();
  const titleLink = firstRow.locator("a").first();
  const title = await titleLink.textContent();

  await titleLink.click();
  await expect(page).toHaveURL(/\/opportunities\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: title ?? "" })).toBeVisible();
  await expect(page.getByText("공고기관")).toBeVisible();

  await page.getByRole("link", { name: /Project Radar 목록으로/ }).click();
  await expect(page).toHaveURL(/\/opportunities$/);
});

test("search with no matches shows the empty state", async ({ page }) => {
  await page.goto("/opportunities");
  const nonsense = `no-such-bid-${randomUUID()}`;
  await page.getByPlaceholder("공고명 또는 발주기관 검색").fill(nonsense);
  await page.getByRole("button", { name: "검색" }).click();

  await expect(page).toHaveURL(new RegExp(`q=${nonsense}`));
  await expect(page.getByText(`“${nonsense}”에 대한 검색 결과가 없습니다.`)).toBeVisible();
  await expect(page.getByRole("link", { name: "전체 공고 보기" })).toBeVisible();
});

test("a nonexistent opportunity id renders the not-found page", async ({ page }) => {
  await page.goto("/opportunities/00000000-0000-0000-0000-000000000000");
  await expect(page.getByText("해당 공고를 찾을 수 없습니다.")).toBeVisible();
});

test("category tab filters the list and shows the category badge", async ({ page }) => {
  await page.goto("/opportunities?category=NON_IT");
  await expect(page.getByRole("link", { name: "IT 무관" })).toHaveAttribute("aria-current", "page");

  const rowCount = await page.locator("table tbody tr").count();
  if (rowCount > 0) {
    await expect(page.locator("table tbody tr").first().getByText("IT 무관")).toBeVisible();
  }
});

test("detail page shows AI analysis for an analyzed opportunity", async ({ page, request }) => {
  const headers = {
    apikey: SERVICE_ROLE_KEY,
    Authorization: `Bearer ${SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
  };
  const opportunityId = randomUUID();

  await request.post(`${SUPABASE_URL}/rest/v1/opportunities`, {
    headers,
    data: {
      id: opportunityId,
      source: "g2b",
      external_id: `e2e-analysis-${opportunityId}`,
      content_hash: "e2e-test-hash",
      title: "E2E 테스트용 AI 챗봇 구축 용역",
      category: "LIKELY_IT",
      raw_payload: {},
    },
  });
  await request.post(`${SUPABASE_URL}/rest/v1/project_analyses`, {
    headers,
    data: {
      opportunity_id: opportunityId,
      status: "SUCCESS",
      project_type: "AI_ML",
      technologies: [{ name: "Python", confidence: 0.92, evidence: "명시적으로 언급됨" }],
      required_roles: ["백엔드 개발자"],
      requirements: ["대화형 챗봇 UI 개발"],
      risks: ["일정 지연 가능성"],
      summary: "E2E 테스트용 요약입니다.",
      model: "qwen3:8b",
      model_version: "test",
      prompt_version: "v1",
      analyzed_content_hash: "e2e-test-hash",
    },
  });

  try {
    await page.goto(`/opportunities/${opportunityId}`);
    await expect(page.getByRole("heading", { name: "AI 분석" })).toBeVisible();
    await expect(page.getByText("E2E 테스트용 요약입니다.")).toBeVisible();
    await expect(page.getByText("Python", { exact: false })).toBeVisible();
    await expect(page.getByText("백엔드 개발자")).toBeVisible();
  } finally {
    await request.delete(`${SUPABASE_URL}/rest/v1/project_analyses?opportunity_id=eq.${opportunityId}`, {
      headers,
    });
    await request.delete(`${SUPABASE_URL}/rest/v1/opportunities?id=eq.${opportunityId}`, { headers });
  }
});
