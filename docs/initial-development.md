# AI Usage Hub — 초기 개발 명세서 (v0.1)

- 작성일: 2026-10-12
- 확정 아키텍처: **옵션 B — FastAPI 백엔드(Railway) + Next.js 프론트엔드(Vercel) + Railway PostgreSQL**
- 범위: 4주 로드맵의 **1주차**(설계 확정, 프로젝트 골격, 인증, DB 마이그레이션)

---

## 1. 검증 결과

기획 초안에는 **옵션 A(Next.js 단일 구성)** 와 **옵션 B(FastAPI + Railway)** 가 섞여 있었고, 아래 결정은 모두 옵션 B를 기준으로 정리했습니다.

### 1.1 문서 내부 불일치와 확정 결정

| # | 기획서 내용 | 문제 | 확정 결정 |
|---|---|---|---|
| 1 | 옵션 A(Vercel Cron + Supabase) / 옵션 B(Railway + APScheduler) 혼재, 권장안은 A | 아키텍처 미확정 | **옵션 B**. 백엔드는 FastAPI, DB는 Railway PostgreSQL, 스케줄러는 APScheduler(프로세스 내부) |
| 2 | 3개 테이블(`providers`, `usage_records`, `monthly_summaries`)과 7개 테이블이 함께 있음. 흐름도에는 `daily_aggregates`도 등장 | 스키마가 둘 | **7개 테이블 안을 채택**하고 `service_credentials`를 추가해 8개로 구성(4장 참고). 3개 테이블 안과 `daily_aggregates`는 폐기 |
| 3 | 파일 구조가 `connectors/`와 `providers/` 두 가지 | 플러그인 구조 이름 불일치 | `backend/app/connectors/`로 통일 |
| 4 | Provider 인터페이스는 `fetchUsage(apiKey) → UsageRecord[]` | 7개 테이블 안의 `usage_snapshots`/`cost_records`와 형식이 맞지 않음 | 커넥터는 `ConnectorResult(snapshots, costs)`를 반환하고 저장과 이력 기록은 공통 모듈이 담당(5장) |
| 5 | 인증은 FastAPI-Users + NextAuth.js | 1인용 MVP에는 과함. 로그인 시스템이 두 개가 됨 | 단일 관리자 계정 + JWT(백엔드 발급). 프론트는 httpOnly 쿠키에 보관하고 서버 측에서만 백엔드 호출. `users` 테이블은 다중 사용자 확장용으로 유지 |
| 6 | 설정 화면에서 "API 키 입력·저장(환경변수)" + "API 키는 DB에 저장하지 않음" | 웹 UI에서 런타임에 환경변수를 바꿀 수 없음. 요구사항끼리 충돌 | **Fernet 암호화 후 DB 저장**(`service_credentials`). 평문 저장 금지 원칙은 유지. 암호화 키는 환경변수 `CREDENTIALS_KEY` |
| 7 | "화면은 메인 대시보드와 서비스 설정 2개 페이지" ↔ 라우트 4개(`/`, `/services/{id}`, `/costs`, `/settings`) | 화면 수 불일치 | **4개 라우트**와 로그인 화면으로 구성 |
| 8 | 목업 2종: ① 사이드바 + KRW 구독형 ② 헤더형 + USD API형. 요약 카드 구성도 다름 | 어떤 화면을 기준으로 할지 불명확 | 레이아웃은 ①(사이드바)을 따름. 요약 4칸은 **월 구독료 합계 · 연결 서비스(n/m) · 평균 사용률 · 이번 달 API 비용**. 미연결/오류 카드는 ②의 빨간 테두리 방식 |
| 9 | FR-06 "월별 12개월" ↔ 목업 "최근 7일 바차트" | 차트 기간 불일치 | 메인 화면은 7일 일별 API 비용, `/costs`는 12개월 월별 추이로 둘 다 구현 |
| 10 | `cost_records.cost_type`에 `'subscription'`이 포함되어 있는데 주석은 "구독료와 분리" | 구독료가 `subscriptions`와 `cost_records`에 중복 저장될 위험 | 구독료는 `subscriptions`에서만 계산. `cost_records`는 `api_usage`/`other`만 허용 |
| 11 | `cost_records`의 단위가 월(`billing_period`)뿐임 | 7일 차트를 만들 수 없음 | `cost_date` + `granularity('day'|'month')` 추가. API는 일 단위, 수동 입력은 월 단위 |
| 12 | "0%로 표시하지 않고 수집 불가 표시" 원칙 | `usage_snapshots`에 상태 컬럼이 없어서 수집 불가와 0을 구분할 수 없음 | `status('ok'|'unavailable')` 추가, `used_value`는 NULL 허용. API와 화면 모두 `null`이면 "—" 또는 "데이터 없음"으로 표시 |
| 13 | 로드맵이 4주와 6주 Phase 두 가지이고, 1차 서비스도 Claude Code+Codex와 Anthropic+OpenAI로 다름 | 일정과 범위 불일치 | **4주 로드맵**(옵션 B 기준)을 채택(8장). Phase 1~4 표는 옵션 A용이라 폐기 |
| 14 | 비용 표 3개의 결론이 서로 다름($5~7/월 vs $0/월). "Railway Starter $0"이라는 표현도 있음 | 비용 결론 불일치 | 옵션 B 기준 **약 $5/월**(Railway Hobby 최소 요금, 사용량 $5 포함) + Vercel Hobby $0. 도메인은 선택(연 $10~15) |
| 15 | 수집 주기: "일 1회 수집 기준 용량 산정" ↔ "1시간마다 자동 수집" | 산정 근거 불일치 | 기본 1시간(설정에서 15~1440분). 1인 기준으로 용량 문제 없음 |
| 16 | 커넥터 4종(Claude Code: CLI 파서 등) ↔ 백엔드는 클라우드(Railway)에서 실행 | **클라우드 서버는 사용자 PC의 CLI 로그를 읽을 수 없음** | CLI 수집은 사용자 PC에서 도는 **로컬 수집 스크립트가 `POST /api/usage/manual`(source_type=`cli`)로 업로드**하는 구조로 확정(2주차) |
| 17 | `railway.toml` 초안의 `[[services]]` 블록 | railway.toml은 서비스 1개 단위 설정이라 이 형식을 지원하지 않음 | `backend/railway.toml`은 build/deploy만 정의. DB는 Railway 대시보드에서 추가하고 `DATABASE_URL` 참조 변수로 연결 |

