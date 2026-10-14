"use client";

import { useActionState, useState } from "react";
import { createWidgetTokenAction, revokeWidgetTokenAction } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/ActionForm";
import { fromNow } from "@/lib/format";
import type { WidgetToken } from "@/lib/types";
import { buildWidgetScript } from "@/lib/widget-script";

const SCRIPTABLE_URL = "https://apps.apple.com/app/scriptable/id1405459188";

function ScriptGuide({ script }: { script: string }) {
  const [copied, setCopied] = useState(false);

  function download() {
    const url = URL.createObjectURL(new Blob([script], { type: "text/javascript" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "AI Hub.js";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm">
      <p className="font-medium text-amber-900">
        이 스크립트에는 위젯 토큰이 들어 있고, 지금 한 번만 표시됩니다. 복사하거나 파일로 받아 두세요.
      </p>
      <ol className="list-decimal space-y-1 pl-5 text-xs text-slate-700">
        <li>
          아이폰에{" "}
          <a href={SCRIPTABLE_URL} target="_blank" rel="noopener noreferrer" className="font-medium underline">
            Scriptable 앱(무료)
          </a>
          을 설치합니다.
        </li>
        <li>Scriptable에서 오른쪽 위 + 를 누르고 아래 스크립트를 붙여 넣은 뒤, 이름을 &ldquo;AI Hub&rdquo;로 저장합니다.</li>
        <li>홈 화면을 길게 눌러 왼쪽 위 + → Scriptable → 원하는 크기를 고르고 위젯을 추가합니다.</li>
        <li>추가한 위젯을 길게 눌러 &ldquo;위젯 편집&rdquo; → Script를 &ldquo;AI Hub&rdquo;로 고릅니다.</li>
        <li>잠금 화면: 잠금 화면을 길게 눌러 사용자화 → 위젯 추가 → Scriptable(원형·사각형·한 줄) → Script 선택.</li>
      </ol>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={async () => {
            await navigator.clipboard.writeText(script);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2000);
          }}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
        >
          {copied ? "복사됨" : "스크립트 복사"}
        </button>
        <button
          type="button"
          onClick={download}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-100"
        >
          파일로 받기
        </button>
      </div>
      <textarea
        readOnly
        value={script}
        rows={8}
        aria-label="위젯 스크립트"
        className="w-full rounded-md border border-slate-300 bg-white p-2 font-mono text-xs text-slate-700"
      />
    </div>
  );
}

export function WidgetManager({
  tokens,
  serverUrl,
  dashboardUrl,
}: {
  tokens: WidgetToken[];
  serverUrl: string;
  dashboardUrl: string;
}) {
  const [state, createAction, pending] = useActionState(createWidgetTokenAction, null);

  return (
    <div className="space-y-3">
      <ul className="divide-y divide-slate-100 text-sm">
        {tokens.map((t) => (
          <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <div className={t.revoked_at ? "opacity-60" : ""}>
              <p className="font-medium">
                {t.name}
                {t.revoked_at && <span className="ml-2 text-xs text-rose-600">폐기됨</span>}
              </p>
              <p className="text-xs text-slate-500">
                발급 {fromNow(t.created_at)} · 마지막 조회 {t.last_used_at ? fromNow(t.last_used_at) : "없음"}
              </p>
            </div>
            {!t.revoked_at && (
              <ActionForm action={revokeWidgetTokenAction}>
                <input type="hidden" name="token_id" value={t.id} />
                <SubmitButton variant="danger">토큰 폐기</SubmitButton>
              </ActionForm>
            )}
          </li>
        ))}
        {tokens.length === 0 && <li className="py-2 text-slate-500">발급한 위젯 토큰 없음</li>}
      </ul>

      <form action={createAction} className="flex flex-wrap items-center gap-2">
        <input name="name" required maxLength={50} placeholder="이름 (예: 내 아이폰)" className="input max-w-xs" />
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {pending ? "처리 중…" : "위젯 토큰 발급"}
        </button>
      </form>
      {state && !state.token && (
        <p className={`text-xs ${state.ok ? "text-emerald-600" : "text-rose-600"}`}>{state.message}</p>
      )}
      {state?.token && <ScriptGuide script={buildWidgetScript({ serverUrl, token: state.token, dashboardUrl })} />}
      <p className="text-xs text-slate-500">
        위젯 토큰은 이번 달 요약을 보는 것만 할 수 있습니다. 스크립트를 잃어버렸거나 휴대폰을 바꾸면 기존 토큰을 폐기하고 새로 발급하세요.
      </p>
    </div>
  );
}
