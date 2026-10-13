import { syncAllAction } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/ActionForm";
import { AutoRefresh } from "@/components/AutoRefresh";
import { CostDonut, DailyCostBars } from "@/components/charts";
import { ServiceCard } from "@/components/ServiceCard";
import { SummaryStats } from "@/components/SummaryStats";
import { api } from "@/lib/api";
import { fromNow, toNum } from "@/lib/format";
import type { DashboardSummary } from "@/lib/types";

export default async function DashboardPage() {
  const summary = await api<DashboardSummary>("/api/dashboard/summary");
  const enabled = summary.services.filter((s) => s.enabled);

  // 도넛: 서비스별 (월 구독료 + 이번 달 API 비용). 환산 불가 금액은 제외된다
  const donut = enabled
    .map((s) => ({ name: s.name, value: (toNum(s.subscription_monthly) ?? 0) + (toNum(s.month_api_cost) ?? 0) }))
    .filter((d) => d.value > 0);
  const daily = summary.daily_api_costs.map((d) => ({ label: d.date.slice(5).replace("-", "/"), value: toNum(d.amount) }));

  return (
    <>
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">대시보드</h1>
          <p className="text-sm text-slate-500">
            {summary.period} · 마지막 수집 {fromNow(summary.last_synced_at)} · 1분마다 자동 갱신
          </p>
          <AutoRefresh seconds={60} />
        </div>
        <ActionForm action={syncAllAction} className="flex items-center gap-2">
          <SubmitButton variant="secondary">새로고침</SubmitButton>
        </ActionForm>
      </header>

      <SummaryStats summary={summary} />

      <section>
        <h2 className="mb-2 text-sm font-medium text-slate-600">서비스별 사용 현황</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {summary.services.map((card) => (
            <ServiceCard key={card.id} card={card} currency={summary.currency} />
          ))}
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-medium text-slate-600">이번 달 비용 비중 (구독료 + API)</h2>
          <CostDonut data={donut} currency={summary.currency} />
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-medium text-slate-600">최근 7일 API 비용</h2>
          <DailyCostBars data={daily} currency={summary.currency} />
        </div>
      </section>

      <footer className="text-xs text-slate-500">
        다음 자동 수집 {summary.next_sync_at ? fromNow(summary.next_sync_at) : "— (스케줄러 꺼짐)"}
        {summary.fx &&
          ` · 환율 1 USD = ${toNum(summary.fx.usd_krw)} KRW (${summary.fx.rate_date ?? "기준일 미입력"} · ${summary.fx.source_label ?? ""})`}
      </footer>
    </>
  );
}