### 1.2 외부 사실 확인 결과 (커넥터 구현 전 재확인 필요)

| 서비스 | 기획서 기재 | 확인 내용 | 조치 |
|---|---|---|---|
| OpenAI | `/v1/dashboard/billing/usage` | 브라우저 세션 키가 필요한 비공식 레거시 엔드포인트임. 공식 경로는 **Admin API 키 + `/v1/organization/costs`, `/v1/organization/usage/*`** | 공식 Costs/Usage API로 구현. ChatGPT 요금제의 Codex 사용량은 API로 제공되지 않으므로 CLI 로그 또는 수동 입력 |
| Anthropic | Admin Usage & Cost API | 기재 내용과 일치. **Admin 키(`sk-ant-admin…`)** 필요, 조직(API 계정) 단위로만 제공 | `/v1/organizations/cost_report`, `/v1/organizations/usage_report/messages` 사용. Pro/Max 구독 한도는 API 없음 → CLI 로그 또는 수동 입력 |
| Claude Code | "CLI 상태 정보" | 로컬 세션 로그(`~/.claude/projects/**/*.jsonl`)에 메시지별 토큰 사용량이 기록됨. 형식은 비공식이라 버전마다 바뀔 수 있음 | 로컬 수집 스크립트로 파싱하고 파서 테스트를 필수로 둠(CLI 파서는 버전 변경에 취약하므로) |
| Gemini | GCP Cloud Billing API로 서비스별 비용 조회 | Cloud Billing API는 계정과 가격 정보만 제공하고 **실제 청구 금액은 제공하지 않음**. 비용은 **BigQuery 결제 내보내기**를 조회해야 함 | 3주차 커넥터는 BigQuery 내보내기 기반으로 구현. 내보내기 설정 전에는 "수집 불가"로 표시 |
| GitHub Copilot | `/user/copilot_billing`, 2026.6~ 토큰 기반 | 공개 문서에서 확인되는 경로는 조직 단위(`/orgs/{org}/copilot/billing`)와 개인 결제 사용량(`/users/{username}/settings/billing/usage`) | **구현 전 확인 필요**. MVP 범위 밖(후속) |
| Anthropic Enterprise Analytics (2026.5~) | Enterprise 전용 | 개인 1인 사용 범위와 맞지 않음 | MVP 제외 |
| Cursor | 공식 API 없음 | Teams 플랜용 Admin API는 있으나 개인 플랜은 해당 없음 | 수동 입력(기획서와 동일) |
| Vercel Cron (옵션 A) | Hobby에서 1시간마다 실행 | Hobby 플랜 Cron은 **하루 1회**만 실행 가능 | 옵션 B를 선택했으므로 해당 없음. 옵션 A로 돌아갈 경우 주의 |
| Railway 빌더 | `builder = "nixpacks"` | Railway 기본 빌더가 바뀌는 중이라 빌드 재현성 문제 가능성 | **Dockerfile 빌드로 고정** |

### 1.3 핵심 원칙 반영 확인

