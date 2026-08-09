import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

// Pretendard - free, open-source (SIL OFL), and the de facto standard UI font for
// modern Korean products. Loaded as a single variable-weight file (next/font/local
// self-hosts it, no external font CDN request) since this app's UI is almost entirely
// Korean text - Geist Sans/Mono (the create-next-app default) have no Hangul coverage,
// so Korean text was always silently falling back to the OS default font regardless of
// what globals.css declared.
const pretendard = localFont({
  src: "../../node_modules/pretendard/dist/web/variable/woff2/PretendardVariable.woff2",
  variable: "--font-pretendard",
  weight: "45 920",
  display: "swap",
});

export const metadata: Metadata = {
  title: "BizRadar",
  description: "공공 IT 프로젝트와 정부지원사업을 발견하는 IT/SI 기업용 대시보드",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className={`${pretendard.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
