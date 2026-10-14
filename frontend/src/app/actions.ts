"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiError, login, TOKEN_COOKIE } from "@/lib/api";
import { toNum } from "@/lib/format";
import type { Device, FxResult, Service, SyncJob, UsageImport, WidgetToken } from "@/lib/types";

export interface ActionResult {
  ok: boolean;
  message: string;
  // 기기 등록 직후 한 번만 내려오는 기기 토큰
  token?: string;
}

const str = (fd: FormData, key: string) => {
  const v = fd.get(key);
  return typeof v === "string" && v.trim() !== "" ? v.trim() : null;
};

async function run(fn: () => Promise<string | ActionResult>, paths: string[] = ["/"]): Promise<ActionResult> {
  try {
    const result = await fn();
    paths.forEach((p) => revalidatePath(p, "layout"));
    return typeof result === "string" ? { ok: true, message: result } : result;
  } catch (e) {
    if (e instanceof ApiError) return { ok: false, message: e.message };
    throw e; // redirect() 등 Next.js 내부 예외는 그대로 전달
  }
}

export async function loginAction(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const token = await login(str(fd, "email") ?? "", str(fd, "password") ?? "");
  if (!token) return { ok: false, message: "이메일 또는 비밀번호가 올바르지 않습니다" };
  (await cookies()).set(TOKEN_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });
  redirect("/");
}

export async function logoutAction() {
  (await cookies()).delete(TOKEN_COOKIE);
  redirect("/login");
}

export async function syncServiceAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    const job = await api<SyncJob>(`/api/services/${str(fd, "service_id")}/sync`, { method: "POST" });
    return job.status === "success" ? `수집 완료 (${job.records_count}건)` : `수집 실패: ${job.error_message ?? ""}`;
  });
}

export async function syncAllAction(_: ActionResult | null, _fd: FormData) {
  return run(async () => {
    const services = await api<Service[]>("/api/services");
    const targets = services.filter((s) => s.enabled && s.connector_available);
    if (targets.length === 0) return "자동 수집 대상 서비스가 없습니다";
    const jobs = await Promise.all(
      targets.map((s) => api<SyncJob>(`/api/services/${s.id}/sync`, { method: "POST" })),
    );
    const failed = jobs.filter((j) => j.status !== "success").length;
    return failed ? `${jobs.length}개 중 ${failed}개 수집 실패` : `${jobs.length}개 서비스 수집 완료`;
  });
}

export async function createServiceAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    await api("/api/services", {
      method: "POST",
      body: JSON.stringify({
        id: str(fd, "id"),
        name: str(fd, "name"),
        provider: str(fd, "provider"),
        collection_method: str(fd, "collection_method") ?? "manual",
      }),
    });
    return "서비스를 추가했습니다";
  });
}

export async function toggleServiceAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    const enabled = str(fd, "enabled") === "true";
    await api(`/api/services/${str(fd, "service_id")}`, { method: "PATCH", body: JSON.stringify({ enabled }) });
    return enabled ? "활성화했습니다" : "비활성화했습니다";
  });
}

export async function saveCredentialAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    await api(`/api/services/${str(fd, "service_id")}/credential`, {
      method: "PUT",
      body: JSON.stringify({ secret: str(fd, "secret") }),
    });
    return "API 키를 암호화해 저장했습니다";
  });
}

export async function deleteCredentialAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    await api(`/api/services/${str(fd, "service_id")}/credential`, { method: "DELETE" });
    return "API 키를 삭제했습니다";
  });
}

export async function testConnectionAction(_: ActionResult | null, fd: FormData) {
  try {
    const res = await api<{ ok: boolean; message: string }>(`/api/services/${str(fd, "service_id")}/test`, {
      method: "POST",
    });
    return { ok: res.ok, message: res.message };
  } catch (e) {
    if (e instanceof ApiError) return { ok: false, message: e.message };
    throw e;
  }
}

export async function createSubscriptionAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    await api("/api/subscriptions", {
      method: "POST",
      body: JSON.stringify({
        service_id: str(fd, "service_id"),
        plan_name: str(fd, "plan_name"),
        billing_cycle: str(fd, "billing_cycle") ?? "monthly",
        price: str(fd, "price"),
        currency: str(fd, "currency"),
        renewal_date: str(fd, "renewal_date"),
      }),
    });
    return "구독 정보를 저장했습니다";
  });
}

export async function deleteSubscriptionAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    await api(`/api/subscriptions/${str(fd, "id")}`, { method: "DELETE" });
    return "구독 정보를 삭제했습니다";
  });
}

export async function manualEntryAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    const metric = str(fd, "metric_code");
    const amount = str(fd, "amount");
    await api("/api/usage/manual", {
      method: "POST",
      body: JSON.stringify({
        service_id: str(fd, "service_id"),
        usage: metric
          ? {
              metric_code: metric,
              used_value: str(fd, "used_value"),
              limit_value: str(fd, "limit_value"),
              unit: str(fd, "unit"),
              resets_at: str(fd, "resets_at"),
            }
          : null,
        cost: amount
          ? { amount, currency: str(fd, "currency") ?? "KRW", billing_period: str(fd, "billing_period") }
          : null,
      }),
    });
    return "수동 입력을 저장했습니다";
  });
}

