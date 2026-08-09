import { NextResponse } from "next/server";
import { getChallenge } from "@/lib/challenges";
import { getUser } from "@/lib/dal";
import { isChallengeEnabled } from "@/lib/features";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!isChallengeEnabled()) return NextResponse.json({ error: "Not found" }, { status: 404 });
  if (!(await getUser())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  try {
    const challenge = await getChallenge((await params).id);
    return challenge ? NextResponse.json(challenge) : NextResponse.json({ error: "Not found" }, { status: 404 });
  } catch {
    return NextResponse.json({ error: "Failed to load challenge" }, { status: 500 });
  }
}

