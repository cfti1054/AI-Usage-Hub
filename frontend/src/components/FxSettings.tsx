"use client";

import { useState } from "react";
import { refreshFxAction, saveFxAction } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/ActionForm";
import type { UserSettings } from "@/lib/types";

const SOURCE_LABELS: Record<string, string> = {
  koreaexim: "한국수출입은행 매매기준율",
  frankfurter: "ECB 기준환율(Frankfurter)",
  manual: "직접 입력",
};

export function FxSettings({ settings }: { settings: UserSettings }) {
  const [mode, setMode] = useState(settings.fx_mode);
  const rate = settings.fx_usd_krw === null ? null : Number(settings.fx_usd_krw);

  return (
    <div className="space-y-3">
      <p className="text-sm">
        현재 적용 환율:{" "}
        {rate === null ? (
          <span className="text-rose-600">미설정 — USD 금액은 원화 합계에서 제외됩니다</span>
        ) : (
          <>
            <span className="font-semibold tabular-nums">1 USD = {rate.toLocaleString("ko-KR")} KRW</span>
            <span className="text-xs text-slate-500">
              {" "}
              · {settings.fx_rate_date} 기준 · {SOURCE_LABELS[settings.fx_source ?? ""] ?? settings.fx_source}
            </span>
          </>
        )}
      </p>

      <ActionForm action={saveFxAction} className="space-y-2">
        <div className="flex gap-4 text-sm">
          {(["auto", "manual"] as const).map((m) => (
            <label key={m} className="flex items-center gap-1.5">
              <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => setMode(m)} />
              {m === "auto" ? "자동 조회" : "직접 입력"}
            </label>
          ))}
        </div>
        {mode === "auto" ? (
          <p className="text-xs text-slate-500">
            6시간마다 자동 갱신합니다. 한국수출입은행 API 키가 설정돼 있으면 매매기준율을, 없거나 실패하면 ECB 기준환율을
            사용합니다. 조회에 실패하면 기존 환율을 유지합니다.
          </p>
        ) : (
          <div className="grid gap-2 md:grid-cols-3">
            <input
              name="fx_usd_krw"
              type="number"
              step="any"
              min="0"
              required
              placeholder="1 USD = ? KRW"
              defaultValue={rate ?? ""}
              className="input"
            />
            <input name="fx_rate_date" type="date" defaultValue={settings.fx_rate_date ?? ""} className="input" />
          </div>
        )}
        <SubmitButton>{mode === "auto" ? "자동 조회로 저장" : "직접 입력값 저장"}</SubmitButton>
      </ActionForm>

      {settings.fx_mode === "auto" && (
        <ActionForm action={refreshFxAction}>
          <SubmitButton variant="secondary">지금 다시 조회</SubmitButton>
        </ActionForm>
      )}
    </div>
  );
}
