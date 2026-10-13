/** 'YYYY-MM' 기간 다루기 */

export const PERIOD_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

export function shiftPeriod(period: string, months: number): string {
  const [y, m] = period.split("-").map(Number);
  const index = y * 12 + (m - 1) + months;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

export function periodLabel(period: string): string {
  const [y, m] = period.split("-");
  return `${y}년 ${Number(m)}월`;
}
