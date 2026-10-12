"""USD/KRW 환율 자동 조회.

1순위 한국수출입은행 매매기준율 (KOREAEXIM_API_KEY 설정 시), 2순위 Frankfurter(ECB 기준, 키 불필요).
조회에 실패하면 기존 환율을 그대로 두고 예외만 올린다.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import UserSettings

logger = logging.getLogger(__name__)

KOREAEXIM_URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
TIMEOUT = 10.0

SOURCE_LABELS = {
    "koreaexim": "한국수출입은행 매매기준율",
    "frankfurter": "ECB 기준환율(Frankfurter)",
    "manual": "직접 입력",
}


class FxError(Exception):
    pass


@dataclass
class FxQuote:
    rate: Decimal
    rate_date: date
    source: str


def _decimal(value: object) -> Decimal:
    try:
        rate = Decimal(str(value).replace(",", ""))
    except InvalidOperation as exc:
        raise FxError(f"환율 값을 해석할 수 없습니다: {value!r}") from exc
    if rate <= 0:
        raise FxError(f"잘못된 환율 값: {value!r}")
    return rate.quantize(Decimal("0.0001"))


def fetch_koreaexim(client: httpx.Client, api_key: str, today: date) -> FxQuote:
    # 영업일 11시 이전·주말·공휴일에는 빈 목록을 주므로 최대 7일 전까지 거슬러 조회한다
    for back in range(8):
        day = today - timedelta(days=back)
        res = client.get(KOREAEXIM_URL, params={"authkey": api_key, "searchdate": day.strftime("%Y%m%d"), "data": "AP01"})
        res.raise_for_status()
        rows = res.json() or []
        if rows and rows[0].get("result") not in (None, 1):
            raise FxError(f"한국수출입은행 API 오류 (result={rows[0].get('result')})")
        usd = next((r for r in rows if r.get("cur_unit") == "USD"), None)
        if usd is not None:
            return FxQuote(rate=_decimal(usd["deal_bas_r"]), rate_date=day, source="koreaexim")
    raise FxError("한국수출입은행: 최근 7일 USD 환율이 없습니다")


def fetch_frankfurter(client: httpx.Client) -> FxQuote:
    res = client.get(FRANKFURTER_URL, params={"base": "USD", "symbols": "KRW"})
    res.raise_for_status()
    body = res.json()
    try:
        return FxQuote(
            rate=_decimal(body["rates"]["KRW"]), rate_date=date.fromisoformat(body["date"]), source="frankfurter"
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FxError(f"Frankfurter 응답 형식 오류: {body!r}") from exc


def fetch_usd_krw(client: httpx.Client | None = None) -> FxQuote:
    api_key = get_settings().koreaexim_api_key
    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    errors: list[str] = []
    try:
        if api_key:
            try:
                return fetch_koreaexim(client, api_key, date.today())
            except (httpx.HTTPError, FxError, ValueError) as exc:
                errors.append(f"koreaexim: {exc}".replace(api_key, "****"))
        try:
            return fetch_frankfurter(client)
        except (httpx.HTTPError, FxError, ValueError) as exc:
            errors.append(f"frankfurter: {exc}")
    finally:
        if owns_client:
            client.close()
    raise FxError("환율 자동 조회 실패 — " + "; ".join(errors))


def apply_quote(settings: UserSettings, quote: FxQuote) -> None:
    settings.fx_usd_krw = quote.rate
    settings.fx_rate_date = quote.rate_date
    settings.fx_source = quote.source
    settings.fx_updated_at = datetime.now(UTC)


def refresh_auto_settings(db: Session) -> int:
    """자동 모드 사용자 설정의 환율을 갱신한다 (스케줄러용). 갱신한 건수를 돌려준다."""
    targets = db.scalars(select(UserSettings).where(UserSettings.fx_mode == "auto")).all()
    if not targets:
        return 0
    quote = fetch_usd_krw()
    for settings in targets:
        apply_quote(settings, quote)
    db.commit()
    return len(targets)
