"use client";

import { useActionState, useEffect, useState } from "react";
import { createDeviceAction, revokeDeviceAction, rotateDeviceTokenAction } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/ActionForm";
import { DeviceStatus } from "@/components/DeviceStatus";
import { formatNumber, fromNow } from "@/lib/format";
import type { Device } from "@/lib/types";

const SERVICE_LABELS: Record<string, string> = { "claude-code": "Claude Code", codex: "Codex" };
const TOKEN_PLACEHOLDER = "<기기 토큰>";

type Os = "windows" | "macos";

function setupCommands(os: Os, serverUrl: string, token: string): { config: string; install: string } {
  if (os === "windows") {
    return {
      config: [
        `[Environment]::SetEnvironmentVariable("AIHUB_URL", "${serverUrl}", "User")`,
        `[Environment]::SetEnvironmentVariable("AIHUB_DEVICE_TOKEN", "${token}", "User")`,
      ].join("\n"),
      install: ["cd <저장소 경로>\\backend", "powershell -ExecutionPolicy Bypass -File .\\collector\\install-agent.ps1"].join("\n"),
    };
  }
  return {
    config: [
      "mkdir -p ~/.aihub && (umask 077; cat > ~/.aihub/agent.env <<'EOF'",
      `AIHUB_URL=${serverUrl}`,
      `AIHUB_DEVICE_TOKEN=${token}`,
      "EOF",
      ")",
    ].join("\n"),
    install: ["cd <저장소 경로>/backend", "sh collector/install-agent.sh"].join("\n"),
  };
}

function CommandBlock({ title, text }: { title: string; text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-slate-700">{title}</p>
        <button
          type="button"
          className="rounded border border-slate-300 bg-white px-2 py-0.5 text-xs hover:bg-slate-100"
          onClick={async () => {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2000);
          }}
        >
          {copied ? "복사됨" : "복사"}
        </button>
      </div>
      <pre className="overflow-x-auto rounded bg-white p-2 text-xs ring-1 ring-slate-200">{text}</pre>
    </div>
  );
}

/** OS별 설치 안내. token 이 있으면 실제 토큰을, 없으면 자리표시자를 넣는다. */
function SetupGuide({ serverUrl, token }: { serverUrl: string; token?: string }) {
  // 서버 렌더링과 어긋나지 않도록 Windows 로 시작하고, 마운트 후 Mac 이면 macOS 탭으로 바꾼다
  const [os, setOs] = useState<Os>("windows");
  useEffect(() => {
    if (/Mac/i.test(navigator.userAgent)) setOs("macos");
  }, []);
  const { config, install } = setupCommands(os, serverUrl, token ?? TOKEN_PLACEHOLDER);
  const shell = os === "windows" ? "PowerShell" : "터미널";

  return (
    <div className={`space-y-3 rounded-md border p-3 text-sm ${token ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-slate-50"}`}>
      {token && (
        <p className="font-medium text-amber-900">
          기기 토큰은 지금 한 번만 표시됩니다. 이 창을 닫기 전에 등록할 PC에서 아래 명령을 실행하세요.
        </p>
      )}
      <div className="flex gap-1" role="tablist">
        {(["windows", "macos"] as const).map((o) => (
          <button
            key={o}
            type="button"
            role="tab"
            aria-selected={os === o}
            onClick={() => setOs(o)}
            className={`rounded-md px-3 py-1 text-xs font-medium ${os === o ? "bg-slate-900 text-white" : "bg-white ring-1 ring-slate-300 hover:bg-slate-100"}`}
          >
            {o === "windows" ? "Windows" : "macOS"}
          </button>
        ))}
      </div>
      <CommandBlock title={`1. 서버 주소와 기기 토큰 저장 (${shell})`} text={config} />
      <CommandBlock title="2. 에이전트 설치 — 로그인 시 자동 실행, 지금 바로 시작" text={install} />
      <ul className="list-disc space-y-0.5 pl-4 text-xs text-slate-600">
        <li>
          필요한 것: 이 저장소(최소 <code>backend/collector</code> 폴더)와{" "}
          <a href="https://docs.astral.sh/uv/" target="_blank" rel="noreferrer" className="underline">
            uv
          </a>
          . <code>&lt;저장소 경로&gt;</code>는 그 PC에 받은 저장소 위치로 바꾸세요.
        </li>
        <li>
          실행 기록: {os === "windows" ? <code>%USERPROFILE%\.aihub\agent.log</code> : <code>~/.aihub/agent.log</code>}
        </li>
        <li>
          {os === "windows" ? (
            <>
              삭제: <code>.\collector\install-agent.ps1 -Uninstall</code>
            </>
          ) : (
            <>
              삭제: <code>sh collector/install-agent.sh --uninstall</code>
            </>
          )}
        </li>
        <li>토큰을 재발급했다면 1번 명령을 새 토큰으로 다시 실행한 뒤 2번(설치)을 다시 실행하면 새 토큰으로 바뀝니다.</li>
      </ul>
    </div>
  );
}

