from datetime import date
from decimal import Decimal

import httpx
import pytest

from app import fx
from app.config import get_settings


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_frankfurter_parse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["base"] == "USD"
        return httpx.Response(200, json={"amount": 1.0, "base": "USD", "date": "2026-10-09", "rates": {"KRW": 1341.49}})

    quote = fx.fetch_frankfurter(_client(handler))
    assert quote == fx.FxQuote(rate=Decimal("1341.4900"), rate_date=date(2026, 10, 9), source="frankfurter")


def test_koreaexim_walks_back_over_weekend():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        day = request.url.params["searchdate"]
        calls.append(day)
        if day == "20261009":  # 금요일
            return httpx.Response(200, json=[
                {"result": 1, "cur_unit": "JPY(100)", "deal_bas_r": "905.1"},
                {"result": 1, "cur_unit": "USD", "deal_bas_r": "1,352.5"},
            ])
        return httpx.Response(200, json=[])  # 주말: 빈 목록

    quote = fx.fetch_koreaexim(_client(handler), "key", date(2026, 10, 11))
    assert calls == ["20261011", "20261010", "20261009"]
    assert quote.rate == Decimal("1352.5000") and quote.rate_date == date(2026, 10, 9) and quote.source == "koreaexim"


def test_koreaexim_auth_error():
    def handler(request):
        return httpx.Response(200, json=[{"result": 3, "cur_unit": None, "deal_bas_r": None}])

    with pytest.raises(fx.FxError, match="result=3"):
        fx.fetch_koreaexim(_client(handler), "key", date(2026, 10, 9))


def test_falls_back_to_frankfurter_and_masks_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "koreaexim_api_key", "SECRET-KEY")

    def handler(request: httpx.Request) -> httpx.Response:
        if "koreaexim" in request.url.host:
            return httpx.Response(500)
        return httpx.Response(200, json={"date": "2026-10-09", "rates": {"KRW": 1341.49}})

    assert fx.fetch_usd_krw(_client(handler)).source == "frankfurter"

    def all_fail(request):
        return httpx.Response(503)

    with pytest.raises(fx.FxError) as err:
        fx.fetch_usd_krw(_client(all_fail))
    assert "SECRET-KEY" not in str(err.value)


QUOTE = fx.FxQuote(rate=Decimal("1350.1234"), rate_date=date(2026, 10, 9), source="frankfurter")


def test_auto_mode_fetches_and_shows_source(client, auth, monkeypatch):
    monkeypatch.setattr(fx, "fetch_usd_krw", lambda client=None: QUOTE)
    res = client.put("/api/settings/fx", headers=auth, json={"mode": "auto"}).json()
    assert res["fx_mode"] == "auto" and Decimal(res["fx_usd_krw"]) == QUOTE.rate
    assert res["fx_source"] == "frankfurter" and res["fx_error"] is None

    summary = client.get("/api/dashboard/summary", headers=auth).json()
    assert summary["fx"]["source_label"] == "ECB 기준환율(Frankfurter)"
    assert summary["fx"]["rate_date"] == "2026-10-09"


def test_manual_mode_is_not_overwritten(client, auth, monkeypatch, session_factory):
    monkeypatch.setattr(fx, "fetch_usd_krw", lambda client=None: QUOTE)
    res = client.put("/api/settings/fx", headers=auth, json={"mode": "manual", "fx_usd_krw": "1400"}).json()
    assert res["fx_source"] == "manual" and res["fx_rate_date"] is not None

    # 스케줄러 갱신과 수동 새로고침 모두 직접 입력값을 건드리지 않는다
    with session_factory() as db:
        assert fx.refresh_auto_settings(db) == 0
    assert client.post("/api/settings/fx/refresh", headers=auth).status_code == 409
    assert Decimal(client.get("/api/settings", headers=auth).json()["fx_usd_krw"]) == Decimal(1400)

    assert client.put("/api/settings/fx", headers=auth, json={"mode": "manual"}).status_code == 422


def test_auto_failure_keeps_previous_rate(client, auth, monkeypatch):
    client.put("/api/settings/fx", headers=auth, json={"mode": "manual", "fx_usd_krw": "1400"})

    def boom(client=None):
        raise fx.FxError("환율 자동 조회 실패 — network down")

    monkeypatch.setattr(fx, "fetch_usd_krw", boom)
    res = client.put("/api/settings/fx", headers=auth, json={"mode": "auto"}).json()
    assert res["fx_mode"] == "auto"
    assert "network down" in res["fx_error"]
    assert Decimal(res["fx_usd_krw"]) == Decimal(1400)  # 기존 값 유지
