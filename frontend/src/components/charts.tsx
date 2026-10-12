"use client";

import { Bar, BarChart, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const PALETTE = ["#d97757", "#10a37f", "#f5a524", "#4285f4", "#8b5cf6", "#64748b", "#ec4899"];

const money = (currency: string) => (v: unknown) =>
  typeof v === "number"
    ? new Intl.NumberFormat("ko-KR", { style: "currency", currency, maximumFractionDigits: currency === "KRW" ? 0 : 2 }).format(v)
    : "—";

export function CostDonut({ data, currency }: { data: { name: string; value: number }[]; currency: string }) {
  if (data.length === 0) return <Empty text="비용 데이터 없음" />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2}>
          {data.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
          ))}
        </Pie>
        <Tooltip formatter={money(currency)} />
        <Legend verticalAlign="middle" align="right" layout="vertical" iconSize={8} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function DailyCostBars({ data, currency }: { data: { label: string; value: number | null }[]; currency: string }) {
  if (data.every((d) => d.value === null)) return <Empty text="최근 7일 일별 API 비용 없음" />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data}>
        <XAxis dataKey="label" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} width={60} />
        <Tooltip formatter={money(currency)} />
        <Bar dataKey="value" name="API 비용" fill="#4285f4" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function MonthlyStackedBars({
  data,
  services,
  currency,
}: {
  data: Record<string, number | string | null>[];
  services: { id: string; name: string }[];
  currency: string;
}) {
  if (services.length === 0) return <Empty text="최근 12개월 API 비용 기록 없음" />;
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data}>
        <XAxis dataKey="period" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} width={70} />
        <Tooltip formatter={money(currency)} />
        <Legend iconSize={8} />
        {services.map((s, i) => (
          <Bar key={s.id} dataKey={s.id} name={s.name} stackId="cost" fill={PALETTE[i % PALETTE.length]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="flex h-[220px] items-center justify-center text-sm text-slate-400">{text}</div>;
}
