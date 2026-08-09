import "server-only";

import { requireUser } from "@/lib/dal";
import { createClient } from "@/lib/supabase/server";

export const CHALLENGE_PAGE_SIZE = 12;

export const CHALLENGE_TYPES = [
  "CONTEST",
  "HACKATHON",
  "AI_COMPETITION",
  "DATA_COMPETITION",
  "DEV_COMPETITION",
  "IDEA_COMPETITION",
  "STARTUP_COMPETITION",
  "AWARD",
  "PUBLIC_DATA_COMPETITION",
  "OTHER",
] as const;
export const CHALLENGE_STATUSES = [
  "UPCOMING",
  "OPEN",
  "CLOSING_SOON",
  "CLOSED",
  "UNKNOWN",
] as const;
export const POLICY_STATUSES = [
  "REQUIRED",
  "ALLOWED",
  "LIMITED",
  "PROHIBITED",
  "UNKNOWN",
] as const;
export const PARTICIPATION_TYPES = ["ONLINE", "OFFLINE", "HYBRID", "UNKNOWN"] as const;

export type ChallengeType = (typeof CHALLENGE_TYPES)[number];
export type ChallengeStatus = (typeof CHALLENGE_STATUSES)[number];
export type PolicyStatus = (typeof POLICY_STATUSES)[number];
export type ParticipationType = (typeof PARTICIPATION_TYPES)[number];

export type ChallengeFilters = {
  page: number;
  q: string;
  type?: ChallengeType;
  status?: ChallengeStatus;
  ai?: PolicyStatus;
  aiCoding?: PolicyStatus;
  participation?: ParticipationType;
  entry?: "individual" | "team";
  hasPrize?: boolean;
  organizer?: string;
  technology?: string;
};

export type ChallengeSummary = {
  id: string;
  title: string;
  challenge_type: ChallengeType;
  organizer: string | null;
  apply_start_date: string | null;
  apply_end_date: string | null;
  eligibility: string | null;
  team_min: number | null;
  team_max: number | null;
  participation_type: ParticipationType;
  prize: string | null;
  total_prize_amount: number | null;
  ai_policy: PolicyStatus;
  technology_keywords: string[];
  status: ChallengeStatus;
};

export type ChallengeAttachment = {
  name: string;
  url: string | null;
  media_type: string | null;
};

export type ChallengeDetail = ChallengeSummary & {
  summary: string | null;
  description: string | null;
  host: string | null;
  sponsor: string | null;
  start_date: string | null;
  end_date: string | null;
  result_date: string | null;
  eligibility_type: string;
  region: string | null;
  prize_description: string | null;
  source_name: string;
  source_url: string;
  application_url: string | null;
  required_documents: string[];
  submission_requirements: string[];
  categories: string[];
  tags: string[];
  attachments: ChallengeAttachment[];
  ai_policy_confidence: number;
  ai_policy_evidence: string | null;
  ai_policy_source_section: string | null;
  generative_ai_policy: PolicyStatus;
  ai_coding_policy: PolicyStatus;
  llm_policy: PolicyStatus;
  ai_image_policy: PolicyStatus;
  ai_video_policy: PolicyStatus;
  ai_audio_policy: PolicyStatus;
  external_ai_api_policy: PolicyStatus;
  prompt_disclosure_required: boolean;
  ai_usage_disclosure_required: boolean;
  analysis_status: string;
  external_api_policy: string | null;
  open_source_policy: string | null;
  copyright_policy: string | null;
  ownership_policy: string | null;
  original_text: string;
};

export type ChallengePage = {
  items: ChallengeSummary[];
  total: number;
  page: number;
  pageSize: number;
};

type SearchParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function enumValue<T extends string>(value: string, allowed: readonly T[]): T | undefined {
  return allowed.includes(value as T) ? (value as T) : undefined;
}

