/**
 * 아이폰 위젯용 Scriptable(https://scriptable.app) 스크립트 템플릿.
 * 설정 → 위젯에서 토큰을 발급하면 서버 주소·토큰·대시보드 주소를 채워 복사할 수 있게 한다.
 *
 * 템플릿 안에서는 백틱과 달러-중괄호 보간을 쓰지 않는다 (String.raw 로 그대로 담기 위해).
 */
export const WIDGET_SCRIPT_TEMPLATE = String.raw`// AI Hub 위젯 — Scriptable 용 스크립트
// 대시보드 설정 → 위젯에서 발급한 위젯 토큰이 들어 있습니다. 다른 사람과 공유하지 마세요.
// 지원 크기: 작게 · 중간 · 크게, 잠금 화면(원형 · 사각형 · 한 줄)

const SERVER = "__SERVER__";
const TOKEN = "__TOKEN__";
const DASHBOARD = "__DASHBOARD__";
const CACHE_FILE = "aihub-widget-cache.json";
const REFRESH_MINUTES = 15;

const C = {
  bg: Color.dynamic(new Color("#FFFFFF"), new Color("#10141C")),
  fg: Color.dynamic(new Color("#12151C"), new Color("#F4F1EA")),
  muted: Color.dynamic(new Color("#5B6270"), new Color("#AEB4C0")),
  track: Color.dynamic(new Color("#E9EBEF"), new Color("#2A3140")),
  divider: Color.dynamic(new Color("#E6E8EC"), new Color("#232A36")),
  bar: Color.dynamic(new Color("#9AA3B2"), new Color("#5B6477")),
  warn: new Color("#C2410C"),
};

// ---------- 데이터 ----------

async function load() {
  const fm = FileManager.local();
  const path = fm.joinPath(fm.documentsDirectory(), CACHE_FILE);
  try {
    const req = new Request(SERVER + "/api/widget/summary");
    req.headers = { "X-Widget-Token": TOKEN };
    req.timeoutInterval = 15;
    const data = await req.loadJSON();
    const status = req.response ? req.response.statusCode : 0;
    if (status !== 200) {
      throw new Error(status === 401 ? "토큰이 폐기되었거나 잘못되었습니다" : (data && data.detail) || ("HTTP " + status));
    }
    fm.writeString(path, JSON.stringify(data));
    return { data: data, error: null };
  } catch (e) {
    // 실패하면 마지막으로 받은 값을 그대로 보여 주고 "오프라인"을 표시한다
    const cached = fm.fileExists(path) ? JSON.parse(fm.readString(path)) : null;
    return { data: cached, error: String((e && e.message) || e) };
  }
}

// ---------- 표시 형식 (값을 모르면 0 이 아니라 "—") ----------

function trimZeros(s) {
  return s.indexOf(".") >= 0 ? s.replace(/\.?0+$/, "") : s;
}

function fmtTokens(n) {
  if (n === null || n === undefined) return "—";
  if (n >= 1e8) return trimZeros((n / 1e8).toFixed(n >= 1e9 ? 0 : 2)) + "억";
  if (n >= 1e4) return trimZeros((n / 1e4).toFixed(n >= 1e6 ? 0 : 1)) + "만";
  return Math.round(n).toLocaleString("ko-KR");
}

function fmtMoney(v, currency) {
  if (v === null || v === undefined) return "—";
  if (currency === "USD") return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return "₩" + Math.round(v).toLocaleString("ko-KR");
}

function ago(iso) {
  if (!iso) return "갱신 기록 없음";
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "방금";
  if (minutes < 60) return minutes + "분 전";
  const hours = Math.round(minutes / 60);
  if (hours < 24) return hours + "시간 전";
  return Math.round(hours / 24) + "일 전";
}

function footerText(data, error) {
  const base = ago(data && data.updated_at);
  return error ? "오프라인 · " + base : base;
}

// ---------- 그림 ----------

// 앱 아이콘(세 조각 원호)을 흰 타일 위에 그린다
function logo(size) {
  const d = new DrawContext();
  d.size = new Size(size, size);
  d.opaque = false;
  d.respectScreenScale = true;
  const u = size / 100;
  const tile = new Path();
  tile.addRoundedRect(new Rect(0, 0, size, size), 22 * u, 22 * u);
  d.addPath(tile);
  d.setFillColor(Color.white());
  d.fillPath();
  const arcs = [["#12151C", -90, 190.98], ["#1DB98B", 30, 76.39], ["#E07A55", 110, 42.02]];
  const r = 30 * u;
  const w = 10 * u;
  const c = 50 * u;
  for (const arc of arcs) {
    const color = new Color(arc[0]);
    const points = [];
    for (let i = 0; i <= 48; i++) {
      const a = ((arc[1] + (arc[2] * i) / 48) * Math.PI) / 180;
      points.push(new Point(c + r * Math.cos(a), c + r * Math.sin(a)));
    }
    const p = new Path();
    p.addLines(points);
    d.addPath(p);
    d.setStrokeColor(color);
    d.setLineWidth(w);
    d.strokePath();
    d.setFillColor(color);
    for (const pt of [points[0], points[points.length - 1]]) {
      d.fillEllipse(new Rect(pt.x - w / 2, pt.y - w / 2, w, w));
    }
  }
  return d.getImage();
}

// 잠금 화면 원형 위젯의 링 (흰색 — iOS 가 배경에 맞춰 칠함)
function ring(share, size) {
  const d = new DrawContext();
  d.size = new Size(size, size);
  d.opaque = false;
  d.respectScreenScale = true;
  const w = size * 0.09;
  const rect = new Rect(w / 2, w / 2, size - w, size - w);
  d.setStrokeColor(new Color("#FFFFFF", 0.25));
  d.setLineWidth(w);
  d.strokeEllipse(rect);
  const c = size / 2;
  const r = (size - w) / 2;
  const sweep = Math.max(0.02, Math.min(1, share || 0)) * 360;
  const points = [];
  for (let i = 0; i <= 64; i++) {
    const a = ((-90 + (sweep * i) / 64) * Math.PI) / 180;
    points.push(new Point(c + r * Math.cos(a), c + r * Math.sin(a)));
  }
  const p = new Path();
  p.addLines(points);
  d.addPath(p);
  d.setStrokeColor(Color.white());
  d.setLineWidth(w);
  d.strokePath();
  return d.getImage();
}

// ---------- 공통 조각 ----------

function text(stack, value, size, color, opts) {
  const o = opts || {};
  const t = stack.addText(value);
  t.font = o.mono ? Font.semiboldMonospacedSystemFont(size) : o.bold ? Font.semiboldSystemFont(size) : Font.systemFont(size);
  t.textColor = color;
  t.lineLimit = 1;
  if (o.scale) t.minimumScaleFactor = o.scale;
  return t;
}

function header(w, data, iconSize, label) {
  const row = w.addStack();
  row.centerAlignContent();
  const img = row.addImage(logo(iconSize));
  img.imageSize = new Size(iconSize, iconSize);
  row.addSpacer(6);
  text(row, label, 12, C.fg, { bold: true });
  row.addSpacer();
  return row;
}

function dot(stack, hex) {
  const d = stack.addStack();
  d.size = new Size(8, 8);
  d.cornerRadius = 4;
  d.backgroundColor = new Color(hex);
}

function serviceRow(stack, s, showSource) {
  const row = stack.addStack();
  row.centerAlignContent();
  dot(row, s.color);
  row.addSpacer(7);
  text(row, s.name, 12, C.fg);
  row.addSpacer();
  if (showSource && s.source) {
    text(row, s.source, 10, C.muted);
    row.addSpacer(8);
  }
  text(row, fmtTokens(s.tokens), 12, C.fg, { mono: true });
}

function shareBar(stack, share, hex, width) {
  const track = stack.addStack();
  track.size = new Size(width, 5);
  track.cornerRadius = 2.5;
  track.backgroundColor = C.track;
  const fill = track.addStack();
  fill.size = new Size(Math.max(3, Math.round(width * (share || 0))), 5);
  fill.cornerRadius = 2.5;
  fill.backgroundColor = new Color(hex);
  track.addSpacer();
}

function errorWidget(w, error) {
  header(w, null, 16, "AI Hub");
  w.addSpacer();
  text(w, "연결할 수 없습니다", 13, C.fg, { bold: true });
  w.addSpacer(4);
  const t = text(w, error || "데이터 없음", 11, C.warn);
  t.lineLimit = 3;
  w.addSpacer();
}

// ---------- 크기별 ----------

function small(w, data, error) {
  w.setPadding(14, 15, 14, 15);
  header(w, data, 16, "AI Hub");
  w.addSpacer();
  text(w, data.period_label + " 지출", 11, C.muted);
  text(w, fmtMoney(data.spend_total, data.currency), 22, C.fg, { mono: true, scale: 0.6 });
  text(w, "토큰 " + fmtTokens(data.tokens_total), 11, C.muted);
  w.addSpacer();
  text(w, footerText(data, error), 10, error ? C.warn : C.muted);
}

function medium(w, data, error) {
  w.setPadding(15, 17, 15, 17);
  const cols = w.addStack();
  const left = cols.addStack();
  left.layoutVertically();
  header(left, data, 16, "AI Hub · " + data.period_label);
  left.addSpacer();
  text(left, "이번 달 지출", 11, C.muted);
  text(left, fmtMoney(data.spend_total, data.currency), 24, C.fg, { mono: true, scale: 0.6 });
  text(left, "구독 " + fmtMoney(data.subscription_total, data.currency) + " · API " + fmtMoney(data.api_cost_total, data.currency), 10, C.muted, { scale: 0.7 });
  cols.addSpacer(14);
  const line = cols.addStack();
  line.size = new Size(1, 120);
  line.backgroundColor = C.divider;
  cols.addSpacer(14);
  const right = cols.addStack();
  right.layoutVertically();
  const services = data.services.slice(0, 3);
  if (services.length === 0) text(right, "토큰 데이터 없음", 12, C.muted);
  for (const s of services) {
    serviceRow(right, s, false);
    right.addSpacer(8);
  }
  right.addSpacer();
  text(right, "토큰 · " + footerText(data, error), 10, error ? C.warn : C.muted);
}

function large(w, data, error) {
  w.setPadding(17, 19, 17, 19);
  const top = header(w, data, 18, "AI Hub · " + data.period.slice(0, 4) + "년 " + data.period_label);
  text(top, footerText(data, error), 10, error ? C.warn : C.muted);
  w.addSpacer(12);
  text(w, "이번 달 지출", 11, C.muted);
  text(w, fmtMoney(data.spend_total, data.currency), 28, C.fg, { mono: true, scale: 0.6 });
  text(w, "구독 " + fmtMoney(data.subscription_total, data.currency) + " · API " + fmtMoney(data.api_cost_total, data.currency), 11, C.muted);
  w.addSpacer(12);
  const line = w.addStack();
  line.size = new Size(280, 1);
  line.backgroundColor = C.divider;
  w.addSpacer(12);
  const services = data.services.slice(0, 4);
  if (services.length === 0) text(w, "토큰 데이터 없음", 12, C.muted);
  for (const s of services) {
    serviceRow(w, s, true);
    w.addSpacer(5);
    shareBar(w, s.share, s.color, 280);
    w.addSpacer(10);
  }
  w.addSpacer();
  text(w, "최근 7일 API 비용", 11, C.muted);
  w.addSpacer(6);
  const days = data.daily_api_costs || [];
  const max = Math.max.apply(null, days.map(function (d) { return d.amount || 0; }).concat([0]));
  const bars = w.addStack();
  bars.bottomAlignContent();
  for (let i = 0; i < days.length; i++) {
    const h = max > 0 ? Math.max(2, Math.round(((days[i].amount || 0) / max) * 40)) : 2;
    const b = bars.addStack();
    b.size = new Size(32, h);
    b.cornerRadius = 3;
    b.backgroundColor = C.bar;
    if (i < days.length - 1) bars.addSpacer(8);
  }
}

function accessoryCircular(w, data) {
  const top = data.services[0];
  w.addAccessoryWidgetBackground = true;
  w.backgroundImage = ring(top ? top.share : 0, 120);
  const s = w.addStack();
  s.layoutVertically();
  s.centerAlignContent();
  const v = text(s, fmtTokens(top ? top.tokens : null), 13, Color.white(), { mono: true, scale: 0.6 });
  v.centerAlignText();
  const n = text(s, top ? top.name.split(" ")[0] : "토큰", 9, Color.white(), { scale: 0.7 });
  n.centerAlignText();
}

function accessoryRectangular(w, data, error) {
  text(w, "AI Hub · " + data.period_label, 12, Color.white(), { bold: true });
  text(w, fmtMoney(data.spend_total, data.currency), 17, Color.white(), { mono: true, scale: 0.6 });
  text(w, "토큰 " + fmtTokens(data.tokens_total) + " · " + footerText(data, error), 11, Color.white(), { scale: 0.7 });
}

function accessoryInline(w, data) {
  w.addText("AI " + fmtMoney(data.spend_total, data.currency) + " · " + fmtTokens(data.tokens_total));
}

function build(family, data, error) {
  const w = new ListWidget();
  w.url = DASHBOARD;
  w.refreshAfterDate = new Date(Date.now() + REFRESH_MINUTES * 60 * 1000);
  const accessory = family.indexOf("accessory") === 0;
  if (!accessory) w.backgroundColor = C.bg;
  if (!data) {
    if (accessory) w.addText("AI Hub 연결 실패");
    else errorWidget(w, error);
    return w;
  }
  if (family === "small") small(w, data, error);
  else if (family === "large" || family === "extraLarge") large(w, data, error);
  else if (family === "accessoryCircular") accessoryCircular(w, data);
  else if (family === "accessoryRectangular") accessoryRectangular(w, data, error);
  else if (family === "accessoryInline") accessoryInline(w, data);
  else medium(w, data, error);
  return w;
}

// ---------- 실행 ----------

const result = await load();
if (config.runsInWidget) {
  Script.setWidget(build(config.widgetFamily || "medium", result.data, result.error));
} else {
  // 앱에서 직접 실행하면 크기를 골라 미리 본다
  const alert = new Alert();
  alert.title = "AI Hub 위젯 미리보기";
  alert.addAction("작게");
  alert.addAction("중간");
  alert.addAction("크게");
  alert.addCancelAction("닫기");
  const choice = await alert.presentSheet();
  if (choice === 0) await build("small", result.data, result.error).presentSmall();
  if (choice === 1) await build("medium", result.data, result.error).presentMedium();
  if (choice === 2) await build("large", result.data, result.error).presentLarge();
}
Script.complete();
`;

export function buildWidgetScript(opts: { serverUrl: string; token: string; dashboardUrl: string }): string {
  return WIDGET_SCRIPT_TEMPLATE.replace('"__SERVER__"', JSON.stringify(opts.serverUrl.replace(/\/+$/, "")))
    .replace('"__TOKEN__"', JSON.stringify(opts.token))
    .replace('"__DASHBOARD__"', JSON.stringify(opts.dashboardUrl));
}
