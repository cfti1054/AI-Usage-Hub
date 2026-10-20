---
name: add-connector
description: AI Usage Hub에 자동 수집 커넥터(Anthropic·OpenAI·Gemini 등 API 비용 조회, 또는 CLI 로그 파서)를 추가하는 절차. "커넥터 추가", "Anthropic 비용 연동", "OpenAI 커넥터", "자동 수집 붙여줘"처럼 외부 서비스 수집 구현을 요청할 때 사용한다.
---

# add-connector — 커넥터 추가 절차

커넥터는 **외부 데이터를 정규화해 반환만** 합니다. DB 저장과 `sync_jobs` 기록은 `app/sync.py`가 맡습니다. 커넥터 안에서 DB 세션을 열거나 직접 저장하지 마세요.

## 0. 먼저 확인할 것

- 설계 근거는 `docs/initial-development.md` 1.2장(외부 사실 확인 결과)에 있습니다. 대상 서비스의 **공식 API 경로**가 거기 적힌 것과 같은지 공식 문서로 다시 확인합니다. 비공식 엔드포인트(예: 브라우저 세션 키 기반)는 쓰지 않습니다.
- 인증 방식을 확인합니다. Anthropic·OpenAI 비용 API는 **Admin 키**가 필요하고 조직 단위로만 제공됩니다. 개인 구독 한도(Pro/Max, ChatGPT 요금제)는 API가 없으니 이 스킬의 대상이 아닙니다.
- 기존 구현을 먼저 읽습니다: `backend/app/connectors/base.py`, `backend/app/connectors/__init__.py`, `backend/app/sync.py`, `backend/tests/test_api.py`의 `FakeConnector` 픽스처.

## 1. 구현 파일 추가

`backend/app/connectors/<서비스명>.py`에 `Connector`를 구현합니다.

```python
class AnthropicCostConnector(Connector):
    key = "anthropic"          # ai_services.connector 값과 일치해야 함
    source_type = "api"         # "api" 또는 "cli"
    requires_secret = True

    def fetch(self, ctx: ConnectorContext) -> ConnectorResult: ...
    def test_connection(self, ctx: ConnectorContext) -> bool: ...
```

지켜야 할 규칙:

- HTTP 호출은 `httpx`를 쓰고, 타임아웃을 명시합니다.
- 인증 실패·네트워크 오류·응답 형식 오류는 `ConnectorError`로 올립니다. 메시지에 `ctx.secret`을 넣지 않습니다 (`sync.py`가 마스킹하지만 이중으로 막습니다).
- 지표를 제공하지 않는 서비스는 `SnapshotData(status="unavailable", used_value=None)`로 반환합니다. **0으로 채우지 않습니다.**
- 비용은 `CostData(cost_type="api_usage", granularity="day")`를 기본으로 하고, 금액은 `Decimal`로 다룹니다. `float`를 쓰지 않습니다.
- 비용은 늦게 확정될 수 있으므로 `ConnectorContext.since`~`until` 범위를 그대로 받아 다시 가져옵니다 (`sync.py`의 35일 lookback이 upsert로 처리합니다).
- 통화는 원 통화 그대로 반환합니다. 환산은 `app/fx.py`와 `app/money.py`가 맡습니다.

## 2. 등록

현재 `register(` 호출이 코드에 하나도 없습니다 (커넥터가 아직 없음). 등록 위치는 이번에 정합니다. 권장:

- `backend/app/connectors/__init__.py` 맨 아래에서 구현 모듈을 import하고 `register(...)`를 호출합니다.
- 순환 import가 생기면 `app/main.py` 시작 시점으로 옮깁니다.

등록 후 `available_connectors()`에 키가 보이는지 확인합니다.

## 3. 서비스 연결 데이터

`ai_services` 행의 `connector` 값을 키와 맞춥니다. 기본 서비스 seed(`app/seed.py`)에 이미 있는 서비스라면 seed를 고치기보다 마이그레이션이나 설정 화면으로 연결하는 방법을 먼저 검토하고 사용자에게 알립니다. 기존 데이터 변경은 되돌리기 어려우니 실행 전에 확인합니다.

## 4. 테스트

`backend/tests/test_connectors_<서비스>.py`를 추가하고 최소 다음을 검증합니다.

- 정상 응답 → `SnapshotData`·`CostData` 변환 (금액 `Decimal`, 날짜 범위)
- 401/403 → `ConnectorError`, 메시지에 키가 없음
- 지표가 없을 때 `status="unavailable"`이고 0이 아님
- 같은 기간을 두 번 수집해도 `cost_records`가 중복되지 않음 (upsert)
- 네트워크 호출은 `httpx.MockTransport` 또는 monkeypatch로 가짜 응답을 씁니다. 실제 API를 테스트에서 호출하지 않습니다.

```bash
cd backend && uv run pytest -q
```

## 5. 문서와 마무리

- `docs/implementation-status.md`: 2장(미구현)의 해당 항목을 1장(완료)으로 옮기고 테스트 건수를 갱신합니다.
- `docs/initial-development.md` 1.2장: 공식 경로·인증 방식을 확인한 결과를 적습니다.
- `docs/user-guide.md`: 사용자가 해야 할 설정(Admin 키 발급 위치 등)이 생기면 추가합니다.
- 마지막에 `/verify`를 실행합니다.

## 보고할 것

- 실제 API 호출은 이 환경에서 검증하지 않았다면 그렇다고 씁니다. 테스트는 가짜 응답 기준입니다.
- 실제 키로 한 번 연결해 보는 확인은 사용자가 직접 해야 합니다. 키를 채팅이나 파일에 적어 달라고 요청하지 마세요.
