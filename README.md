# AI-Usage-Hub

Claude Code, Codex, Cursor, Gemini CLI 등 여러 AI 서비스의 구독료·사용량·API 비용을 한 화면에서 보는 개인용 대시보드.

- `backend/` — FastAPI + SQLAlchemy + Alembic + APScheduler (Railway)
- `frontend/` — Next.js 15 + Tailwind CSS + Recharts (Vercel)

## 문서

| 문서 | 내용 |
|---|---|
| [docs/user-guide.md](docs/user-guide.md) | 사용 설명서 — 화면 사용법, 수집기 실행, 문제 해결 |
| [docs/implementation-status.md](docs/implementation-status.md) | 구현 범위 — 완료·미구현 기능, 알려진 제한 |
| [docs/erd.md](docs/erd.md) | DB ERD와 테이블 명세 (모델에서 자동 생성) |
| [docs/initial-development.md](docs/initial-development.md) | 설계 검증 결과, 확정 설계, 로컬 실행·배포 방법 |

빠른 시작은 [docs/initial-development.md](docs/initial-development.md#9-로컬-실행) 참고.