| 기획서 원칙 | 반영 위치 |
|---|---|
| 수집 실패 시 0%로 표시하지 않음 | `usage_snapshots.status`, 대시보드 `data_state`(ok/no_data/unavailable/error/disabled), 금액·사용률 `null` → "—" |
| 구독 한도와 API 종량제 분리 | `subscriptions`와 `cost_records` 분리, 요약 카드와 `/costs` 화면에서 별도 표시 |
| 데이터 출처 표시(API/CLI/수동) | 모든 스냅샷과 비용에 `source_type` 저장, `SourceBadge`로 항상 표시 |
| 수집 실패 시 기존 데이터 유지 + 오래된 데이터 표시 | 실패 시 스냅샷을 쓰지 않고 `sync_jobs`에만 기록. 주기의 2배 이상 갱신되지 않으면 `stale` 표시 |
| API 키 평문 저장·로그 출력 금지 | Fernet 암호화, 응답에는 끝 4자리 힌트만 포함, 오류 메시지에서 키 마스킹 |
| 공개 URL 인증 필수 | 백엔드 전 API에 JWT 필요(`/health` 제외), 프론트 미들웨어에서 로그인 강제 |
| 원화 환산 시 원 통화·환율·적용일 표시 | 환율 자동 조회와 직접 입력을 모두 지원(4.1장). 대시보드와 `/costs`에 적용 환율, 기준일, 출처를 표시. 환율이 없으면 합계에서 빼고 경고 |

---

## 2. 확정 아키텍처

```
[APScheduler (FastAPI 프로세스 내부) / 새로고침 버튼]
        ↓
[Railway — FastAPI: 커넥터 실행 → 정규화 → 저장 → sync_jobs 기록]
        ↑ POST /api/usage/manual (source_type=cli)   ← [사용자 PC 로컬 수집 스크립트] (2주차)
        ↓
[Railway PostgreSQL] usage_snapshots · cost_records · subscriptions · sync_jobs …
        ↑ REST(JSON) + JWT — Next.js 서버에서만 호출 (CORS 불필요)
[Vercel — Next.js 15 (App Router) 대시보드]
```

| 레이어 | 선택 | 비고 |
|---|---|---|
| 프론트엔드 | Next.js 15 + TypeScript + Tailwind CSS v4 + Recharts + date-fns | Vercel Hobby. shadcn/ui는 2주차 UI 다듬기 때 도입 |
| 백엔드 | Python 3.12 + FastAPI | Railway, Dockerfile 빌드 |
| ORM·마이그레이션 | SQLAlchemy 2.0 + Alembic | 테스트는 SQLite, 운영은 PostgreSQL |
| DB | Railway PostgreSQL | `DATABASE_URL` 자동 주입(`postgresql://`는 `psycopg` 드라이버로 자동 변환) |
| 스케줄러 | APScheduler(BackgroundScheduler) | **Railway 레플리카는 1개로 유지**(중복 수집 방지) |
| 인증 | 단일 관리자 + JWT(HS256) | 비밀번호는 scrypt 해시 |
| 비밀 관리 | 환경변수 + Fernet 암호화 DB 저장 | `JWT_SECRET`, `CREDENTIALS_KEY` |

---

## 3. 저장소 구조

```
backend/
  app/
    main.py            FastAPI 앱, 라우터 등록, 스케줄러 수명주기, /health
    config.py          환경변수 설정
    db.py · models.py  SQLAlchemy 엔진/세션, 8개 테이블
    schemas.py         요청/응답 스키마
    security.py        비밀번호 해시, JWT, Fernet, 키 마스킹
    credentials.py     서비스 API 키 암복호화 저장
    sync.py            커넥터 실행 → 저장 → sync_jobs 기록 (비용은 upsert)
    scheduler.py       주기 수집 + 환율 갱신
    reports.py · money.py  집계, 통화 환산
    fx.py              환율 자동 조회 (수출입은행 → Frankfurter 순서)
    erd.py             docs/erd.md 자동 생성
    imports/           사용량 CSV 파서(Cursor)와 중복 제거 저장
  collector/           PC 에이전트 (Claude Code·Codex 파서, 설치 스크립트)
    seed.py            관리자 계정 + 1차 서비스 4종 (멱등)
    connectors/        __init__.py(레지스트리), base.py(인터페이스)
    routers/           auth, dashboard, services, subscriptions, usage, costs, sync_jobs, settings
  migrations/          Alembic (0001_initial_schema, 0002_fx_auto, 0003_devices, 0004_usage_imports, 0005_widget_tokens)
  tests/               API·환율·기기·에이전트·CSV·월 선택·위젯·ERD 테스트 51건
  Dockerfile · railway.toml · pyproject.toml · uv.lock
frontend/
  src/app/(app)/       page.tsx(대시보드), services/[id], costs, settings
  src/app/login/       로그인
  src/app/actions.ts   서버 액션 (백엔드 호출)
  src/components/      ServiceCard, SummaryStats, SourceBadge, Sidebar, charts, ActionForm, FxSettings
  src/lib/             api.ts(server-only), types.ts, format.ts
  src/middleware.ts    미인증 시 /login 리다이렉트
docs/                user-guide · implementation-status · erd · initial-development
```

---

## 4. DB 스키마 확정안

