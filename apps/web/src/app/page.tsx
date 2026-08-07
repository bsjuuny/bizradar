import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col items-center justify-center gap-6 px-4 text-center">
      <h1 className="text-3xl font-semibold tracking-tight">BizRadar</h1>
      <p className="max-w-md text-muted-foreground">
        IT/SI 기업을 위한 공공 IT 프로젝트·정부지원사업 발견 및 시장 분석 도구
      </p>
      <div className="flex gap-3">
        <Link href="/signup" className={buttonVariants({ size: "lg" })}>
          회원가입
        </Link>
        <Link href="/login" className={buttonVariants({ variant: "outline", size: "lg" })}>
          로그인
        </Link>
      </div>
    </main>
  );
}
