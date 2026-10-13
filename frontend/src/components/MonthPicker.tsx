import Form from "next/form";
import Link from "next/link";
import { shiftPeriod } from "@/lib/period";

const navButton =
  "inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-300 bg-white text-sm hover:bg-slate-100";

/** 대시보드 월 선택: ◀ 이전 달 · 월 입력 · 다음 달 ▶ · 이번 달로. 미래 달로는 이동하지 않는다. */
export function MonthPicker({ period, current }: { period: string; current: string }) {
  const prev = shiftPeriod(period, -1);
  const next = shiftPeriod(period, 1);
  const canNext = next <= current;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Link href={`/?period=${prev}`} className={navButton} aria-label="이전 달">
        ◀
      </Link>
      <Form action="/" className="flex items-center gap-1.5">
        <input
          key={period}
          type="month"
          name="period"
          defaultValue={period}
          max={current}
          required
          aria-label="조회할 월"
          className="input h-8 w-40"
        />
        <button type="submit" className="h-8 rounded-md border border-slate-300 bg-white px-3 text-sm hover:bg-slate-100">
          보기
        </button>
      </Form>
      {canNext ? (
        <Link href={next === current ? "/" : `/?period=${next}`} className={navButton} aria-label="다음 달">
          ▶
        </Link>
      ) : (
        <span className={`${navButton} cursor-not-allowed opacity-40`} aria-disabled="true">
          ▶
        </span>
      )}
      {period !== current && (
        <Link href="/" className="h-8 rounded-md bg-slate-900 px-3 text-sm leading-8 text-white hover:bg-slate-700">
          이번 달
        </Link>
      )}
    </div>
  );
}