function DeviceRow({ device, serverUrl }: { device: Device; serverUrl: string }) {
  const [state, rotateAction, pending] = useActionState(rotateDeviceTokenAction, null);
  const revoked = !!device.revoked_at;

  return (
    <li className="space-y-2 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className={revoked ? "opacity-60" : ""}>
          <p className="flex items-center gap-2 font-medium">
            <DeviceStatus online={device.online} revoked={revoked} withLabel /> {device.name}
          </p>
          <p className="text-xs text-slate-500">
            마지막 신호 {fromNow(device.last_seen_at)}
            {Object.entries(device.month_usage).map(([sid, v]) => ` · ${SERVICE_LABELS[sid] ?? sid} ${formatNumber(v)}`)}
          </p>
        </div>
        {!revoked && (
          <div className="flex gap-2">
            <form
              action={rotateAction}
              onSubmit={(e) => {
                if (!window.confirm(`"${device.name}"의 토큰을 재발급할까요? 이전 토큰은 즉시 쓸 수 없게 됩니다.`)) e.preventDefault();
              }}
            >
              <input type="hidden" name="device_id" value={device.id} />
              <button
                type="submit"
                disabled={pending}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-100 disabled:opacity-50"
              >
                {pending ? "처리 중…" : "토큰 재발급"}
              </button>
            </form>
            <ActionForm action={revokeDeviceAction}>
              <input type="hidden" name="device_id" value={device.id} />
              <SubmitButton variant="danger">토큰 폐기</SubmitButton>
            </ActionForm>
          </div>
        )}
      </div>
      {state && !state.ok && <p className="text-xs text-rose-600">{state.message}</p>}
      {state?.token && <SetupGuide serverUrl={serverUrl} token={state.token} />}
    </li>
  );
}

export function DeviceManager({ devices, serverUrl }: { devices: Device[]; serverUrl: string }) {
  const [state, createAction, pending] = useActionState(createDeviceAction, null);

  return (
    <div className="space-y-3">
      <ul className="divide-y divide-slate-100 text-sm">
        {devices.map((d) => (
          <DeviceRow key={d.id} device={d} serverUrl={serverUrl} />
        ))}
        {devices.length === 0 && <li className="py-2 text-slate-500">등록된 기기 없음</li>}
      </ul>

      <form action={createAction} className="flex flex-wrap items-center gap-2">
        <input name="name" required maxLength={50} placeholder="기기 이름 (예: 집 데스크톱, 맥북)" className="input max-w-xs" />
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {pending ? "처리 중…" : "기기 등록"}
        </button>
      </form>
      {state && !state.token && (
        <p className={`text-xs ${state.ok ? "text-emerald-600" : "text-rose-600"}`}>{state.message}</p>
      )}
      {state?.token && <SetupGuide serverUrl={serverUrl} token={state.token} />}

      <details className="text-sm">
        <summary className="cursor-pointer text-slate-600">설치 방법 보기 (Windows / macOS)</summary>
        <div className="mt-2 space-y-2">
          <p className="text-xs text-slate-500">
            토큰은 보안을 위해 서버에 해시로만 저장되어 다시 볼 수 없습니다. 이미 등록한 기기의 토큰이 필요하면 해당 기기의{" "}
            <b>토큰 재발급</b>을 누르세요. 사용량 기록은 그대로 유지됩니다.
          </p>
          <SetupGuide serverUrl={serverUrl} />
        </div>
      </details>
    </div>
  );
}
