import type { SourceType } from "@/lib/types";

const LABELS: Record<SourceType, { label: string; className: string }> = {
  api: { label: "API", className: "bg-blue-50 text-blue-700 ring-blue-200" },
  cli: { label: "CLI", className: "bg-violet-50 text-violet-700 ring-violet-200" },
  manual: { label: "수동", className: "bg-amber-50 text-amber-700 ring-amber-200" },
};

/** 데이터가 어떤 방식으로 들어오는지 항상 노출한다 (기획서 6장). */
export function SourceBadge({ source }: { source: SourceType }) {
  const { label, className } = LABELS[source];
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ring-1 ${className}`}>{label}</span>;
}
