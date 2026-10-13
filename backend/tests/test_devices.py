from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models import Device


def month_start() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).date().replace(day=1).isoformat()


def month_row(service_id: str, value: int, start: str | None = None) -> dict:
    start = start or month_start()
    return {
        "service_id": service_id,
        "metric_code": "tokens_month",
        "used_value": value,
        "period_start": start,
        "period_end": start[:8] + "28",
        "raw": {"input": value, "output": 0, "cache_creation": 0, "cache_read": 0},
    }


def register(client, auth, name: str) -> tuple[int, str]:
    res = client.post("/api/devices", headers=auth, json={"name": name})
    assert res.status_code == 201
    body = res.json()
    assert body["token"].startswith("aihub_dev_")
    return body["device"]["id"], body["token"]


def upload(client, token: str, rows: list[dict]):
    return client.post("/api/agent/usage", headers={"X-Device-Token": token}, json={"snapshots": rows})


def card(client, auth, service_id: str) -> dict:
    summary = client.get("/api/dashboard/summary", headers=auth).json()
    return next(c for c in summary["services"] if c["id"] == service_id)


def test_device_token_is_shown_once_and_stored_hashed(client, auth, session_factory):
    _, token = register(client, auth, "집 데스크톱")
    devices = client.get("/api/devices", headers=auth).json()
    assert token not in str(devices)
    with session_factory() as db:
        stored = db.query(Device).one()
        assert stored.token_hash != token and len(stored.token_hash) == 64

    assert client.post("/api/devices", headers=auth, json={"name": "집 데스크톱"}).status_code == 409
    assert client.post("/api/devices", headers=auth, json={"name": "   "}).status_code == 422


def test_agent_requires_valid_unrevoked_token(client, auth):
    device_id, token = register(client, auth, "노트북")
    assert upload(client, "wrong", [month_row("claude-code", 1)]).status_code == 401
    assert client.post("/api/agent/heartbeat").status_code == 401
    assert client.post("/api/agent/heartbeat", headers={"X-Device-Token": token}).json()["ok"] is True

    client.post(f"/api/devices/{device_id}/revoke", headers=auth)
    assert upload(client, token, [month_row("claude-code", 1)]).status_code == 401
    assert upload(client, "x", []).status_code == 401  # 인증이 검증보다 먼저


def test_unknown_service_rejected(client, auth):
    _, token = register(client, auth, "노트북")
    res = upload(client, token, [month_row("no-such-service", 1)])
    assert res.status_code == 422 and "no-such-service" in res.text


def test_devices_are_summed_and_reupload_overwrites(client, auth):
    _, home = register(client, auth, "집")
    _, office = register(client, auth, "회사")

    assert upload(client, home, [month_row("claude-code", 1000), month_row("codex", 30)]).json() == {"saved": 2}
    upload(client, office, [month_row("claude-code", 500)])
    # 같은 기간 값을 다시 올리면 행이 늘지 않고 덮어쓴다
    upload(client, home, [month_row("claude-code", 1200)])

    c = card(client, auth, "claude-code")
    assert c["data_state"] == "ok"
    assert Decimal(c["usage"]["used_value"]) == Decimal(1700)
    assert c["usage"]["source_type"] == "cli"
    assert {d["name"]: Decimal(d["used_value"]) for d in c["devices"]} == {"집": 1200, "회사": 500}
    assert all(d["online"] for d in c["devices"])
    assert Decimal(card(client, auth, "codex")["usage"]["used_value"]) == Decimal(30)

    detail = client.get("/api/services/claude-code/usage", headers=auth).json()
    assert len(detail["devices"]) == 2 and detail["latest"] == []
    assert detail["devices"][0]["breakdown"]["input"] in (1200, 500)

    devices = {d["name"]: d for d in client.get("/api/devices", headers=auth).json()}
    assert Decimal(devices["집"]["month_usage"]["claude-code"]) == Decimal(1200)
    assert Decimal(devices["집"]["month_usage"]["codex"]) == Decimal(30)


def test_last_month_device_rows_do_not_show_as_current(client, auth):
    _, token = register(client, auth, "집")
    upload(client, token, [month_row("claude-code", 999, start="2020-01-01")])
    c = card(client, auth, "claude-code")
    assert c["data_state"] == "no_data" and c["devices"] == []


def test_revoked_device_usage_stays_in_total_and_goes_offline(client, auth, session_factory):
    device_id, token = register(client, auth, "잃어버린 노트북")
    upload(client, token, [month_row("claude-code", 400)])
    revoked = client.post(f"/api/devices/{device_id}/revoke", headers=auth).json()
    assert revoked["revoked_at"] is not None and revoked["online"] is False

    c = card(client, auth, "claude-code")
    assert Decimal(c["usage"]["used_value"]) == Decimal(400)
    assert c["devices"][0]["revoked"] is True


def test_rotate_token_invalidates_old_and_keeps_usage(client, auth):
    device_id, old = register(client, auth, "맥북")
    upload(client, old, [month_row("claude-code", 300)])

    res = client.post(f"/api/devices/{device_id}/rotate-token", headers=auth)
    assert res.status_code == 200
    new = res.json()["token"]
    assert new != old and new.startswith("aihub_dev_")

    assert upload(client, old, [month_row("claude-code", 1)]).status_code == 401
    assert upload(client, new, [month_row("claude-code", 350)]).status_code == 200
    c = card(client, auth, "claude-code")
    assert [(d["name"], Decimal(d["used_value"])) for d in c["devices"]] == [("맥북", Decimal(350))]

    client.post(f"/api/devices/{device_id}/revoke", headers=auth)
    assert client.post(f"/api/devices/{device_id}/rotate-token", headers=auth).status_code == 409
    assert client.post("/api/devices/99999/rotate-token", headers=auth).status_code == 404


def test_device_goes_offline_after_silence(client, auth, session_factory):
    _, token = register(client, auth, "집")
    upload(client, token, [month_row("claude-code", 1)])
    with session_factory() as db:
        device = db.query(Device).one()
        device.last_seen_at = datetime.now(UTC) - timedelta(minutes=10)
        db.commit()
    assert card(client, auth, "claude-code")["devices"][0]["online"] is False