export async function saveSettingsAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        currency: str(fd, "currency"),
        timezone: str(fd, "timezone"),
        alert_threshold: Number(str(fd, "alert_threshold")),
        sync_interval_minutes: Number(str(fd, "sync_interval_minutes")),
      }),
    });
    return "설정을 저장했습니다";
  });
}

export async function createDeviceAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    const res = await api<{ device: Device; token: string }>("/api/devices", {
      method: "POST",
      body: JSON.stringify({ name: str(fd, "name") }),
    });
    return { ok: true, message: `"${res.device.name}" 기기를 등록했습니다`, token: res.token };
  });
}

const MAX_CSV_BYTES = 5_000_000; // 백엔드 한도(MAX_IMPORT_CHARS)와 같게

export async function uploadCsvAction(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const file = fd.get("file");
  if (!(file instanceof File) || file.size === 0) return { ok: false, message: "CSV 파일을 선택하세요" };
  if (file.size > MAX_CSV_BYTES) return { ok: false, message: "파일이 너무 큽니다 (최대 5MB). 기간을 나눠서 올려 주세요" };
  return run(async () => {
    const res = await api<{ record: UsageImport; errors: string[] }>(
      `/api/services/${str(fd, "service_id")}/usage-imports`,
      { method: "POST", body: JSON.stringify({ filename: file.name, content: await file.text() }) },
    );
    const r = res.record;
    const period = r.period_from && r.period_to ? ` · 기간 ${r.period_from.slice(0, 10)} ~ ${r.period_to.slice(0, 10)}` : "";
    const errors = res.errors.length ? ` · 건너뛴 행: ${res.errors.slice(0, 3).join(", ")}` : "";
    return {
      ok: r.rows_invalid === 0,
      message: `업로드 완료: ${r.rows_total}행 중 새로 추가 ${r.rows_added}, 이미 있던 요청 ${r.rows_duplicate}, 오류 ${r.rows_invalid}${period}${errors}`,
    };
  });
}

export async function deleteImportAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    const res = await api<{ removed_events: number }>(`/api/usage-imports/${str(fd, "import_id")}`, { method: "DELETE" });
    return `업로드를 삭제했습니다 (요청 ${res.removed_events}건 제거)`;
  });
}

export async function createWidgetTokenAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    const res = await api<{ widget_token: WidgetToken; token: string }>("/api/widget-tokens", {
      method: "POST",
      body: JSON.stringify({ name: str(fd, "name") }),
    });
    return { ok: true, message: `"${res.widget_token.name}" 위젯 토큰을 발급했습니다`, token: res.token };
  });
}

export async function revokeWidgetTokenAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    await api(`/api/widget-tokens/${str(fd, "token_id")}/revoke`, { method: "POST" });
    return "위젯 토큰을 폐기했습니다. 이 토큰을 쓰는 위젯은 더 이상 값을 받지 못합니다";
  });
}

export async function rotateDeviceTokenAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    const res = await api<{ device: Device; token: string }>(`/api/devices/${str(fd, "device_id")}/rotate-token`, {
      method: "POST",
    });
    return {
      ok: true,
      message: `"${res.device.name}" 기기 토큰을 재발급했습니다. 이전 토큰은 더 이상 쓸 수 없습니다`,
      token: res.token,
    };
  });
}

export async function revokeDeviceAction(_: ActionResult | null, fd: FormData) {
  return run(async () => {
    await api(`/api/devices/${str(fd, "device_id")}/revoke`, { method: "POST" });
    return "기기 토큰을 폐기했습니다. 이 기기의 에이전트는 더 이상 업로드할 수 없습니다";
  });
}

function fxMessage(res: FxResult): ActionResult {
  if (res.fx_error) return { ok: false, message: `${res.fx_error} (기존 환율 유지)` };
  return { ok: true, message: `적용 환율 1 USD = ${toNum(res.fx_usd_krw)} KRW (${res.fx_rate_date} 기준)` };
}

export async function saveFxAction(_: ActionResult | null, fd: FormData) {
  const mode = str(fd, "mode") === "manual" ? "manual" : "auto";
  return run(async () => {
    const res = await api<FxResult>("/api/settings/fx", {
      method: "PUT",
      body: JSON.stringify(
        mode === "manual" ? { mode, fx_usd_krw: str(fd, "fx_usd_krw"), fx_rate_date: str(fd, "fx_rate_date") } : { mode },
      ),
    });
    return fxMessage(res);
  });
}

export async function refreshFxAction(_: ActionResult | null, _fd: FormData) {
  return run(async () => fxMessage(await api<FxResult>("/api/settings/fx/refresh", { method: "POST" })));
}