기획 단계의 7개 테이블을 기준으로 아래 내용을 바꿨습니다. 실제 정의는 `backend/app/models.py`와 `backend/migrations/versions/0001_initial_schema.py`에 있습니다.

| 테이블 | 기획서 대비 변경 |
|---|---|
| `users` | `password_hash` 추가(로그인) |
| `ai_services` | `collection_method('api'|'cli'|'manual')`, `connector`(레지스트리 키), `created_at` 추가 → FR-01 "제공 방식 기록" |
| `service_credentials` (**신규**) | `service_id` PK, `encrypted_secret`(Fernet), `hint`(끝 4자리), `updated_at` |
| `subscriptions` | `is_active`, `created_at` 추가. `billing_cycle` CHECK 제약 |
| `usage_snapshots` | `status('ok'|'unavailable')`, `resets_at`(다음 초기화 시각, 목업 반영) 추가. `(service_id, captured_at)` 인덱스 |
| `cost_records` | `cost_type`은 `api_usage`/`other`만 허용. `granularity`, `cost_date`, `recorded_at` 추가. 버킷 유니크 제약 `(user, service, cost_type, source_type, granularity, cost_date)`로 재수집 시 upsert |
| `sync_jobs` | `status`에 `running` 추가, `records_count`, `trigger('schedule'|'manual')` 추가 |
| `user_settings` | `fx_mode('auto'|'manual')`, `fx_usd_krw`, `fx_rate_date`(기준일), `fx_source`, `fx_updated_at`, `sync_interval_minutes` 추가 (마이그레이션 `0002_fx_auto`) |

공통: PK는 `bigserial`(PostgreSQL), 시각은 모두 `timestamptz`, `raw`는 `JSONB`입니다.

### 4.1 환율 — 자동 조회 + 직접 입력

| 항목 | 내용 |
|---|---|
| 모드 | **자동 조회**(기본) 또는 **직접 입력**. 설정 화면에서 전환 |
| 자동 조회 출처 | 1순위 **한국수출입은행 매매기준율**(`KOREAEXIM_API_KEY`를 설정한 경우), 2순위 **Frankfurter(ECB 기준환율, 키 불필요)** |
| 갱신 주기 | 서버 기동 직후 1회, 이후 `FX_REFRESH_HOURS`(기본 6시간)마다. 설정 화면의 "지금 다시 조회" 버튼으로 즉시 조회도 가능 |
| 실패 처리 | 조회에 실패하면 **기존 환율을 유지**하고 화면에 실패 사유를 표시. 오류 메시지에서 API 키는 가림 |
| 직접 입력 | 환율 값과 기준일을 입력합니다(기준일을 비워두면 오늘). 직접 입력 모드에서는 스케줄러와 새로고침이 값을 덮어쓰지 않습니다 |
| 수출입은행 특성 | 영업일 11시 전, 주말, 공휴일에는 데이터가 비어 있어 최대 7일 전까지 거슬러 조회합니다. 응답의 `result` 코드가 오류(인증키 오류 3, 일일 한도 초과 4 등)이면 Frankfurter로 넘어갑니다 |
| ECB 기준환율 특성 | 유럽중앙은행 영업일 기준으로 하루 한 번 갱신되며, 국내 은행 고시 환율과 약간 차이가 날 수 있습니다. 화면에 출처를 함께 표시합니다 |
| 기존 데이터 | 마이그레이션 시 이미 환율을 직접 입력해 둔 사용자는 `manual` 모드로 전환해 기존 값을 보존합니다 |
| 제한 | 지금은 모든 금액을 **현재 적용 환율**로 환산합니다. 과거 월 비용을 그 시점 환율로 환산하는 기능(일별 환율 이력 테이블)은 후속 과제로 남겨 둡니다. 수동 비용 입력의 `exchange_rate`를 지정하면 그 값이 우선합니다 |

---

## 5. 커넥터 인터페이스

```python
class Connector(ABC):
    key: ClassVar[str]                       # ai_services.connector 값
    source_type: ClassVar["api" | "cli"]
    requires_secret: ClassVar[bool] = True

    def fetch(self, ctx: ConnectorContext) -> ConnectorResult: ...   # snapshots + costs
    def test_connection(self, ctx: ConnectorContext) -> bool: ...
```

- 새 서비스를 연동하려면 `app/connectors/<서비스>.py`를 만들고 `register()`로 등록한 뒤, `ai_services.connector`에 키를 지정합니다.
- 커넥터는 지표를 제공하지 않을 때 `SnapshotData(status="unavailable")`를 반환합니다. 0으로 채우지 않습니다.
- 실패하면 `ConnectorError`를 던집니다. `sync.py`가 기존 데이터를 유지한 채 실패 이력만 남기고, 메시지 안의 API 키는 가립니다.
- 비용은 최근 35일을 다시 조회해서 upsert합니다(늦게 확정되는 금액 대응).

---

## 6. API 엔드포인트 (구현 완료)

