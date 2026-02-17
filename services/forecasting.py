from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import calendar

import pandas as pd
from sqlalchemy import select

from db import models
from services.fx import convert_amount
from services.user_settings import get_or_create_user_settings


@dataclass
class ForecastSummary:
    probability_negative_14d: float
    probability_negative_30d: float
    expected_min_balance_14d: float
    expected_min_balance_30d: float
    safe_to_spend_14d_p90: float


def _monthly_income_to_daily(monthly_amount: float, pay_frequency: str) -> float:
    if pay_frequency == "weekly":
        return (monthly_amount * 12 / 52) / 7
    if pay_frequency == "biweekly":
        return (monthly_amount * 12 / 26) / 7
    return monthly_amount / 30.4375


def _load_income_and_bills(session):
    profile = session.scalar(select(models.IncomeProfile).where(models.IncomeProfile.name == "Primary Income"))
    bills = session.scalars(select(models.Bill).where(models.Bill.is_active == True)).all()  # noqa: E712
    monthly_income = float(profile.monthly_amount) if profile else 0.0
    pay_frequency = profile.pay_frequency if profile else "monthly"
    return monthly_income, pay_frequency, bills


def _build_deterministic_schedule(start: date, horizon_days: int, monthly_income: float, pay_frequency: str, bills):
    rows = []
    daily_income = _monthly_income_to_daily(monthly_income, pay_frequency)

    for i in range(horizon_days):
        d = start + timedelta(days=i)
        rows.append({"date": d, "deterministic_income": daily_income, "deterministic_bills": 0.0})

    df = pd.DataFrame(rows)

    for bill in bills:
        for d in df["date"]:
            if d.day == min(max(1, bill.due_day), calendar.monthrange(d.year, d.month)[1]):
                df.loc[df["date"] == d, "deterministic_bills"] += float(bill.amount)

    df["deterministic_net"] = df["deterministic_income"] - df["deterministic_bills"]
    return df


def _stochastic_remainder_estimate(session, base_currency: str, stress_pct: float = 0.0):
    txs = session.scalars(select(models.Transaction).order_by(models.Transaction.date)).all()
    if not txs:
        return {"weekday_mean": {i: 0.0 for i in range(7)}, "q10": 0.0, "q50": 0.0, "q90": 0.0}

    rows = []
    for t in txs:
        rows.append(
            {
                "date": t.date,
                "amount": convert_amount(
                    session,
                    t.amount,
                    from_currency=t.currency or base_currency,
                    to_currency=base_currency,
                    at_date=t.date,
                    stress_pct=stress_pct,
                ),
            }
        )

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    daily = df.groupby("date", as_index=False)["amount"].sum()
    daily["weekday"] = daily["date"].dt.weekday

    weekday_mean = daily.groupby("weekday")["amount"].mean().to_dict()
    for i in range(7):
        weekday_mean.setdefault(i, 0.0)

    q10 = float(daily["amount"].quantile(0.10))
    q50 = float(daily["amount"].quantile(0.50))
    q90 = float(daily["amount"].quantile(0.90))

    return {"weekday_mean": weekday_mean, "q10": q10, "q50": q50, "q90": q90}


def generate_hybrid_forecast(
    session,
    starting_balance: float = 0.0,
    horizon_days: int = 30,
    base_currency: str | None = None,
    fx_stress_pct: float = 0.0,
):
    start = date.today()
    settings = get_or_create_user_settings(session)
    fx_base = (base_currency or settings.base_currency or "USD").upper()

    monthly_income, pay_frequency, bills = _load_income_and_bills(session)
    det = _build_deterministic_schedule(start, horizon_days, monthly_income, pay_frequency, bills)
    stochastic = _stochastic_remainder_estimate(session, base_currency=fx_base, stress_pct=fx_stress_pct)

    det["weekday"] = pd.to_datetime(det["date"]).dt.weekday
    det["stochastic_mean"] = det["weekday"].map(stochastic["weekday_mean"]).fillna(0.0)
    det["net_p10"] = det["deterministic_net"] + stochastic["q10"]
    det["net_p50"] = det["deterministic_net"] + stochastic["q50"]
    det["net_p90"] = det["deterministic_net"] + stochastic["q90"]

    det["balance_p10"] = starting_balance + det["net_p10"].cumsum()
    det["balance_p50"] = starting_balance + det["net_p50"].cumsum()
    det["balance_p90"] = starting_balance + det["net_p90"].cumsum()

    det["p_negative"] = ((det["balance_p10"] < 0).astype(float) * 0.9 + (det["balance_p50"] < 0).astype(float) * 0.5) / 1.4
    det["currency"] = fx_base
    det["fx_stress_pct"] = fx_stress_pct

    return det[[
        "date",
        "deterministic_net",
        "net_p10",
        "net_p50",
        "net_p90",
        "balance_p10",
        "balance_p50",
        "balance_p90",
        "p_negative",
        "currency",
        "fx_stress_pct",
    ]]


def generate_fx_stress_table(session, starting_balance: float, horizon_days: int, base_currency: str, shocks: list[float]):
    rows = []
    for shock in shocks:
        fc = generate_hybrid_forecast(
            session,
            starting_balance=starting_balance,
            horizon_days=horizon_days,
            base_currency=base_currency,
            fx_stress_pct=shock,
        )
        s = summarize_forecast(fc)
        rows.append(
            {
                "fx_shock_pct": round(shock * 100, 2),
                "p_negative_14d": s.probability_negative_14d,
                "min_balance_14d": s.expected_min_balance_14d,
                "safe_to_spend_14d": s.safe_to_spend_14d_p90,
            }
        )
    return pd.DataFrame(rows)


def summarize_forecast(forecast_df: pd.DataFrame) -> ForecastSummary:
    f14 = forecast_df.head(14)
    f30 = forecast_df.head(30)

    probability_negative_14d = float(f14["p_negative"].max()) if not f14.empty else 0.0
    probability_negative_30d = float(f30["p_negative"].max()) if not f30.empty else 0.0
    expected_min_balance_14d = float(f14["balance_p50"].min()) if not f14.empty else 0.0
    expected_min_balance_30d = float(f30["balance_p50"].min()) if not f30.empty else 0.0
    safe_to_spend_14d_p90 = float(max(0.0, f14["balance_p10"].min())) if not f14.empty else 0.0

    return ForecastSummary(
        probability_negative_14d=round(probability_negative_14d, 4),
        probability_negative_30d=round(probability_negative_30d, 4),
        expected_min_balance_14d=round(expected_min_balance_14d, 2),
        expected_min_balance_30d=round(expected_min_balance_30d, 2),
        safe_to_spend_14d_p90=round(safe_to_spend_14d_p90, 2),
    )
