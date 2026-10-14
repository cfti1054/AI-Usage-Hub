import type { MetadataRoute } from "next";

/** "홈 화면에 추가" 했을 때 앱처럼 열리게 하는 PWA 설정 (/manifest.webmanifest) */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "AI Usage Hub",
    short_name: "AI Hub",
    description: "AI 구독 및 사용량 통합 대시보드",
    start_url: "/",
    display: "standalone",
    background_color: "#FFFFFF",
    theme_color: "#FFFFFF",
    lang: "ko",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
