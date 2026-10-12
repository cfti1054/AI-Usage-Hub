import { differenceInCalendarDays, formatDistanceToNowStrict } from "date-fns";
import { ko } from "date-fns/locale";
import type { Num } from "./types";

export function toNum(value: Num | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** 금액이 없으면 0 이 아니라 "—" 를 보여준다 (기획서 핵심 원칙). */
export function formatMoney(value: Num | null | undefined, currency: string): string {
  const n = toNum(value);
  if (n === null) return "—";
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency,
    maximumFractionDigits: currency === "KRW" ? 0 : 2,
  }).format(n);
}

export function formatNumber(value: Num | null | undefined): string {
  const n = toNum(value);
  if (n === null) return "—";
  return new Intl.NumberFormat("ko-KR", { notation: n >= 100_000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n);
}

export function formatPercent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value)}%`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Seoul",
  }).format(new Date(iso));
}

export function fromNow(iso: string | null | undefined): string {
  if (!iso) return "—";
  return formatDistanceToNowStrict(new Date(iso), { addSuffix: true, locale: ko });
}

export function dday(isoDate: string | null | undefined): string | null {
  if (!isoDate) return null;
  const days = differenceInCalendarDays(new Date(isoDate), new Date());
  return days === 0 ? "D-day" : days > 0 ? `D-${days}` : `D+${-days}`;
}
