import { deleteImportAction, uploadCsvAction } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/ActionForm";
import { formatDateTime } from "@/lib/format";
import type { UsageImport } from "@/lib/types";

const CURSOR_USAGE_URL = "https://cursor.com/dashboard/usage";

/** Cursor 사용량 CSV 업로드와 업로드 이력. 기간이 겹치는 파일을 다시 올려도 같은 요청은 한 번만 저장된다. */
export function CsvImportPanel({ serviceId, imports }: { serviceId: string; imports: UsageImport[] }) {
  return (
    <section className="panel space-y-3">
      <div>
        <h2 className="text-sm font-medium text-slate-600">CSV 업로드</h2>
        <p className="text-xs text-slate-500">
          Cursor 대시보드에서 내려받은 <code>usage-events-*.csv</code>를 그대로 올리세요. 기간은 자유롭게 정해도 되고,
          이미 올린 기간과 겹쳐도 같은 요청은 한 번만 집계됩니다.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900">
        <span>CSV 파일은 Cursor 사용량 페이지에서 받을 수 있습니다.</span>
        <a
          href={CURSOR_USAGE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 font-medium underline underline-offset-2 hover:text-sky-700"
        >
          cursor.com/dashboard/usage 열기
          <span aria-hidden="true">↗</span>
          <span className="sr-only">(새 창)</span>
        </a>
      </div>
      <ActionForm action={uploadCsvAction} className="flex flex-wrap items-center gap-2">
        <input type="hidden" name="service_id" value={serviceId} />
        <input name="file" type="file" accept=".csv,text/csv" required className="text-sm" />
        <SubmitButton>업로드</SubmitButton>
      </ActionForm>

      {imports.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500">
              <tr>
                <th className="py-1">업로드 시각</th>
                <th>파일</th>
                <th>기간</th>
                <th className="text-right">전체</th>
                <th className="text-right">추가</th>
                <th className="text-right">중복</th>
                <th className="text-right">오류</th>
                <th />
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {imports.map((i) => (
                <tr key={i.id} className="border-t border-slate-100">
                  <td className="py-1.5">{formatDateTime(i.uploaded_at)}</td>
                  <td className="max-w-48 truncate" title={i.filename}>
                    {i.filename}
                  </td>
                  <td>
                    {i.period_from && i.period_to ? `${i.period_from.slice(0, 10)} ~ ${i.period_to.slice(0, 10)}` : "—"}
                  </td>
                  <td className="text-right">{i.rows_total}</td>
                  <td className="text-right">{i.rows_added}</td>
                  <td className="text-right">{i.rows_duplicate}</td>
                  <td className={`text-right ${i.rows_invalid ? "text-rose-600" : ""}`}>{i.rows_invalid}</td>
                  <td className="text-right">
                    <ActionForm action={deleteImportAction}>
                      <input type="hidden" name="import_id" value={i.id} />
                      <SubmitButton variant="danger">삭제</SubmitButton>
                    </ActionForm>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-slate-500">삭제하면 그 업로드로 새로 추가된 요청만 지워집니다.</p>
        </div>
      )}
    </section>
  );
}
