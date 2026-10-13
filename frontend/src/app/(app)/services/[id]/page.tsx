import { notFound } from "next/navigation";
import { manualEntryAction, syncServiceAction, testConnectionAction } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/ActionForm";
import { AutoRefresh } from "@/components/AutoRefresh";
import { DeviceStatus } from "@/components/DeviceStatus";
import { SourceBadge } from "@/components/SourceBadge";
import { api, ApiError } from "@/lib/api";
import { formatDateTime, formatMoney, formatNumber } from "@/lib/format";
import { CsvImportPanel } from "@/components/CsvImportPanel";
import type { ServiceUsage, UsageImport } from "@/lib/types";

export default async function ServiceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await api<ServiceUsage>(`/api/services/${encodeURIComponent(id)}/usage?days=90`).catch((e) => {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  });
  const { service } = data;
  const thisMonth = new Date().toISOString().slice(0, 7);
  const imports = data.csv_import_supported
    ? await api<UsageImport[]>(`/api/services/${encodeURIComponent(id)}/usage-imports`)
    : [];

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            {service.name} <SourceBadge source={service.collection_method} />
          </h1>
          <p className="text-sm text-slate-500">{service.provider}</p>
        </div>
        {service.connector_available && (
          <div className="flex gap-2">
            <ActionForm action={testConnectionAction}>
              <input type="hidden" name="service_id" value={service.id} />
              <SubmitButton variant="secondary">연결 테스트</SubmitButton>
            </ActionForm>
            <ActionForm action={syncServiceAction}>
              <input type="hidden" name="service_id" value={service.id} />
              <SubmitButton>지금 수집</SubmitButton>
            </ActionForm>
          </div>
        )}
      </header>

      <AutoRefresh seconds={60} />
      {data.csv_import_supported && <CsvImportPanel serviceId={service.id} imports={imports} />}

      {data.token_months.length > 0 && (
        <section className="panel">
          <h2 className="mb-2 text-sm font-medium text-slate-600">월별 토큰 사용량 (최근 12개월)</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500">
                <tr>
                  <th className="py-1">월</th>
                  <th className="text-right">합계</th>
                  <th className="text-right">입력</th>
                  <th className="text-right">출력</th>
                  <th className="text-right">캐시 생성</th>
                  <th className="text-right">캐시 읽기</th>
                  <th className="text-right">출처</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {data.token_months.map((m) => (
                  <tr key={m.period} className="border-t border-slate-100">
                    <td className="py-1.5">{m.period}</td>
                    <td className="text-right font-medium">{m.total.toLocaleString("ko-KR")}</td>
                    <td className="text-right">{m.input.toLocaleString("ko-KR")}</td>
                    <td className="text-right">{m.output.toLocaleString("ko-KR")}</td>
                    <td className="text-right">{m.cache_creation.toLocaleString("ko-KR")}</td>
                    <td className="text-right">{m.cache_read.toLocaleString("ko-KR")}</td>
                    <td className="text-right text-xs text-slate-500">
                      {[m.devices ? "기기" : null, m.csv ? "CSV" : null].filter(Boolean).join(" + ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {data.devices.length > 0 && (
        <section className="panel">
          <h2 className="mb-2 text-sm font-medium text-slate-600">기기별 이번 달 토큰 사용량</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500">
                <tr>
                  <th className="py-1">기기</th>
                  <th>합계</th>
                  <th>입력</th>
                  <th>출력</th>
                  <th>캐시 생성</th>
                  <th>캐시 읽기</th>
                  <th>마지막 업로드</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {data.devices.map((d) => (
                  <tr key={d.device_id} className="border-t border-slate-100">
                    <td className="py-1.5">
                      <span className="flex items-center gap-1.5">
                        <DeviceStatus online={d.online} revoked={d.revoked} /> {d.name}
                      </span>
                    </td>
                    <td>{formatNumber(d.used_value)}</td>
                    <td>{formatNumber(d.breakdown?.input ?? null)}</td>
                    <td>{formatNumber(d.breakdown?.output ?? null)}</td>
                    <td>{formatNumber(d.breakdown?.cache_creation ?? null)}</td>
                    <td>{formatNumber(d.breakdown?.cache_read ?? null)}</td>
                    <td>{formatDateTime(d.captured_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="panel">
        <h2 className="mb-2 text-sm font-medium text-slate-600">최신 지표 (수동 입력·API)</h2>
        {data.latest.length === 0 ? (
          <p className="text-sm text-slate-500">데이터 없음</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500">
              <tr>
                <th className="py-1">지표</th>
                <th>사용량</th>
                <th>한도</th>
                <th>다음 초기화</th>
                <th>출처</th>
                <th>갱신 시각</th>
              </tr>
            </thead>
            <tbody>
              {data.latest.map((s) => (
                <tr key={s.id} className="border-t border-slate-100">
                  <td className="py-1.5">{s.metric_code}</td>
                  <td className="tabular-nums">{s.status === "ok" ? `${formatNumber(s.used_value)} ${s.unit ?? ""}` : "수집 불가"}</td>
                  <td className="tabular-nums">{formatNumber(s.limit_value)}</td>
                  <td>{formatDateTime(s.resets_at)}</td>
                  <td><SourceBadge source={s.source_type} /></td>
                  <td>{formatDateTime(s.captured_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <h2 className="mb-2 text-sm font-medium text-slate-600">수동 입력 / 보정</h2>
        <ActionForm action={manualEntryAction} className="grid gap-2 md:grid-cols-4">
          <input type="hidden" name="service_id" value={service.id} />
          <input name="metric_code" placeholder="지표 (예: credits)" className="input" />
          <input name="used_value" type="number" step="any" placeholder="사용량" className="input" />
          <input name="limit_value" type="number" step="any" placeholder="한도 (선택)" className="input" />
          <input name="unit" placeholder="단위 (선택)" className="input" />
          <input name="amount" type="number" step="any" placeholder="월 비용 (선택)" className="input" />
          <select name="currency" className="input" defaultValue="KRW">
            <option>KRW</option>
            <option>USD</option>
          </select>
          <input name="billing_period" type="month" defaultValue={thisMonth} className="input" />
          <SubmitButton>저장</SubmitButton>
        </ActionForm>
      </section>

      <section className="panel">
        <h2 className="mb-2 text-sm font-medium text-slate-600">비용 기록</h2>
        {data.costs.length === 0 ? (
          <p className="text-sm text-slate-500">데이터 없음</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {data.costs.map((c) => (
              <li key={`${c.cost_date}-${c.granularity}-${c.source_type}`} className="flex justify-between">
                <span>
                  {c.granularity === "month" ? c.cost_date.slice(0, 7) : c.cost_date} <SourceBadge source={c.source_type as "api"} />
                </span>
                <span className="tabular-nums">{formatMoney(c.amount, c.currency)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <h2 className="mb-2 text-sm font-medium text-slate-600">수집 이력</h2>
        {data.recent_jobs.length === 0 ? (
          <p className="text-sm text-slate-500">수집 이력 없음</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {data.recent_jobs.map((j) => (
              <li key={j.id} className="flex flex-wrap justify-between gap-2">
                <span>
                  {formatDateTime(j.started_at)} · {j.trigger === "schedule" ? "자동" : "수동"}
                </span>
                <span className={j.status === "success" ? "text-emerald-600" : "text-rose-600"}>
                  {j.status === "success" ? `성공 (${j.records_count}건)` : `${j.status}: ${j.error_message ?? ""}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
