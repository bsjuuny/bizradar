import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-border p-6 text-sm">
      <p className="font-medium">해당 지원사업을 찾을 수 없습니다.</p>
      <p className="text-muted-foreground">삭제되었거나 잘못된 링크일 수 있습니다.</p>
      <Link href="/support" className="underline">
        Support Radar 목록으로
      </Link>
    </div>
  );
}
