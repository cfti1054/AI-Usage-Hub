from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import WidgetToken


def month_row(service_id: str, value: int) -> dict:
    start = datetime.now(ZoneInfo("Asia/Seoul")).date().replace(day=1).isoformat()
    return {"service_id": service_id, "metric_code": "tokens_month", "used_value": value,
            "period_start": start, "period_end": start[:8] + "28"}


def create_token(client, auth, name="내 아이폰") -> tuple[int, str]:
    res = client.post("/api/widget-tokens", headers=auth, json={"name": name})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["token"].startswith("aihub_wgt_")
    return body["widget_token"]["id"], body["token"]


def summary(client, token: str):
    return client.get("/api/widget/summary", headers={"X-Widget-Token": token})


def test_token_shown_once_hashed_and_unique_name(client, auth, session_factory):
    _, token = create_token(client, auth)
    assert token not in str(client.get("/api/widget-tokens", headers=auth).json())
    with session_factory() as db:
        assert db.query(WidgetToken).one().token_hash != token
    assert client.post("/api/widget-tokens", headers=auth, json={"name": "내 아이폰"}).status_code == 409


def test_summary_requires_valid_widget_token(client, auth):
    token_id, token = create_token(client, auth)
    assert client.get("/api/widget/summary").status_code == 401
    assert summary(client, "wrong").status_code == 401
    # 대시보드 JWT 나 기기 토큰으로는 위젯 API 를 쓸 수 없고, 위젯 토큰으로는 다른 API 를 쓸 수 없다
    assert client.get("/api/widget/summary", headers=auth).status_code == 401
    assert client.get("/api/dashboard/summary", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.post("/api/agent/heartbeat", headers={"X-Device-Token": token}).status_code == 401

    assert summary(client, token).status_code == 200
    client.post(f"/api/widget-tokens/{token_id}/revoke", headers=auth)
    assert summary(client, token).status_code == 401


def test_empty_summary_uses_null_not_zero(client, auth):
    _, token = create_token(client, auth)
    data = summary(client, token).json()
    assert data["spend_total"] is None and data["tokens_total"] is None
    assert data["services"] == [] and data["updated_at"] is None
    assert len(data["daily_api_costs"]) == 7
    assert data["period_label"].endswith("월")


def test_summary_matches_dashboard(client, auth):
    device = client.post("/api/devices", headers=auth, json={"name": "집"}).json()["token"]
    client.post("/api/agent/usage", headers={"X-Device-Token": device},
                json={"snapshots": [month_row("claude-code", 190_000_000), month_row("codex", 3_200_000)]})
    client.post("/api/subscriptions", headers=auth,
                json={"service_id": "claude-code", "plan_name": "Max", "price": "166000", "currency": "KRW"})
    period = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m")
    client.post("/api/usage/manual", headers=auth, json={
        "service_id": "codex", "cost": {"amount": "20700", "currency": "KRW", "billing_period": period}})

    _, token = create_token(client, auth)
    data = summary(client, token).json()
    assert data["spend_total"] == 186_700 and data["subscription_total"] == 166_000 and data["api_cost_total"] == 20_700
    assert data["tokens_total"] == 193_200_000
    assert [(s["id"], s["tokens"], s["source"], s["color"]) for s in data["services"]] == [
        ("claude-code", 190_000_000, "기기 1대", "#E07A55"),
        ("codex", 3_200_000, "기기 1대", "#1DB98B"),
    ]
    assert abs(sum(s["share"] for s in data["services"]) - 1) < 0.001
    assert data["services"][0]["online"] is True and data["updated_at"] is not None

    tokens = client.get("/api/widget-tokens", headers=auth).json()
    assert tokens[0]["last_used_at"] is not None  # 마지막 사용 시각 기록
