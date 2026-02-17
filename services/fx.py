from __future__ import annotations

from datetime import date

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


def list_fx_snapshots(session):
    return session.scalars(
        select(models.FxRateSnapshot).order_by(
            models.FxRateSnapshot.snapshot_date.desc(),
            models.FxRateSnapshot.base_currency,
            models.FxRateSnapshot.quote_currency,
        )
    ).all()


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


def upsert_fx_snapshot(
    session,
    base_currency: str,
    quote_currency: str,
    rate: float,
    snapshot_date: date,
    source: str = "manual",
):
    base = (base_currency or "").strip().upper()
    quote = (quote_currency or "").strip().upper()
    if not base or not quote:
        raise ValueError("Both base and quote currency are required")
    if rate <= 0:
        raise ValueError("Rate must be positive")

    row = session.scalar(
        select(models.FxRateSnapshot).where(
            models.FxRateSnapshot.base_currency == base,
            models.FxRateSnapshot.quote_currency == quote,
            models.FxRateSnapshot.snapshot_date == snapshot_date,
        )
    )
    if row:
        row.rate = float(rate)
        row.source = source
    else:
        row = models.FxRateSnapshot(
            base_currency=base,
            quote_currency=quote,
            rate=float(rate),
            snapshot_date=snapshot_date,
            source=source,
        )
        session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _effective_rate(session, from_currency: str, to_currency: str, at_date: date | None = None):
    f = (from_currency or "USD").upper()
    t = (to_currency or "USD").upper()
    if f == t:
        return 1.0

    if at_date:
        direct_snap = session.scalar(
            select(models.FxRateSnapshot)
            .where(
                models.FxRateSnapshot.base_currency == f,
                models.FxRateSnapshot.quote_currency == t,
                models.FxRateSnapshot.snapshot_date <= at_date,
            )
            .order_by(models.FxRateSnapshot.snapshot_date.desc())
        )
        if direct_snap:
            return float(direct_snap.rate)

        inverse_snap = session.scalar(
            select(models.FxRateSnapshot)
            .where(
                models.FxRateSnapshot.base_currency == t,
                models.FxRateSnapshot.quote_currency == f,
                models.FxRateSnapshot.snapshot_date <= at_date,
            )
            .order_by(models.FxRateSnapshot.snapshot_date.desc())
        )
        if inverse_snap and float(inverse_snap.rate) != 0:
            return 1.0 / float(inverse_snap.rate)

    direct = session.scalar(select(models.FxRate).where(models.FxRate.base_currency == f, models.FxRate.quote_currency == t))
    if direct:
        return float(direct.rate)

    inverse = session.scalar(select(models.FxRate).where(models.FxRate.base_currency == t, models.FxRate.quote_currency == f))
    if inverse and float(inverse.rate) != 0:
        return 1.0 / float(inverse.rate)

    return 1.0


def convert_amount(
    session,
    amount: float,
    from_currency: str | None,
    to_currency: str | None,
    at_date: date | None = None,
    stress_pct: float = 0.0,
):
    f = (from_currency or "USD").upper()
    t = (to_currency or "USD").upper()
    amt = float(amount or 0.0)
    if f == t:
        return amt

    rate = _effective_rate(session, f, t, at_date=at_date)
    if stress_pct:
        rate = rate * (1.0 + float(stress_pct))
    return amt * rate


def available_currencies(session):
    codes = {"USD"}
    for row in list_fx_rates(session):
        codes.add(row.base_currency)
        codes.add(row.quote_currency)
    for row in session.scalars(select(models.Account.currency)).all():
        if row:
            codes.add(str(row).upper())
    for row in session.scalars(select(models.Pod.currency)).all():
        if row:
            codes.add(str(row).upper())
    return sorted(codes)


def currency_exposure(session, base_currency: str = "USD") -> list[dict]:
    base = (base_currency or "USD").upper()
    exposures: dict[str, float] = {}

    for acc in session.scalars(select(models.Account).where(models.Account.is_active == True)).all():  # noqa: E712
        latest = session.scalar(
            select(models.BalanceSnapshot)
            .where(models.BalanceSnapshot.source_type == "account", models.BalanceSnapshot.source_id == acc.id)
            .order_by(models.BalanceSnapshot.snapshot_at.desc())
        )
        bal = float(latest.balance if latest else 0.0)
        ccy = (acc.currency or base).upper()
        exposures[ccy] = exposures.get(ccy, 0.0) + bal

    for pod in session.scalars(select(models.Pod)).all():
        ccy = (pod.currency or base).upper()
        exposures[ccy] = exposures.get(ccy, 0.0) + float(pod.current_balance or 0.0)

    rows = []
    total_base = 0.0
    for ccy, original in sorted(exposures.items()):
        base_amount = convert_amount(session, original, ccy, base)
        total_base += base_amount
        rows.append(
            {
                "currency": ccy,
                "original_amount": round(original, 2),
                "base_currency": base,
                "base_amount": round(base_amount, 2),
            }
        )

    for row in rows:
        row["exposure_share"] = round((row["base_amount"] / total_base) if total_base else 0.0, 4)

    return rows
