/** 기기 상태 점: 온라인(초록) · 오프라인(회색) · 폐기(빨강) */
export function DeviceStatus({ online, revoked, withLabel = false }: { online: boolean; revoked: boolean; withLabel?: boolean }) {
  const [color, label] = revoked
    ? ["bg-rose-400", "폐기됨"]
    : online
      ? ["bg-emerald-500", "온라인"]
      : ["bg-slate-300", "오프라인"];
  return (
    <span className="inline-flex items-center gap-1" title={label}>
      <span className={`inline-block h-2 w-2 rounded-full ${color}`} />
      {withLabel && <span className="text-xs text-slate-500">{label}</span>}
    </span>
  );
}
