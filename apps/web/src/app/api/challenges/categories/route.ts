import { NextResponse } from "next/server";
import { CHALLENGE_TYPES } from "@/lib/challenges";
import { getUser } from "@/lib/dal";
import { isChallengeEnabled } from "@/lib/features";

export async function GET() {
  if (!isChallengeEnabled()) return NextResponse.json({ error: "Not found" }, { status: 404 });
  if (!(await getUser())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  return NextResponse.json({ items: CHALLENGE_TYPES });
}