`/health`, `/api/auth/login`, `/api/agent/*`, `/api/widget/summary`를 제외한 모든 엔드포인트는 `Authorization: Bearer <JWT>`가 필요합니다. `/api/agent/*`는 기기 토큰, `/api/widget/summary`는 위젯 토큰으로 인증합니다.

| Method | Endpoint | 설명 | 기획서 |
|---|---|---|---|
| POST | `/api/auth/login` | 로그인 → JWT | 추가 |
| GET | `/api/dashboard/summary?period=YYYY-MM` | 요약 4칸, 서비스 카드, 일별 비용, 다음 수집 시각. `period`를 주면 그 달 기준(기본 이번 달) | ✅ |
| GET / POST | `/api/services` | 서비스 목록 / 추가 | ✅ |
| PATCH | `/api/services/{id}` | 수정·활성화·비활성화 (FR-01) | 추가 |
| GET | `/api/services/{id}/usage?days=` | 최신 지표, 이력, 비용, 최근 수집 이력 | ✅ |
| POST | `/api/services/{id}/sync` | 즉시 수집 (커넥터 없으면 400) | ✅ |
| PUT / DELETE | `/api/services/{id}/credential` | API 키 저장(암호화)·삭제 | 추가 |
| POST | `/api/services/{id}/test` | 연결 테스트 | 추가 |
| GET / POST / PATCH / DELETE | `/api/subscriptions` | 구독 관리 (FR-02) | 추가 |
| POST | `/api/usage/manual` | 수동 사용량·월 비용 입력 (`source_type` = manual 또는 cli) | ✅ |
| GET | `/api/costs?period=YYYY-MM` | 구독료와 API 비용 분리, 원 통화, 환율 | ✅ |
| GET | `/api/costs/trend?months=12` | 서비스별 월 API 비용 추이 (FR-06) | 추가 |
| GET | `/api/sync-jobs?service_id=&status=` | 수집 이력과 실패 원인 | ✅ |
| GET / PUT | `/api/settings` | 통화, 시간대, 알림 임계치, 수집 주기 | 추가 |
| PUT | `/api/settings/fx` | 환율 모드 전환 (`{"mode":"auto"}` 또는 `{"mode":"manual","fx_usd_krw":…,"fx_rate_date":…}`). auto로 바꾸면 즉시 조회 | 추가 |
| POST | `/api/settings/fx/refresh` | 자동 모드에서 즉시 재조회 (직접 입력 모드면 409) | 추가 |
| GET / POST | `/api/devices` | 기기 목록(온라인 여부·이번 달 사용량) / 기기 등록(기기 토큰 1회 반환) | 추가 |
| POST | `/api/devices/{id}/rotate-token` | 토큰 재발급(이전 토큰 즉시 무효, 기기·기록 유지). 원문은 저장하지 않으므로 "토큰 다시 보기" 대신 사용 | 추가 |
| POST | `/api/devices/{id}/revoke` | 기기 토큰 폐기 | 추가 |
| POST | `/api/agent/usage` | **기기 토큰 인증**(`X-Device-Token`). 기기별 월·일 누계 덮어쓰기 업로드 | 추가 |
| POST / GET | `/api/services/{id}/usage-imports` | 사용량 CSV 업로드(`{filename, content}`) / 업로드 이력. 현재 `cursor`만 지원 | 추가 |
| DELETE | `/api/usage-imports/{id}` | 업로드 삭제(그 업로드로 추가된 요청만 제거) | 추가 |
| GET / POST | `/api/widget-tokens` | 위젯 토큰 목록 / 발급(토큰 1회 반환) | 추가 |
| POST | `/api/widget-tokens/{id}/revoke` | 위젯 토큰 폐기 | 추가 |
| GET | `/api/widget/summary` | **위젯 토큰 인증**(`X-Widget-Token`). 이번 달 지출·서비스별 토큰·7일 API 비용 요약 (조회 전용) | 추가 |
| POST | `/api/agent/heartbeat` | **기기 토큰 인증**. 온라인 신호 | 추가 |

---

## 7. 1주차 완료 내역과 검증 결과

| 항목 | 상태 | 검증 |
|---|---|---|
| 설계 확정(이 문서) | 완료 | 1장 |
| DB 스키마와 Alembic 마이그레이션 | 완료 | 빈 DB에 적용 후 `alembic check`에서 모델과 차이 없음. PostgreSQL DDL 렌더링 확인(BIGSERIAL·UUID·JSONB·`now()`) |
| 인증(JWT + 로그인 화면 + 미들웨어) | 완료 | 미인증 접근 시 401/307, 잘못된 비밀번호 401 |
| 서비스·구독·설정 CRUD API | 완료 | pytest |
| 수동 입력, 비용 집계, 환율 환산 | 완료 | pytest. 혼합 통화에서 환율이 없으면 `conversion_missing` |
| 동기화 엔진, sync_jobs, 키 마스킹 | 완료 | 가짜 커넥터로 성공·실패·upsert·키 미노출 테스트 |
| APScheduler 주기 수집 | 완료 | 서버 기동 시 등록 확인, `next_sync_at` 응답 |
| 화면 4종 + 로그인 | 골격 완료 | `next build` 성공. 로컬에서 백엔드와 함께 띄워 전체 라우트 200 / 없는 서비스 404, 환산 합계 표시 확인 |
| 환율 자동 조회 + 직접 입력 | 완료 | pytest(수출입은행 주말 처리, 인증 오류, Frankfurter 대체, 키 마스킹, 직접 입력값 보호, 실패 시 기존 값 유지). 마이그레이션 0002 적용과 되돌리기 확인. 실제 Frankfurter API 조회로 화면 표시 확인 |
| 백엔드 테스트 | **16/16 통과** | `uv run pytest` |
| 실제 서비스 커넥터 | **미구현(2주차)** | 현재는 수동 입력만으로 데이터가 들어옴 |

