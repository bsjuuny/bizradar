import Link from "next/link";

export default function NotFound() {
  return <div className="rounded-xl border border-dashed border-border p-6"><p className="font-medium">해당 공모전을 찾을 수 없습니다.</p><p className="mt-1 text-sm text-muted-foreground">삭제되었거나 잘못된 링크일 수 있습니다.</p><Link href="/challenges" className="mt-3 inline-block text-sm underline">CHALLENGE 목록으로</Link></div>;
}