export function parseChallengeFilters(params: SearchParams): ChallengeFilters {
  const rawPage = Number.parseInt(one(params.page), 10);
  const entry = one(params.entry);
  return {
    page: Number.isFinite(rawPage) && rawPage > 0 ? rawPage : 1,
    q: one(params.q).trim().slice(0, 100),
    type: enumValue(one(params.type), CHALLENGE_TYPES),
    status: enumValue(one(params.status), CHALLENGE_STATUSES),
    ai: enumValue(one(params.ai), POLICY_STATUSES),
    aiCoding: enumValue(one(params.aiCoding), POLICY_STATUSES),
    participation: enumValue(one(params.participation), PARTICIPATION_TYPES),
    entry: entry === "individual" || entry === "team" ? entry : undefined,
    hasPrize: one(params.hasPrize) === "true" || undefined,
    organizer: one(params.organizer).trim().slice(0, 100) || undefined,
    technology: one(params.technology).trim().slice(0, 50) || undefined,
  };
}

function escapeLikeTerm(term: string): string {
  return term.replace(/[%_]/g, "\\$&");
}

const SUMMARY_COLUMNS =
  "id,title,challenge_type,organizer,apply_start_date,apply_end_date,eligibility," +
  "team_min,team_max,participation_type,prize,total_prize_amount,ai_policy," +
  "technology_keywords,status";

export async function getChallenges(filters: ChallengeFilters): Promise<ChallengePage> {
  await requireUser();
  const supabase = await createClient();
  const from = (filters.page - 1) * CHALLENGE_PAGE_SIZE;
  const to = from + CHALLENGE_PAGE_SIZE - 1;

  let query = supabase
    .from("challenges")
    .select(SUMMARY_COLUMNS, { count: "exact" })
    .order("apply_end_date", { ascending: true, nullsFirst: false })
    .range(from, to);

  if (filters.q) query = query.ilike("search_text", `%${escapeLikeTerm(filters.q)}%`);
  if (filters.type) query = query.eq("challenge_type", filters.type);
  if (filters.status) query = query.eq("status", filters.status);
  if (filters.ai) query = query.eq("ai_policy", filters.ai);
  if (filters.aiCoding) query = query.eq("ai_coding_policy", filters.aiCoding);
  if (filters.participation) query = query.eq("participation_type", filters.participation);
  if (filters.entry === "individual") query = query.lte("team_min", 1);
  if (filters.entry === "team") query = query.gt("team_max", 1);
  if (filters.hasPrize) query = query.gt("total_prize_amount", 0);
  if (filters.organizer) {
    query = query.ilike("organizer", `%${escapeLikeTerm(filters.organizer)}%`);
  }
  if (filters.technology) {
    query = query.contains("technology_keywords", [filters.technology]);
  }

  const { data, error, count } = await query;
  if (error) throw new Error(`Failed to load challenges: ${error.message}`);
  return {
    items: (data ?? []) as unknown as ChallengeSummary[],
    total: count ?? 0,
    page: filters.page,
    pageSize: CHALLENGE_PAGE_SIZE,
  };
}

export async function getChallenge(id: string): Promise<ChallengeDetail | null> {
  await requireUser();
  const supabase = await createClient();
  const { data, error } = await supabase.from("challenges").select("*").eq("id", id).maybeSingle();
  if (error) throw new Error(`Failed to load challenge: ${error.message}`);
  return data as ChallengeDetail | null;
}

export type ChallengeSourceStatus = {
  source_id: string;
  source_name: string;
  enabled: boolean;
  last_run_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_status: string | null;
  fetched: number;
  error: string | null;
};

export async function getChallengeSources(): Promise<ChallengeSourceStatus[]> {
  await requireUser();
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("challenge_source_status")
    .select("source_id,source_name,enabled,last_run_at,last_success_at,last_failure_at,last_status,fetched,error")
    .order("source_name");
  if (error) throw new Error(`Failed to load challenge sources: ${error.message}`);
  return (data ?? []) as ChallengeSourceStatus[];
}

export function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}
