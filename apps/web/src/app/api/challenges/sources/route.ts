import { NextResponse } from "next/server";
import { getChallengeSources } from "@/lib/challenges";
import { getUser } from "@/lib/dal";
import { isChallengeEnabled } from "@/lib/features";

export async function GET() {
  if (!isChallengeEnabled()) return NextResponse.json({ error: "Not found" }, { status: 404 });
  if (!(await getUser())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  try {
    return NextResponse.json({ items: await getChallengeSources() });
  } catch {
    return NextResponse.json({ error: "Failed to load challenge sources" }, { status: 500 });
  }
}