참고: Next 15에 포함된 postcss의 알려진 취약점은 `package.json`의 `overrides`(postcss ^8.5.23)로 해결했습니다(`npm audit` 0건).

---

## 8. 다음 작업 (2~4주차)

| 주차 | 작업 | 완료 기준 |
|---|---|---|
| 2주차 | ① Anthropic Admin API 커넥터(cost_report, usage_report) ② OpenAI Costs/Usage API 커넥터 ③ **로컬 수집 스크립트**(Claude Code `~/.claude/projects`, Codex 세션 로그 → `/api/usage/manual` source_type=cli) + 파서 테스트 ④ shadcn/ui 도입 | 2개 서비스 자동 수집이 대시보드에 표시됨 |
| 3주차 | ① Gemini(BigQuery 결제 내보내기) 커넥터 ② Cursor 수동 입력 UX 보강 ③ 서비스 상세 사용량 추이 라인 차트 ④ 갱신 D-day 정렬 | 작동하는 MVP 화면 |
| 4주차 | ① 알림(FR-07: 임계치·수집 실패·갱신 예정). 화면 내 알림과 **카카오톡 "나에게 보내기"** 채널(11장) ② 다크 모드(next-themes) ③ Railway·Vercel 배포, GitHub Actions에서 pytest와 build 실행 ④ 운영 문서 | 배포 버전, MVP 완료 기준 충족 |
| 후속 | CSV 내보내기(FR-08), GitHub Copilot·Azure·AWS Bedrock 커넥터, 다중 사용자(FR-09) | — |

남은 의사결정:
- ~~환율 자동 조회 여부~~ → 자동 조회와 직접 입력 모두 지원하기로 결정하고 구현 완료(4.1장).
- 알림 채널 → 카카오톡 "나에게 보내기"를 1순위로 검토(11장). 화면 내 알림은 기본으로 제공합니다.
- 구독료 이력 관리. 지금은 현재 활성 구독만 월 합계에 반영되므로, 12개월 추이는 API 비용만 보여줍니다.

---

## 9. 로컬 실행

```bash
# 백엔드
cd backend
cp .env.example .env          # JWT_SECRET, CREDENTIALS_KEY, ADMIN_* 입력
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload    # http://localhost:8000/docs
uv run pytest

# 프론트엔드
cd frontend
cp .env.example .env.local    # API_BASE_URL=http://localhost:8000
npm install
npm run dev                   # http://localhost:3000
```

## 10. 배포

- **Railway**: 프로젝트에 PostgreSQL을 추가하고, 루트 디렉터리를 `backend`로 지정한 서비스를 연결합니다. 변수로 `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `JWT_SECRET`, `CREDENTIALS_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`를 설정하고, 필요하면 `KOREAEXIM_API_KEY`도 설정합니다. 컨테이너가 시작될 때 마이그레이션과 seed가 자동으로 실행됩니다. 레플리카는 1개로 유지합니다.
- **Vercel**: 루트 디렉터리를 `frontend`로 지정하고, 환경변수 `API_BASE_URL`에 Railway 서비스 URL을 넣습니다.
- 예상 비용: Railway Hobby 약 $5/월 + Vercel Hobby $0 (도메인 선택 시 연 $10~15 추가)

---

## 11. 카카오톡 알림 검토

결론부터 말하면 가능합니다. 개인 1인용이라면 **카카오톡 메시지 API의 "나에게 보내기"** 가 가장 현실적이고 비용도 들지 않습니다. 기업용 **알림톡**은 사업자 요건 때문에 이 프로젝트에는 맞지 않습니다.

### 11.1 방식 비교

| 방식 | 받는 곳 | 요건 | 비용 | 적합도 |
|---|---|---|---|---|
| **나에게 보내기** (`/v2/api/talk/memo/default/send`) | 본인 카카오톡 "나와의 채팅" | Kakao Developers 앱 생성, 카카오 로그인 활성화, 동의항목 "카카오톡 메시지 전송" 설정, 본인 계정으로 1회 로그인(OAuth) | 무료, 발송량 제한 없음(공식 문서 기준) | ✅ **권장** |
| 친구에게 보내기 (`/v1/api/talk/friends/message/...`) | 같은 앱을 쓰는 카카오 친구 | 비즈 앱 전환, 사업자 정보 심사, "카카오톡 친구/메시지" 권한 신청 | 무료(일일 한도 있음) | ❌ 1인용에는 불필요 |
| 알림톡 (카카오 비즈메시지) | 전화번호 기반 수신 | **사업자등록**, 비즈니스 인증을 받은 카카오톡 채널, 공식 딜러사(발송 대행사) 계약, 템플릿 사전 검수 | 건당 과금 | ❌ 개인 프로젝트에 부적합 |

### 11.2 "나에게 보내기" 구현 설계 (4주차)

```
[설정 화면] "카카오톡 연결" 버튼
   → https://kauth.kakao.com/oauth/authorize?client_id=…&redirect_uri=…&response_type=code&scope=talk_message
   → [백엔드] GET /api/notify/kakao/callback?code=…  → 토큰 발급 → Fernet 암호화 후 DB 저장
