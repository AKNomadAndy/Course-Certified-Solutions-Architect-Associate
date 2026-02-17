from __future__ import annotations

from sqlalchemy import select

from db import models


DEFAULT_RATES = {
    ("USD", "EUR"): 0.92,
    ("EUR", "USD"): 1.09,
    ("USD", "GBP"): 0.79,
    ("GBP", "USD"): 1.27,
    ("USD", "JPY"): 150.0,
    ("JPY", "USD"): 0.0067,
}


def ensure_default_fx_rates(session):
    created = 0
    for (base, quote), rate in DEFAULT_RATES.items():
        existing = session.scalar(
            select(models.FxRate).where(models.FxRate.base_currency == base, models.FxRate.quote_currency == quote)
        )
        if existing:
            continue
        session.add(models.FxRate(base_currency=base, quote_currency=quote, rate=float(rate), source="default"))
        created += 1
    if created:
        session.commit()
    return created


def list_fx_rates(session):
    return session.scalars(select(models.FxRate).order_by(models.FxRate.base_currency, models.FxRate.quote_currency)).all()


def upsert_fx_rate(session, base_currency: str, quote_currency: str, rate: float, source: str = "manual"):
    base = (base_currency or "").strip().upper()
    quote = (quote_currency or "").strip().upper()
    if not base or not quote:
        raise ValueError("Both base and quote currency are required")
    if rate <= 0:
        raise ValueError("Rate must be positive")

    row = session.scalar(
        select(models.FxRate).where(models.FxRate.base_currency == base, models.FxRate.quote_currency == quote)
    )
    if row:
        row.rate = float(rate)
        row.source = source
    else:
        row = models.FxRate(base_currency=base, quote_currency=quote, rate=float(rate), source=source)
        session.add(row)
    session.commit()
    session.refresh(row)
    return row


def convert_amount(session, amount: float, from_currency: str | None, to_currency: str | None):
    f = (from_currency or "USD").upper()
    t = (to_currency or "USD").upper()
    amt = float(amount or 0.0)
    if f == t:
        return amt

    direct = session.scalar(select(models.FxRate).where(models.FxRate.base_currency == f, models.FxRate.quote_currency == t))
    if direct:
        return amt * float(direct.rate)

    inverse = session.scalar(select(models.FxRate).where(models.FxRate.base_currency == t, models.FxRate.quote_currency == f))
    if inverse and float(inverse.rate) != 0:
        return amt / float(inverse.rate)

    return amt


def available_currencies(session):
    codes = {"USD"}
    for row in list_fx_rates(session):
        codes.add(row.base_currency)
        codes.add(row.quote_currency)
    return sorted(codes)
