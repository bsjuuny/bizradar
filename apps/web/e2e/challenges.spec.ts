import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { SERVICE_ROLE_KEY, SUPABASE_URL, cleanupUser, createConfirmedUser } from "./helpers";

let userId: string;
let companyId: string;
let challengeId: string;
let email: string;
let password: string;

const challengeTitle = `E2E AI 해커톤 ${randomUUID().slice(0, 8)}`;

function serviceHeaders() {
  return {
    apikey: SERVICE_ROLE_KEY,
    Authorization: `Bearer ${SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
  };
}

test.beforeAll(async ({ request }) => {
  email = `bizradar-e2e-challenge-${randomUUID().slice(0, 8)}@example.com`;
  password = `Test-${randomUUID()}!A1`;
  userId = await createConfirmedUser(request, email, password);
  companyId = randomUUID();
  challengeId = randomUUID();

  await request.post(`${SUPABASE_URL}/rest/v1/companies`, {
    headers: serviceHeaders(),
    data: { id: companyId, name: "Challenge E2E Co", size_band: "1-5" },
  });
  await request.post(`${SUPABASE_URL}/rest/v1/company_members`, {
    headers: serviceHeaders(),
    data: { user_id: userId, company_id: companyId, role: "owner" },
  });
  const challengeResponse = await request.post(`${SUPABASE_URL}/rest/v1/challenges`, {
    headers: serviceHeaders(),
    data: {
      id: challengeId,
      source_id: "e2e-official",
      source_name: "E2E 공식기관",
      source_type: "OFFICIAL_HTML",
      source_priority: 1,
      external_id: challengeId,
      dedupe_key: `e2e-${challengeId}`,
      content_hash: `e2e-${challengeId}`,
      title: challengeTitle,
      description: "생성형 AI 활용 가능. 결과물과 프롬프트를 제출합니다.",
      challenge_type: "HACKATHON",
      organizer: "E2E 공식기관",
      apply_end_date: "2026-08-31T23:59:59+09:00",
      eligibility: "전 국민 누구나, 개인 또는 팀(최대 4인)",
      team_min: 1,
      team_max: 4,
      participation_type: "ONLINE",
      prize: "총 상금 3,000만원",
      total_prize_amount: 30_000_000,
      source_url: "https://example.com/challenges/e2e",
      application_url: "https://example.com/challenges/e2e/apply",
      technology_keywords: ["AI", "LLM"],
      categories: ["웹서비스"],
      attachments: [{ name: "공고문.pdf", url: "https://example.com/challenges/e2e.pdf", media_type: "pdf" }],
      ai_policy: "ALLOWED",
      ai_policy_confidence: 0.95,
      ai_policy_evidence: "생성형 AI 활용 가능",
      ai_policy_source_section: "제출 유의사항",
      generative_ai_policy: "ALLOWED",
      ai_coding_policy: "ALLOWED",
      llm_policy: "ALLOWED",
      prompt_disclosure_required: true,
      analysis_status: "SUCCESS",
      original_text: "생성형 AI 활용 가능. 결과물과 프롬프트를 제출합니다.",
      search_text: `${challengeTitle} E2E 공식기관 AI LLM 웹서비스`,
      status: "OPEN",
      raw_payload: {},
      collected_at: new Date().toISOString(),
      last_checked_at: new Date().toISOString(),
    },
  });
  if (!challengeResponse.ok()) {
    throw new Error(`challenge seed failed: ${challengeResponse.status()} ${await challengeResponse.text()}`);
  }
});

test.afterAll(async ({ request }) => {
  if (challengeId) {
    await request.delete(`${SUPABASE_URL}/rest/v1/challenges?id=eq.${challengeId}`, {
      headers: serviceHeaders(),
    });
  }
  await cleanupUser(request, userId);
});

test.beforeEach(async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인" }).click();
  await page.waitForURL(/\/dashboard$/);
});

test("CHALLENGE list, API, filters, detail, evidence, and source link work", async ({ page }) => {
  await page.goto("/challenges");
  await expect(page.getByRole("heading", { name: "CHALLENGE" })).toBeVisible();
  await expect(page.getByRole("link", { name: challengeTitle })).toBeVisible();

  const apiResponse = await page.request.get(`/api/challenges?q=${encodeURIComponent(challengeTitle)}`);
  expect(apiResponse.ok()).toBeTruthy();
  const apiBody = await apiResponse.json();
  expect(apiBody.items).toHaveLength(1);
  expect(apiBody.items[0].title).toBe(challengeTitle);
  expect(apiBody.items[0].original_text).toBeUndefined();

  const categoriesResponse = await page.request.get("/api/challenges/categories");
  expect(categoriesResponse.ok()).toBeTruthy();
  expect((await categoriesResponse.json()).items).toContain("HACKATHON");
  const sourcesResponse = await page.request.get("/api/challenges/sources");
  expect(sourcesResponse.ok()).toBeTruthy();
  expect((await sourcesResponse.json()).items).toEqual(
    expect.arrayContaining([expect.objectContaining({ source_id: "data-go-kr-notices" })]),
  );

  await page.goto(`/challenges?q=${encodeURIComponent(challengeTitle)}&ai=ALLOWED&type=HACKATHON`);
  await expect(page.getByRole("link", { name: challengeTitle })).toBeVisible();
  await expect(page.getByRole("link", { name: "AI 사용 가능" })).toHaveAttribute("aria-current", "page");

  await page.getByRole("link", { name: challengeTitle }).click();
  await expect(page).toHaveURL(new RegExp(`/challenges/${challengeId}$`));
  await expect(page.getByRole("heading", { name: challengeTitle })).toBeVisible();
  await expect(page.locator("blockquote").getByText("생성형 AI 활용 가능")).toBeVisible();
  await expect(page.getByRole("link", { name: "공고문.pdf ↗" })).toBeVisible();
  await expect(page.getByRole("link", { name: "공고 원문 보기 ↗" })).toHaveAttribute(
    "href",
    "https://example.com/challenges/e2e",
  );
});
