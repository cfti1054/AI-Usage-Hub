import Link from "next/link";
import { dday, formatDateTime, formatMoney, formatNumber, formatPercent, fromNow } from "@/lib/format";
import type { DataState, ServiceCardData } from "@/lib/types";
import { DeviceStatus } from "./DeviceStatus";
import { SourceBadge } from "./SourceBadge";

const METRIC_LABELS: Record<string, string> = {
  tokens_day: "오늘 토큰",
};

const STATE_MESSAGE: Record<Exclude<DataState, "ok">, string> = {
  no_data: "데이터 없음 — 아직 수집되거나 입력된 사용량이 없습니다",
  unavailable: "수집 불가 — 이 서비스는 해당 지표를 제공하지 않습니다",
  error: "수집 실패",
  disabled: "비활성화된 서비스",
};

export function ServiceCard({
  card,
  currency,
  monthLabel = "이번 달",
}: {
  card: ServiceCardData;
  currency: string;
  monthLabel?: string;
}) {
  const sub = card.subscription;
  const renewal = dday(sub?.renewal_date);
  const isError = card.data_state === "error";

  return (
    <Link
      href={`/services/${card.id}`}
      className={`block rounded-lg border bg-white p-4 transition hover:shadow-sm ${
        isError ? "border-rose-300" : "border-slate-200"
      } ${card.enabled ? "" : "opacity-60"}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{card.name}</p>
          <p className="text-xs text-slate-500">
            {sub ? `${sub.plan_name} · ${formatMoney(sub.price, sub.currency)}/${sub.billing_cycle === "annual" ? "년" : "월"}` : "구독 정보 없음"}
          </p>
        </div>
        <SourceBadge source={card.usage?.source_type ?? card.collection_method} />
      </div>

      <div className="mt-3">
        {card.data_state === "ok" && card.usage ? (
          <>
            <div className="flex items-baseline justify-between text-sm">
              <span className="text-slate-600">{card.usage.metric_code === "tokens_month" ? `${monthLabel} 토큰` : (METRIC_LABELS[card.usage.metric_code] ?? card.usage.metric_code)}</span>
              <span className="font-medium tabular-nums">
                {card.usage_rate !== null
                  ? formatPercent(card.usage_rate)
                  : `${formatNumber(card.usage.used_value)} ${card.usage.unit ?? ""}`}
              </span>
            </div>
            {card.usage_rate !== null && (
              <div className="mt-1 h-1.5 rounded-full bg-slate-100">
                <div
                  className="h-1.5 rounded-full bg-slate-800"
                  style={{ width: `${Math.min(100, card.usage_rate)}%` }}
                />
              </div>
            )}
          </>
        ) : (
          <p className={`text-sm ${isError ? "text-rose-600" : "text-slate-500"}`}>
            {STATE_MESSAGE[card.data_state as Exclude<DataState, "ok">]}
            {isError && card.last_sync?.error_message ? `: ${card.last_sync.error_message}` : ""}
          </p>
        )}
      </div>

      {card.devices.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-slate-600">
          {card.devices.map((d) => (
            <li key={d.kind === "csv" ? "csv" : d.device_id} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5">
                {d.kind === "csv" ? <span className="rounded bg-amber-50 px-1 text-[10px] text-amber-700 ring-1 ring-amber-200">CSV</span> : <DeviceStatus online={d.online} revoked={d.revoked} />} {d.name}
              </span>
              <span className="tabular-nums">{formatNumber(d.used_value)}</span>
            </li>
          ))}
        </ul>
      )}

      <dl className="mt-3 space-y-0.5 text-xs text-slate-500">
        {card.month_api_cost !== null && (
          <div className="flex justify-between">
            <dt>{monthLabel} API 비용</dt>
            <dd className="tabular-nums text-slate-700">{formatMoney(card.month_api_cost, currency)}</dd>
          </div>
        )}
        {(renewal || card.usage?.resets_at) && (
          <div>
            {renewal && `갱신 ${renewal}`}
            {renewal && card.usage?.resets_at && " · "}
            {card.usage?.resets_at && `다음 초기화 ${formatDateTime(card.usage.resets_at)}`}
          </div>
        )}
        <div>
          {card.usage ? `마지막 갱신 ${fromNow(card.usage.captured_at)}` : "갱신 기록 없음"}
          {card.stale && <span className="ml-1 text-amber-600">(오래된 데이터)</span>}
        </div>
      </dl>
    </Link>
  );
}
