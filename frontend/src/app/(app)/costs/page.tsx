import { MonthlyStackedBars } from "@/components/charts";
import { api } from "@/lib/api";
import { formatMoney, toNum } from "@/lib/format";
import type { CostsReport, CostTrend, Service } from "@/lib/types";

export default async function CostsPage({ searchParams }: { searchParams: Promise<{ period?: string }> }) {
  const { period } = await searchParams;
  const query = period && /^\d{4}-\d{2}$/.test(period) ? `?period=${period}` : "";
  const [report, trend, services] = await Promise.all([
    api<CostsReport>(`/api/costs${query}`),
    api<CostTrend>("/api/costs/trend?months=12"),
    api<Service[]>("/api/services"),
  ]);

  const names = Object.fromEntries(services.map((s) => [s.id, s.name]));
  const trendServiceIds = [...new Set(trend.months.flatMap((m) => Object.keys(m.by_service)))];
  const chartData = trend.months.map((m) => ({
    period: m.period,
    ...Object.fromEntries(Object.entries(m.by_service).map(([k, v]) => [k, toNum(v)])),
  }));

  return (
    <>
      <header className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-xl font-semibold">비용 분석</h1>
        <form className="flex gap-2">
          <input type="month" name="period" defaultValue={report.period} className="input" />
          <button className="rounded-md border border-slate-300 bg-white px-3 text-sm">조회</button>
        </form>
      </header>

      {report.conversion_missing && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          환율이 없어 일부 금액이 합계에서 제외되었습니다. 설정에서 환율 자동 조회를 실행하거나 직접 입력하세요.
        </p>
      )}

      <section className="grid gap-3 md:grid-cols-2">
        <div className="panel">
          <h2 className="text-sm font-medium text-slate-600">구독료 (월 환산)</h2>
          <p className="mt-1 text-2xl font-semibold">{formatMoney(report.subscription_total, report.currency)}</p>
          <ul className="mt-3 space-y-1 text-sm">
            {report.subscriptions.map((s) => (
              <li key={`${s.service_id}-${s.plan_name}`} className="flex justify-between gap-2">
                <span>
                  {s.service_name} · {s.plan_name}
                </span>
                <span className="tabular-nums">
                  {formatMoney(s.price, s.currency)}
                  {s.billing_cycle === "annual" ? "/년" : "/월"}
                  {s.currency !== report.currency && ` → ${formatMoney(s.monthly_converted, report.currency)}`}
                </span>
              </li>
            ))}
            {report.subscriptions.length === 0 && <li className="text-slate-500">등록된 구독 없음</li>}
          </ul>
        </div>
        <div className="panel">
          <h2 className="text-sm font-medium text-slate-600">API 종량제 비용 ({report.period})</h2>
          <p className="mt-1 text-2xl font-semibold">{formatMoney(report.api_cost_total, report.currency)}</p>
          <ul className="mt-3 space-y-1 text-sm">
            {report.api_costs.map((c) => (
              <li key={c.service_id} className="flex justify-between gap-2">
                <span>{c.service_name}</span>
                <span className="tabular-nums">
                  {Object.entries(c.original)
                    .map(([cur, amt]) => formatMoney(amt, cur))
                    .join(" + ")}
                  {Object.keys(c.original).some((cur) => cur !== report.currency) &&
                    ` → ${formatMoney(c.converted, report.currency)}`}
                </span>
              </li>
            ))}
            {report.api_costs.length === 0 && <li className="text-slate-500">데이터 없음</li>}
          </ul>
        </div>
      </section>

      <p className="text-xs text-slate-500">
        {report.fx
          ? `환산 기준: 1 USD = ${toNum(report.fx.usd_krw)} KRW (${report.fx.rate_date ?? "기준일 미입력"} 기준 · ${report.fx.source_label ?? ""})`
          : "환율 미설정"}
        {" · "}서비스마다 측정 단위가 달라 구독료 대비 사용량 비교는 비용 효율 추정치입니다.
      </p>

      <section className="panel">
        <h2 className="text-sm font-medium text-slate-600">최근 12개월 API 비용 추이</h2>
        <MonthlyStackedBars
          data={chartData}
          services={trendServiceIds.map((id) => ({ id, name: names[id] ?? id }))}
          currency={trend.currency}
        />
      </section>
    </>
  );
}
