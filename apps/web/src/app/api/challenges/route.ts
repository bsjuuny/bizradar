import { NextResponse } from "next/server";
import { getChallenges, parseChallengeFilters } from "@/lib/challenges";
import { getUser } from "@/lib/dal";
import { isChallengeEnabled } from "@/lib/features";

export async function GET(request: Request) {
  if (!isChallengeEnabled()) return NextResponse.json({ error: "Not found" }, { status: 404 });
  if (!(await getUser())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const url = new URL(request.url);
  try {
    const filters = parseChallengeFilters(Object.fromEntries(url.searchParams));
    return NextResponse.json(await getChallenges(filters));
  } catch {
    return NextResponse.json({ error: "Failed to load challenges" }, { status: 500 });
  }
}

