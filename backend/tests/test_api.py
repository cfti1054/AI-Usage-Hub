from datetime import date
from decimal import Decimal

import pytest

from app import connectors
from app.connectors.base import Connector, ConnectorContext, ConnectorError, ConnectorResult, CostData, SnapshotData

SECRET = "sk-test-0123456789abcd"


class FakeConnector(Connector):
    key = "fake"
    source_type = "api"

    def fetch(self, ctx: ConnectorContext) -> ConnectorResult:
        return ConnectorResult(
            snapshots=[SnapshotData(metric_code="tokens", used_value=Decimal(300), limit_value=Decimal(1000), unit="tokens")],
            costs=[CostData(amount=Decimal("1.50"), currency="USD", cost_date=date.today())],
        )

    def test_connection(self, ctx: ConnectorContext) -> bool:
        return ctx.secret == SECRET


class FailingConnector(FakeConnector):
    key = "failing"

    def fetch(self, ctx: ConnectorContext) -> ConnectorResult:
        raise ConnectorError(f"401 Unauthorized for key {ctx.secret}")


@pytest.fixture
def fake_connectors():
    connectors.register(FakeConnector())
    connectors.register(FailingConnector())
    yield
    connectors._registry.pop("fake", None)
    connectors._registry.pop("failing", None)


def card(summary: dict, service_id: str) -> dict:
    return next(c for c in summary["services"] if c["id"] == service_id)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_requires_auth(client):
    assert client.get("/api/dashboard/summary").status_code == 401
    assert client.post("/api/auth/login", json={"email": "me@example.com", "password": "wrong"}).status_code == 401


def test_empty_dashboard_shows_no_data_not_zero(client, auth):
    summary = client.get("/api/dashboard/summary", headers=auth).json()
    assert summary["subscription_total"] is None
    assert summary["api_cost_total"] is None
    assert summary["avg_usage_rate"] is None
    assert summary["services_total"] == 4
    assert summary["services_connected"] == 0
    assert {c["data_state"] for c in summary["services"]} == {"no_data"}
    assert all(c["usage_rate"] is None for c in summary["services"])
    assert len(summary["daily_api_costs"]) == 7


def test_subscription_total_needs_fx_for_mixed_currency(client, auth):
    client.post("/api/subscriptions", headers=auth, json={"service_id": "claude-code", "plan_name": "Max", "price": "20", "currency": "USD"})
    client.post("/api/subscriptions", headers=auth, json={"service_id": "cursor", "plan_name": "Pro", "price": "24000", "currency": "KRW"})

    summary = client.get("/api/dashboard/summary", headers=auth).json()
    assert Decimal(summary["subscription_total"]) == Decimal(24000)
    assert summary["conversion_missing"] is True

    client.put("/api/settings/fx", headers=auth, json={"mode": "manual", "fx_usd_krw": "1400", "fx_rate_date": "2026-10-01"})
    summary = client.get("/api/dashboard/summary", headers=auth).json()
    assert Decimal(summary["subscription_total"]) == Decimal(52000)
    assert summary["conversion_missing"] is False
    assert summary["fx"]["rate_date"] == "2026-10-01"


def test_manual_entry(client, auth):
    period = date.today().strftime("%Y-%m")
    res = client.post(
        "/api/usage/manual",
        headers=auth,
        json={
            "service_id": "cursor",
            "usage": {"metric_code": "credits", "used_value": "34", "limit_value": "100", "unit": "credits"},
            "cost": {"amount": "12000", "currency": "KRW", "billing_period": period},
        },
    )
    assert res.status_code == 201

    c = card(client.get("/api/dashboard/summary", headers=auth).json(), "cursor")
    assert c["data_state"] == "ok"
    assert c["usage_rate"] == pytest.approx(34.0)
    assert c["usage"]["source_type"] == "manual"
    assert Decimal(c["month_api_cost"]) == Decimal(12000)

    costs = client.get(f"/api/costs?period={period}", headers=auth).json()
    assert Decimal(costs["api_cost_total"]) == Decimal(12000)
    trend = client.get("/api/costs/trend?months=12", headers=auth).json()["months"]
    assert len(trend) == 12 and trend[-1]["period"] == period


def test_manual_usage_without_value_is_unavailable(client, auth):
    client.post("/api/usage/manual", headers=auth, json={"service_id": "cursor", "usage": {"metric_code": "credits"}})
    c = card(client.get("/api/dashboard/summary", headers=auth).json(), "cursor")
    assert c["data_state"] == "unavailable"
    assert c["usage_rate"] is None


def test_sync_without_connector_is_rejected(client, auth):
    res = client.post("/api/services/cursor/sync", headers=auth)
    assert res.status_code == 400


def test_sync_success_and_failure(client, auth, fake_connectors):
    client.post("/api/services", headers=auth, json={"id": "fake-api", "name": "Fake", "provider": "Test", "collection_method": "api", "connector": "fake"})
    client.post("/api/services", headers=auth, json={"id": "bad-api", "name": "Bad", "provider": "Test", "collection_method": "api", "connector": "failing"})

    # 키가 없으면 실패로 기록
    job = client.post("/api/services/fake-api/sync", headers=auth).json()
    assert job["status"] == "failed" and "API 키" in job["error_message"]

    assert client.put("/api/services/fake-api/credential", headers=auth, json={"secret": SECRET}).json()["hint"] == "****abcd"
    assert client.post("/api/services/fake-api/test", headers=auth).json()["ok"] is True
    job = client.post("/api/services/fake-api/sync", headers=auth).json()
    assert job["status"] == "success" and job["records_count"] == 2
    # 같은 날 재수집해도 비용은 upsert 되어 중복되지 않는다
    client.post("/api/services/fake-api/sync", headers=auth)

    client.put("/api/services/bad-api/credential", headers=auth, json={"secret": SECRET})
    job = client.post("/api/services/bad-api/sync", headers=auth).json()
    assert job["status"] == "failed"
    assert SECRET not in job["error_message"]

    services = client.get("/api/services", headers=auth).json()
    assert all(SECRET not in str(s) for s in services)

    client.put("/api/settings/fx", headers=auth, json={"mode": "manual", "fx_usd_krw": "1400"})
    summary = client.get("/api/dashboard/summary", headers=auth).json()
    ok = card(summary, "fake-api")
    assert ok["data_state"] == "ok" and ok["usage_rate"] == pytest.approx(30.0)
    assert Decimal(ok["month_api_cost"]) == Decimal(2100)
    assert card(summary, "bad-api")["data_state"] == "error"

    jobs = client.get("/api/sync-jobs?status=failed", headers=auth).json()
    assert {j["service_id"] for j in jobs} == {"fake-api", "bad-api"}


def test_disable_service(client, auth):
    res = client.patch("/api/services/gemini-cli", headers=auth, json={"enabled": False})
    assert res.json()["enabled"] is False
    summary = client.get("/api/dashboard/summary", headers=auth).json()
    assert summary["services_total"] == 3
    assert card(summary, "gemini-cli")["data_state"] == "disabled"
