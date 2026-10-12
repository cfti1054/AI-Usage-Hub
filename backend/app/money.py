"""통화 환산. 환율이 없으면 0으로 처리하지 않고 None(환산 불가)을 돌려준다."""

from decimal import Decimal


def monthly_equivalent(price: Decimal, billing_cycle: str) -> Decimal:
    return price / 12 if billing_cycle == "annual" else price


def convert(amount: Decimal, from_cur: str, to_cur: str, usd_krw: Decimal | None) -> Decimal | None:
    if from_cur == to_cur:
        return amount
    if usd_krw is None:
        return None
    if (from_cur, to_cur) == ("USD", "KRW"):
        return amount * usd_krw
    if (from_cur, to_cur) == ("KRW", "USD"):
        return amount / usd_krw
    return None