[알림 평가 (스케줄러, 수집 직후)] 임계치 초과 / 수집 실패 / 갱신 D-3
   → access token 만료 시 refresh → POST /v2/api/talk/memo/default/send (텍스트 템플릿 + 대시보드 링크)
```

| 항목 | 내용 |
|---|---|
| 토큰 수명 | 액세스 토큰 6시간, 리프레시 토큰 2개월. 만료가 1개월 이하로 남았을 때 갱신하면 새 리프레시 토큰이 발급되고 이전 토큰은 폐기됩니다 → **갱신 응답에 리프레시 토큰이 오면 반드시 교체 저장**해야 합니다 |
| 장기 미사용 | 알림을 보내지 않더라도 스케줄러가 주기적으로 토큰을 갱신하면 연결이 유지됩니다. 갱신에 실패하면 화면에 "카카오톡 재연결 필요"를 표시하고, 알림은 화면 내 알림으로 대신합니다 |
| 저장 | 기존 `service_credentials`와 같은 방식(Fernet 암호화)으로 `notification_channels` 테이블을 추가합니다(channel, encrypted_token, expires_at, enabled) |
| 중복 방지 | `notifications` 테이블에 (종류, 대상 서비스, 기간) 키로 발송 이력을 저장해 같은 알림을 반복해서 보내지 않습니다(예: 임계치 알림은 한도 주기당 1회) |
| 메시지 | 기본 텍스트 템플릿. 링크를 넣으려면 대시보드 도메인을 Kakao Developers 앱의 **Web 플랫폼 사이트 도메인**에 등록해야 합니다(Vercel 주소 또는 커스텀 도메인) |
| Redirect URI | 백엔드 콜백 URL(Railway 주소)을 앱 설정에 등록해야 합니다. 로컬 개발용 URI도 함께 등록합니다 |
| 보안 | 콜백에 `state` 값을 넣어 CSRF를 막고, 토큰은 로그와 응답에 절대 남기지 않습니다 |

### 11.3 준비물 (사용자 작업)

1. [Kakao Developers](https://developers.kakao.com)에서 앱을 만들고 REST API 키를 확인합니다.
2. 카카오 로그인을 활성화하고 Redirect URI를 등록합니다(예: `https://<railway-domain>/api/notify/kakao/callback`).
3. 동의항목에서 "카카오톡 메시지 전송"(`talk_message`)을 설정합니다. 비즈 앱이 아니어도 선택 동의로 설정할 수 있는지 콘솔에서 확인이 필요합니다.
4. 플랫폼 > Web에 대시보드 도메인을 등록합니다.
5. 환경변수 `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`(사용 시), `KAKAO_REDIRECT_URI`를 설정합니다.

### 11.4 리스크

- 카카오 계정에서 앱 연결을 끊거나 리프레시 토큰이 만료되면 발송이 중단됩니다 → 재연결 안내와 화면 내 알림으로 대신합니다.
- 메시지 API 정책은 바뀔 수 있으므로 구현할 때 공식 문서를 다시 확인합니다.
- 카카오톡을 쓰지 않는 상황에 대비해 이메일(예: Resend 무료 플랜)을 2순위 채널로 붙일 수 있도록 알림 채널을 인터페이스로 추상화합니다.

---

## 12. 기기 등록과 PC 에이전트 (Claude Code·Codex)

서버(Railway)는 공유기·방화벽 뒤에 있는 PC에 접속할 수 없으므로, **PC에서 상주하는 에이전트가 서버로 보내는(push) 구조**를 씁니다. 사용 방법은 [user-guide.md](user-guide.md) 8장에 있습니다.

