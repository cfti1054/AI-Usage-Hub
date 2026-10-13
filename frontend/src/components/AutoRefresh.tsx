"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** 서버 컴포넌트 데이터를 주기적으로 다시 받아온다. 탭이 보이지 않을 때는 쉬고, 돌아오면 바로 갱신한다. */
export function AutoRefresh({ seconds = 60 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible") router.refresh();
    };
    const id = window.setInterval(refresh, seconds * 1000);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [router, seconds]);
  return null;
}
