# AI Usage Hub — Claude Code 작업 지침

Claude Code, Codex, Cursor, Gemini CLI 등 여러 AI 서비스의 구독료·사용량·API 비용을 한 화면에서 보는 **개인용(1인)** 대시보드입니다. 세부 설계는 `docs/`에 있으니 필요할 때 먼저 읽으세요.

- `docs/initial-development.md` — 확정 설계, 결정 이유, 로컬 실행·배포
- `docs/implementation-status.md` — 구현 범위, 미구현 목록, 알려진 제한
- `docs/erd.md` — DB ERD (모델에서 자동 생성되는 구역 포함)
- `docs/user-guide.md` — 화면 사용법, 수집기 설치, 문제 해결

## 구조

| 경로 | 역할 | 배포 |
|---|---|---|
| `backend/app/` | FastAPI 라우터, SQLAlchemy 모델, 커넥터, 스케줄러 | Railway (Dockerfile, 레플리카 1개 고정) |
| `backend/app/connectors/` | 외부 서비스 커넥터 (`Connector` 인터페이스, 레지스트리) | |
| `backend/collector/` | 사용자 PC에서 도는 에이전트 (Claude Code·Codex 로그 집계) | PC에 설치 (`install-agent.ps1` / `.sh`) |
| `backend/migrations/` | Alembic 마이그레이션 (`0001`~`0005`) | |
| `backend/tests/` | pytest (51건) | |
| `frontend/src/app/` | Next.js 15 App Router 화면 | Vercel |
| `frontend/src/lib/` | 백엔드 호출(`api.ts`), 포맷·기간 유틸 | |
| `scripts/` | 앱 아이콘 생성 스크립트 | |

## 명령

```bash
# 백엔드 (작업 디렉터리: backend/)
uv sync                              # 의존성 설치
uv run pytest                        # 테스트 전체 (SQLite 인메모리, 외부 호출 없음)
uv run pytest tests/test_api.py -k 이름   # 일부만
uv run python -m app.erd             # 모델 변경 후 docs/erd.md 재생성
uv run python -m app.erd --check     # 최신인지 검사 (test_erd.py가 같은 검사를 함)
uv run alembic upgrade head          # 로컬 DB 마이그레이션 (PostgreSQL 필요)
uv run uvicorn app.main:app --reload # http://localhost:8000/docs

# 프론트엔드 (작업 디렉터리: frontend/)
npm install
npm run lint                         # tsc --noEmit (이 프로젝트의 타입 검사 겸 린트)
npm run build                        # 배포 전 빌드 확인
npm run dev                          # http://localhost:3000
```

변경 후 최소 검증: 백엔드를 건드렸으면 `uv run pytest`, 프론트를 건드렸으면 `npm run lint`. 스키마를 건드렸으면 `app.erd --check`까지. 전부 통과해야 완료로 봅니다. `/verify` 스킬이 이 순서를 자동으로 돌립니다.

## 반드시 지킬 규칙

**보안·데이터 무결성 (이 프로젝트의 핵심 원칙)**
- API 키·기기 토큰·위젯 토큰은 평문으로 DB에 저장하지 않습니다. 외부 서비스 키는 Fernet 암호화(`app/credentials.py`), 기기·위젯 토큰은 해시만 저장하고 발급 시 1회만 보여 줍니다.
- 오류 메시지·로그에 키가 들어가면 안 됩니다. 커넥터 오류는 `mask_secrets`를 거쳐 `sync_jobs.error_message`에 저장됩니다.
- 응답에는 키의 끝 4자리 힌트만 노출합니다.
- 백엔드 API는 JWT 필수입니다 (`/health` 제외). 토큰 종류별 권한을 섞지 않습니다 (위젯 토큰은 요약 조회 전용, 기기 토큰은 에이전트 업로드 전용).
- 프론트엔드는 백엔드를 **서버 측에서만** 호출합니다. 브라우저에 백엔드 주소나 토큰을 노출하는 코드를 만들지 않습니다.

**데이터 의미**
- 수집 실패·데이터 없음을 **0으로 채우지 않습니다.** 지표가 없으면 `status='unavailable'`, 금액·사용률은 `null`로 두고 화면에서는 "—" 또는 "데이터 없음"으로 표시합니다.
- 구독 한도(`subscriptions`)와 API 종량 비용(`cost_records`)은 분리합니다. 구독료는 `subscriptions`에서만 계산합니다.
- 모든 스냅샷·비용에 `source_type`(api / cli / manual)을 저장하고 화면에 표시합니다.
- 수집 실패 시 기존 데이터는 지우지 않고 실패 이력만 `sync_jobs`에 남깁니다.
- 기기 에이전트 업로드는 **덮어쓰기**입니다 (월·일 누계를 다시 보내므로 중복 합산이 되면 안 됩니다).

**코드 변경 규칙**
- DB 모델을 바꾸면: Alembic 마이그레이션 파일을 추가하고 (`alembic revision --autogenerate -m "..."`, 생성 후 내용을 직접 검토), `uv run python -m app.erd`로 ERD를 재생성합니다. `test_erd.py`가 이를 강제합니다.
- `backend/collector/`는 **표준 라이브러리만** 씁니다. 사용자 PC에 백엔드 패키지를 설치하지 않는 것이 설계 전제입니다. 외부 패키지를 import하지 마세요.
- 커넥터를 추가할 때는 `/add-connector` 스킬을 따릅니다.
- `.sh` 파일은 LF 줄바꿈을 유지합니다 (`.gitattributes`).
- 설정값은 `app/config.py`의 `Settings`로 읽습니다. 새 환경변수를 추가하면 `backend/.env.example`에도 같이 적습니다.
- 미구현 항목을 "완료"처럼 문서에 쓰지 않습니다. 기능이 바뀌면 `docs/implementation-status.md`의 표와 테스트 건수를 함께 갱신합니다.

**문서·커밋**
- 문서는 한국어로 씁니다. 코드 식별자와 기술 용어는 원문을 유지합니다.
- 사용자 설명(`docs/user-guide.md`)이 바뀌는 기능이면 해당 장도 갱신합니다.
- 커밋 메시지는 기존 이력 형식을 따릅니다: `feat : YYYY-MM-DD / 요약` 첫 줄, 이어서 `- ` 항목으로 변경 내용. 커밋과 푸시는 사용자가 요청할 때만 합니다.

## 배포 주의

- Railway 레플리카는 **1개**여야 합니다. APScheduler가 프로세스 안에서 돌기 때문입니다 (`backend/railway.toml`).
- 컨테이너 시작 시 `alembic upgrade head` → `python -m app.seed` → 서버 순서로 실행됩니다. 마이그레이션은 되돌리기 어려울 수 있으니 실행 전에 내용을 확인합니다.
- Vercel 환경변수 `API_BASE_URL`은 Railway 주소입니다.
- 현재 CI가 없으므로 배포 전 로컬에서 `pytest`와 `npm run build`를 직접 돌립니다.

## 현재 상태 한눈에 (2026-10-19 기준)

- 완료: 인증, 서비스·구독 관리, 기기 등록·에이전트(Claude Code·Codex), Cursor CSV 업로드, 대시보드 월 선택, 위젯 API, 환율 자동 조회, 수집 엔진·스케줄러.
- 미구현 (다음 작업 후보): Anthropic·OpenAI·Gemini 비용 커넥터(현재 자동 수집 대상 없음), 알림(카카오톡 "나에게 보내기"), CI, 실제 아이폰·Mac 검증.
- 실제 PC 로그와 Mac 설치는 아직 검증되지 않았습니다. 이 부분을 "검증됨"으로 말하지 않습니다.
