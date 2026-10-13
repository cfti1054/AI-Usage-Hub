from decimal import Decimal

from tests.test_imports import SAMPLE

PAST = "2020-01"


def summary(client, auth, period: str | None = None) -> dict:
    url = "/api/dashboard/summary" + (f"?period={period}" if period else "")
    res = client.get(url, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def card(data: dict, service_id: str) -> dict:
    return next(c for c in data["services"] if c["id"] == service_id)


def test_default_is_current_month(client, auth):
    data = summary(client, auth)
    assert data["is_current_month"] is True and data["period"] == data["current_period"]
    assert len(data["daily_api_costs"]) == 7


def test_past_month_shows_that_months_device_csv_and_api_cost(client, auth):
    # 기기 에이전트: 2020-01 누계
    token = client.post("/api/devices", headers=auth, json={"name": "집"}).json()["token"]
    client.post(
        "/api/agent/usage",
        headers={"X-Device-Token": token},
        json={"snapshots": [{"service_id": "claude-code", "metric_code": "tokens_month", "used_value": 700,
                             "period_start": "2020-01-01", "period_end": "2020-01-31"}]},
    )
    # 수동 월 비용: 2020-01
    client.post("/api/usage/manual", headers=auth, json={
        "service_id": "codex", "cost": {"amount": "5000", "currency": "KRW", "billing_period": PAST}})

    past = summary(client, auth, PAST)
    assert past["period"] == PAST and past["is_current_month"] is False
    assert past["next_sync_at"] is None
    assert len(past["daily_api_costs"]) == 31 and past["daily_api_costs"][0]["date"] == "2020-01-01"
    assert Decimal(card(past, "claude-code")["usage"]["used_value"]) == Decimal(700)
    assert Decimal(past["api_cost_total"]) == Decimal(5000)

    current = summary(client, auth)
    assert card(current, "claude-code")["devices"] == []  # 지난달 값은 이번 달에 나오지 않음
    assert current["api_cost_total"] is None


def test_csv_month_selection(client, auth):
    client.post("/api/services/cursor/usage-imports", headers=auth, json={"filename": "aug.csv", "content": SAMPLE})
    aug = card(summary(client, auth, "2026-08"), "cursor")
    assert aug["data_state"] == "ok"
    assert Decimal(aug["usage"]["used_value"]) == Decimal(237734 + 77785 + 883583 + 88850)
    assert card(summary(client, auth, "2026-07"), "cursor")["data_state"] == "no_data"


def test_manual_snapshot_only_counts_in_its_month(client, auth):
    client.post("/api/usage/manual", headers=auth, json={
        "service_id": "cursor", "usage": {"metric_code": "credits", "used_value": "10", "limit_value": "100"}})
    assert card(summary(client, auth), "cursor")["usage_rate"] == 10.0
    assert card(summary(client, auth, PAST), "cursor")["data_state"] == "no_data"


def test_invalid_period_rejected(client, auth):
    assert client.get("/api/dashboard/summary?period=2026-13", headers=auth).status_code == 422
    assert client.get("/api/dashboard/summary?period=202610", headers=auth).status_code == 422
