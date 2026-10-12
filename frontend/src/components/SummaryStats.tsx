import { formatMoney, formatPercent } from "@/lib/format";
import type { DashboardSummary } from "@/lib/types";

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {note && <p className="mt-1 text-xs text-slate-500">{note}</p>}
    </div>
  );
}

export function SummaryStats({ summary }: { summary: DashboardSummary }) {
  const missing = summary.conversion_missing ? "일부 금액 환율 미설정" : undefined;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat label="월 구독료 합계" value={formatMoney(summary.subscription_total, summary.currency)} note={missing} />
      <Stat
        label="연결된 서비스"
        value={`${summary.services_connected} / ${summary.services_total}`}
        note={
          summary.services_total > summary.services_connected
            ? `데이터 없음 ${summary.services_total - summary.services_connected}개`
            : undefined
        }
      />
      <Stat
        label="평균 사용률"
        value={formatPercent(summary.avg_usage_rate)}
        note={summary.avg_usage_rate === null ? "한도 정보가 있는 서비스 없음" : "한도 제공 서비스 기준"}
      />
      <Stat label="이번 달 API 비용" value={formatMoney(summary.api_cost_total, summary.currency)} note={missing} />
    </div>
  );
}
