// 백엔드는 Decimal 을 문자열 또는 숫자로 직렬화하므로 표시 직전에 toNum() 으로 변환한다
export type Num = number | string;

export type SourceType = "api" | "cli" | "manual";
export type DataState = "ok" | "no_data" | "error" | "unavailable" | "disabled";

export interface Subscription {
  id: number;
  service_id: string;
  plan_name: string;
  billing_cycle: "monthly" | "annual";
  price: Num;
  currency: string;
  renewal_date: string | null;
  is_active: boolean;
}

export interface Snapshot {
  id: number;
  metric_code: string;
  used_value: Num | null;
  limit_value: Num | null;
  unit: string | null;
  status: "ok" | "unavailable";
  period_start: string | null;
  period_end: string | null;
  resets_at: string | null;
  source_type: SourceType;
  captured_at: string;
}

export interface SyncJob {
  id: number;
  service_id: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "success" | "failed" | "partial";
  error_message: string | null;
  records_count: number;
  source_type: string;
  trigger: string;
}

export interface Service {
  id: string;
  name: string;
  provider: string;
  collection_method: SourceType;
  connector: string | null;
  enabled: boolean;
  connector_available: boolean;
  has_credential: boolean;
  credential_hint: string | null;
}

export interface DeviceUsage {
  // 'device' = PC 에이전트, 'csv' = CSV 업로드 합계
  kind?: "device" | "csv";
  device_id: number | null;
  name: string;
  used_value: Num | null;
  captured_at: string;
  online: boolean;
  revoked: boolean;
}

export interface WidgetToken {
  id: number;
  name: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface Device {
  id: number;
  name: string;
  created_at: string;
  last_seen_at: string | null;
  revoked_at: string | null;
  online: boolean;
  month_usage: Record<string, Num>;
}

export interface ServiceCardData {
  id: string;
  name: string;
  provider: string;
  collection_method: SourceType;
  enabled: boolean;
  has_credential: boolean;
  subscription: Subscription | null;
  subscription_monthly: Num | null;
  usage: Snapshot | null;
  usage_rate: number | null;
  month_api_cost: Num | null;
  last_sync: SyncJob | null;
  data_state: DataState;
  stale: boolean;
  // 기기 에이전트 값이 있으면 기기별 이번 달 누계 (usage.used_value 는 그 합계)
  devices: DeviceUsage[];
}

export type FxMode = "auto" | "manual";

export interface Fx {
  usd_krw: Num;
  rate_date: string | null;
  mode: FxMode;
  source: string | null;
  source_label: string | null;
  updated_at: string | null;
}

export interface DashboardSummary {
  period: string;
  current_period: string;
  is_current_month: boolean;
  currency: string;
  fx: Fx | null;
  subscription_total: Num | null;
  api_cost_total: Num | null;
  conversion_missing: boolean;
  services_connected: number;
  services_total: number;
  avg_usage_rate: number | null;
  services: ServiceCardData[];
  daily_api_costs: { date: string; amount: Num | null; conversion_missing: boolean }[];
  last_synced_at: string | null;
  next_sync_at: string | null;
}

export interface CostsReport {
  period: string;
  currency: string;
  fx: Fx | null;
  subscriptions: {
    service_id: string;
    service_name: string;
    plan_name: string;
    billing_cycle: string;
    price: Num;
    currency: string;
    monthly_converted: Num | null;
  }[];
  subscription_total: Num | null;
  api_costs: {
    service_id: string;
    service_name: string;
    original: Record<string, Num>;
    converted: Num | null;
    conversion_missing: boolean;
  }[];
  api_cost_total: Num | null;
  conversion_missing: boolean;
}

export interface CostTrend {
  currency: string;
  months: { period: string; by_service: Record<string, Num | null>; conversion_missing: boolean }[];
}

export interface TokenMonth {
  period: string;
  total: number;
  input: number;
  output: number;
  cache_creation: number;
  cache_read: number;
  devices: number;
  csv: number;
}

export interface UsageImport {
  id: number;
  service_id: string;
  filename: string;
  uploaded_at: string;
  rows_total: number;
  rows_added: number;
  rows_duplicate: number;
  rows_invalid: number;
  period_from: string | null;
  period_to: string | null;
}

export interface ServiceUsage {
  service: Service;
  csv_import_supported: boolean;
  token_months: TokenMonth[];
  devices: (DeviceUsage & { breakdown: Partial<Record<"input" | "output" | "cache_creation" | "cache_read", number>> | null })[];
  latest: Snapshot[];
  history: Snapshot[];
  recent_jobs: SyncJob[];
  costs: { cost_date: string; granularity: "day" | "month"; amount: Num; currency: string; source_type: string }[];
}

export interface UserSettings {
  timezone: string;
  currency: "KRW" | "USD";
  alert_threshold: number;
  fx_mode: FxMode;
  fx_usd_krw: Num | null;
  fx_rate_date: string | null;
  fx_source: string | null;
  fx_updated_at: string | null;
  sync_interval_minutes: number;
}

export interface FxResult extends UserSettings {
  fx_error: string | null;
}