```
[설정 → 기기 관리] 기기 등록 → 기기 토큰 1회 발급 (서버에는 SHA-256 해시만 저장)
[PC 에이전트] 로그인 시 자동 시작(Windows 작업 스케줄러 / macOS launchd, 창 없음)
   1분마다 로그 집계 → 값이 바뀌면 POST /api/agent/usage, 아니면 5분마다 POST /api/agent/heartbeat
[서버] (기기, 서비스, 지표, 기간 시작) 단위로 덮어쓰기 → 기기별 이번 달 누계 합산
[대시보드] 1분마다 자동 갱신, 카드에 합계 + 기기별 값·온라인 상태
```

### 12.1 구성 요소

| 구성 | 파일 | 내용 |
|---|---|---|
| 기기 모델·마이그레이션 | `app/models.py`, `migrations/versions/0003_devices.py` | `devices` 테이블, `usage_snapshots.device_id`와 기기별 유니크 제약 |
| 기기 관리 API | `app/routers/devices.py` | 등록(토큰 1회 반환), 목록(온라인 여부·이번 달 사용량), 토큰 재발급, 폐기 |
| 에이전트 API | `app/routers/agent.py` | `X-Device-Token` 헤더 인증, 사용량 덮어쓰기 업로드, 신호 |
| 에이전트 | `collector/agent.py` | 주기 실행, 변경 감지(해시), 재시도, 폐기 시 종료, `~/.aihub/agent.log` |
| 파서 | `collector/claude_code.py`, `collector/codex.py` | 로그별 사용량 이벤트 추출. 바뀐 파일만 다시 읽음 |
| 설치 스크립트 | `collector/install-agent.ps1`, `collector/install-agent.sh` | Windows 작업 스케줄러 / macOS launchd 에 로그인 시 자동 실행 등록·삭제 |
| 설정 읽기 | `collector/agent.py` | 환경변수 우선, 없으면 `~/.aihub/agent.env`(macOS 기본 방식). launchd 는 셸 환경변수를 넘기지 않기 때문 |

### 12.2 업로드 데이터

에이전트는 매번 **이번 달과 지난달**의 값을 함께 보냅니다. PC가 월말에 꺼져 있었어도 다음 실행 때 지난달 값이 맞춰집니다.

| `metric_code` | 기간 | 값 | `raw` |
|---|---|---|---|
| `tokens_month` | 그달 1일 ~ 말일 | 그달 누계 | 입력·출력·캐시 생성·캐시 읽기, 모델별 합계 |
| `tokens_day` | 해당 날짜 | 그날 합계 | 입력·출력·캐시 생성·캐시 읽기 |

대시보드 카드는 이번 달 `tokens_month`를 기기별로 합산합니다. `tokens_day`는 일별 추이 차트(후속)를 위해 저장만 합니다.

### 12.3 로그별 집계 규칙

| 서비스 | 로그 위치 | 규칙 |
|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` (`CLAUDE_PROJECTS_DIR`) | 어시스턴트 응답의 `message.usage`. 같은 `message.id`가 여러 줄에 반복되므로 한 번만 셈. 실제 로그 1973줄이 고유 메시지 754개였음 |
| Codex | `~/.codex/sessions/**/rollout-*.jsonl`, `archived_sessions` (`CODEX_HOME`) | `event_msg`의 `token_count` 이벤트. `total_token_usage`가 세션 누적값이므로 직전 값과의 차이를 사용량으로 봄. `cached_input_tokens`는 입력에 포함된 값이라 빼서 캐시 읽기로 셈. 포크된 세션은 부모 시각으로 재기록된 이력을 제외. 같은 세션 ID는 한 번만 셈 |

Codex 형식은 openai/codex 저장소의 `codex-rs/protocol` 소스와 공개 분석 자료를 기준으로 했으며, 이 PC에 Codex 로그가 없어 **실제 로그로는 아직 검증하지 않았습니다.** Codex를 쓰는 PC에서 `--dry-run` 결과를 확인해야 합니다.

### 12.4 보안

- 기기 토큰은 무작위 256비트 값이며 서버에는 SHA-256 해시만 저장합니다. 대시보드 비밀번호를 PC에 두지 않습니다.
- 폐기되거나 재발급으로 바뀐 이전 토큰은 즉시 401로 거부되고, 에이전트는 종료합니다.
- 토큰 원문은 다시 보여 주지 않습니다(서버에 없음). 필요하면 재발급합니다.
- macOS의 `~/.aihub/agent.env`는 권한 600(본인만 읽기)으로 만듭니다.
- 에이전트는 로그를 **읽기만** 하고, 서버로 나가는 HTTPS 연결만 씁니다. 대화 내용은 보내지 않고 토큰 수와 모델 이름만 보냅니다.

### 12.5 한계

- 휴대폰 앱·웹 사용량은 PC 로그가 없어 포함되지 않습니다.
- 구독 한도 대비 사용률(%)은 로그에 없어 계산하지 않습니다.
- 같은 PC에서 여러 계정을 쓰면 합쳐집니다.
- "실시간"은 약 1~2분 지연입니다(에이전트 1분 주기 + 화면 1분 자동 갱신).
