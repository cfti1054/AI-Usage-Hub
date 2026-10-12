import {
  createServiceAction,
  createSubscriptionAction,
  deleteCredentialAction,
  deleteSubscriptionAction,
  saveCredentialAction,
  saveSettingsAction,
  testConnectionAction,
  toggleServiceAction,
} from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/ActionForm";
import { FxSettings } from "@/components/FxSettings";
import { SourceBadge } from "@/components/SourceBadge";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { Service, Subscription, UserSettings } from "@/lib/types";

export default async function SettingsPage() {
  const [services, subscriptions, settings] = await Promise.all([
    api<Service[]>("/api/services"),
    api<Subscription[]>("/api/subscriptions"),
    api<UserSettings>("/api/settings"),
  ]);
  const names = Object.fromEntries(services.map((s) => [s.id, s.name]));

  return (
    <>
      <h1 className="text-xl font-semibold">설정</h1>

      <section className="panel space-y-3">
        <h2 className="text-sm font-medium text-slate-600">서비스</h2>
        {services.map((s) => (
          <div key={s.id} className="space-y-2 border-t border-slate-100 pt-3 first:border-0 first:pt-0">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-2 font-medium">
                {s.name} <SourceBadge source={s.collection_method} />
                {!s.enabled && <span className="text-xs text-slate-400">비활성</span>}
              </p>
              <ActionForm action={toggleServiceAction}>
                <input type="hidden" name="service_id" value={s.id} />
                <input type="hidden" name="enabled" value={String(!s.enabled)} />
                <SubmitButton variant="secondary">{s.enabled ? "비활성화" : "활성화"}</SubmitButton>
              </ActionForm>
            </div>
            {s.connector_available ? (
              <div className="flex flex-wrap items-start gap-2">
                <ActionForm action={saveCredentialAction} className="flex flex-1 flex-wrap items-center gap-2">
                  <input type="hidden" name="service_id" value={s.id} />
                  <input
                    name="secret"
                    type="password"
                    autoComplete="off"
                    placeholder={s.credential_hint ?? "API 키"}
                    className="input max-w-xs"
                  />
                  <SubmitButton>저장</SubmitButton>
                </ActionForm>
                <ActionForm action={testConnectionAction}>
                  <input type="hidden" name="service_id" value={s.id} />
                  <SubmitButton variant="secondary">연결 테스트</SubmitButton>
                </ActionForm>
                {s.has_credential && (
                  <ActionForm action={deleteCredentialAction}>
                    <input type="hidden" name="service_id" value={s.id} />
                    <SubmitButton variant="danger">키 삭제</SubmitButton>
                  </ActionForm>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                자동 수집 커넥터 없음 — 서비스 상세 화면에서 사용량·비용을 수동 입력합니다.
              </p>
            )}
          </div>
        ))}

        <details className="border-t border-slate-100 pt-3">
          <summary className="cursor-pointer text-sm text-slate-600">서비스 추가</summary>
          <ActionForm action={createServiceAction} className="mt-2 grid gap-2 md:grid-cols-5">
            <input name="id" required placeholder="ID (예: copilot)" pattern="[a-z0-9][a-z0-9-]{1,40}" className="input" />
            <input name="name" required placeholder="이름" className="input" />
            <input name="provider" required placeholder="제공사" className="input" />
            <select name="collection_method" className="input" defaultValue="manual">
              <option value="manual">수동</option>
              <option value="cli">CLI</option>
              <option value="api">API</option>
            </select>
            <SubmitButton>추가</SubmitButton>
          </ActionForm>
        </details>
      </section>

      <section className="panel space-y-3">
        <h2 className="text-sm font-medium text-slate-600">구독 정보</h2>
        <ul className="space-y-1 text-sm">
          {subscriptions.map((sub) => (
            <li key={sub.id} className="flex flex-wrap items-center justify-between gap-2">
              <span>
                {names[sub.service_id] ?? sub.service_id} · {sub.plan_name} · {formatMoney(sub.price, sub.currency)}/
                {sub.billing_cycle === "annual" ? "년" : "월"}
                {sub.renewal_date && ` · 갱신일 ${sub.renewal_date}`}
              </span>
              <ActionForm action={deleteSubscriptionAction}>
                <input type="hidden" name="id" value={sub.id} />
                <SubmitButton variant="danger">삭제</SubmitButton>
              </ActionForm>
            </li>
          ))}
          {subscriptions.length === 0 && <li className="text-slate-500">등록된 구독 없음</li>}
        </ul>
        <ActionForm action={createSubscriptionAction} className="grid gap-2 md:grid-cols-7">
          <select name="service_id" className="input" required>
            {services.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <input name="plan_name" required placeholder="요금제 (예: Pro)" className="input" />
          <input name="price" required type="number" step="any" min="0" placeholder="가격" className="input" />
          <select name="currency" className="input" defaultValue="USD">
            <option>USD</option>
            <option>KRW</option>
          </select>
          <select name="billing_cycle" className="input" defaultValue="monthly">
            <option value="monthly">월간</option>
            <option value="annual">연간</option>
          </select>
          <input name="renewal_date" type="date" className="input" />
          <SubmitButton>추가</SubmitButton>
        </ActionForm>
      </section>

      <section className="panel">
        <h2 className="mb-3 text-sm font-medium text-slate-600">환율 (USD → KRW)</h2>
        <FxSettings settings={settings} />
      </section>

      <section className="panel">
        <h2 className="mb-3 text-sm font-medium text-slate-600">표시 · 알림 · 수집</h2>
        <ActionForm action={saveSettingsAction} className="grid gap-3 md:grid-cols-3">
          <label className="text-xs text-slate-500">
            표시 통화
            <select name="currency" defaultValue={settings.currency} className="input mt-1">
              <option>KRW</option>
              <option>USD</option>
            </select>
          </label>
          <label className="text-xs text-slate-500">
            시간대
            <input name="timezone" defaultValue={settings.timezone} className="input mt-1" />
          </label>
          <label className="text-xs text-slate-500">
            알림 임계치 (%)
            <input name="alert_threshold" type="number" min={1} max={100} defaultValue={settings.alert_threshold} className="input mt-1" />
          </label>
          <label className="text-xs text-slate-500">
            수집 주기 (분)
            <input name="sync_interval_minutes" type="number" min={15} max={1440} defaultValue={settings.sync_interval_minutes} className="input mt-1" />
          </label>
          <div>
            <SubmitButton>저장</SubmitButton>
          </div>
        </ActionForm>
      </section>
    </>
  );
}
