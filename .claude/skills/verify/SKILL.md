---
name: verify
description: 변경 사항을 프로젝트 검증 순서대로 실행한다 (pytest, ERD 최신 검사, 프론트 타입 검사·빌드). 코드를 수정한 뒤 "검증해줘", "테스트 돌려줘", "완료 전 확인" 같은 요청이나 작업을 끝낼 때 사용한다.
---

# verify — 변경 검증

이 저장소의 검증 순서를 실행하고, 결과를 있는 그대로 보고합니다.

## 1. 무엇이 바뀌었는지 확인

```bash
git status --short
git diff --stat
```

변경 경로로 실행 범위를 정합니다.

| 바뀐 경로 | 실행할 검증 |
|---|---|
| `backend/` | 2 → 3 |
| `frontend/` | 4 |
| `backend/app/models.py` 또는 `backend/migrations/` | 2 → 3 → 5 |
| 문서만 (`docs/`, `*.md`) | 없음. 문서 링크와 표 형식만 눈으로 확인 |

## 2. 백엔드 테스트

```bash
cd backend && uv run pytest -q
```

- 기준: 현재 51건 통과.
- 실패하면 실패한 테스트 이름과 assertion 메시지를 그대로 보고합니다. 원인을 추측해서 고친 뒤 "통과"라고 쓰지 마세요.
- 건수가 늘거나 줄었으면 `docs/implementation-status.md`의 테스트 건수를 갱신해야 하는지 알려 줍니다.

## 3. ERD 최신 검사

```bash
cd backend && uv run python -m app.erd --check
```

불일치하면 `uv run python -m app.erd`로 재생성하고, 생성된 구역 밖의 설명은 손대지 않았는지 `git diff docs/erd.md`로 확인합니다.

## 4. 프론트엔드 타입 검사

```bash
cd frontend && npm run lint
```

`tsc --noEmit`입니다. 화면 동작을 바꿨다면 5를 추가로 실행합니다.

## 5. 프론트엔드 빌드 (배포 전이나 화면 변경 시)

```bash
cd frontend && npm run build
```

## 6. 보고 형식

| 단계 | 결과 | 비고 |
|---|---|---|
| pytest | 통과 / 실패 (실패 테스트명) | |
| ERD 검사 | 최신 / 재생성 필요 | |
| tsc | 통과 / 실패 (파일:줄) | |
| build | 실행 안 함 / 통과 / 실패 | |

실행하지 않은 단계는 "실행 안 함"이라고 쓰고, 이유를 한 줄로 덧붙입니다. 전부 통과해도 실기기 검증(아이폰 위젯, Mac 설치, 실제 PC 로그)은 이 스킬로 검증되지 않는다는 점을 함께 적습니다.
