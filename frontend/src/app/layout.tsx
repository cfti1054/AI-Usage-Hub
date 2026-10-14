import type { Metadata, Viewport } from "next";
import "./globals.css";

// 파비콘(icon.svg, favicon.ico)과 아이폰 아이콘(apple-icon.png)은 app 폴더의 파일로 자동 연결된다.
// 아이콘을 바꿀 때는 scripts/generate_icons.py 를 다시 실행한다.
export const metadata: Metadata = {
  title: "AI Usage Hub",
  description: "AI 구독 및 사용량 통합 대시보드",
  applicationName: "AI Hub",
  appleWebApp: { capable: true, title: "AI Hub", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: "#FFFFFF",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
