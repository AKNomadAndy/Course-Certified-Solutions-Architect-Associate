from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import select

from db import models
from services.forecasting import generate_hybrid_forecast, summarize_forecast
from services.fx import convert_amount
from services.personal_intelligence import track_recommendation_feedback
from services.planner import build_debt_payoff_schedule, get_or_create_income_profile, list_bills, summarize_debt_payoff


def _current_eurusd(session) -> float:
    rate = convert_amount(session, 1.0, "EUR", "USD")
    return float(rate or 1.0)


def _monthly_cash_projection(session, income_multiplier: float = 1.0, rent_increase: float = 0.0, rent_after_month: int = 2) -> pd.DataFrame:
    profile = get_or_create_income_profile(session)
    bills = list_bills(session)
    rows = []
    base_income = float(profile.monthly_amount or 0.0) * float(income_multiplier)

    for month_idx in range(1, 7):
        bills_total = 0.0
        for b in bills:
            amt = float(b.amount or 0.0)
            if month_idx >= rent_after_month and ("rent" in (b.name or "").lower() or (b.category or "").lower() == "housing"):
                amt += float(rent_increase)
            bills_total += amt
        rows.append(
            {
                "month_index": month_idx,
                "income": round(base_income, 2),
                "bills": round(bills_total, 2),
                "net": round(base_income - bills_total, 2),
            }
        )
    return pd.DataFrame(rows)


def run_scenarios(
    session,
    extra_debt_payment: float = 300.0,
    income_drop_pct: float = 15.0,
    rent_increase_amount: float = 200.0,
    rent_increase_after_month: int = 2,
    eurusd_target: float = 1.0,
):
    profile = get_or_create_income_profile(session)
    starting_balance = float(profile.current_checking_balance or 0.0)
    base_currency = "USD"

    baseline_forecast = generate_hybrid_forecast(
        session,
        starting_balance=starting_balance,
        horizon_days=30,
        base_currency=base_currency,
        fx_stress_pct=0.0,
    )
    baseline_summary = summarize_forecast(baseline_forecast)

    baseline_debt = build_debt_payoff_schedule(session, monthly_extra_payment=0.0, months=24)
    baseline_debt_summary = summarize_debt_payoff(baseline_debt)

    # Scenario 1: extra debt payment
    debt_scn = build_debt_payoff_schedule(session, monthly_extra_payment=float(extra_debt_payment), months=24)
    debt_scn_summary = summarize_debt_payoff(debt_scn)

    # Scenario 2: income drop
    income_multiplier = max(0.0, 1.0 - float(income_drop_pct) / 100.0)
    income_projection = _monthly_cash_projection(session, income_multiplier=income_multiplier)

    # Scenario 3: rent increase in future months
    rent_projection = _monthly_cash_projection(
        session,
        income_multiplier=1.0,
        rent_increase=float(rent_increase_amount),
        rent_after_month=max(1, int(rent_increase_after_month)),
    )

    # Scenario 4: EURUSD target move
    current_eurusd = _current_eurusd(session)
    stress_pct = (float(eurusd_target) / current_eurusd - 1.0) if current_eurusd else 0.0
    fx_forecast = generate_hybrid_forecast(
        session,
        starting_balance=starting_balance,
        horizon_days=30,
        base_currency=base_currency,
        fx_stress_pct=stress_pct,
    )
    fx_summary = summarize_forecast(fx_forecast)

    return {
        "generated_on": date.today().isoformat(),
        "baseline": {
            "forecast": baseline_summary.__dict__,
            "debt": baseline_debt_summary,
        },
        "extra_debt_payment": {
            "input": extra_debt_payment,
            "summary": debt_scn_summary,
            "interest_delta": round(
                float(debt_scn_summary.get("total_interest", 0.0)) - float(baseline_debt_summary.get("total_interest", 0.0)),
                2,
            ),
            "ending_balance_delta": round(
                float(debt_scn_summary.get("ending_total_balance", 0.0))
                - float(baseline_debt_summary.get("ending_total_balance", 0.0)),
                2,
            ),
            "table": debt_scn,
        },
        "income_drop": {
            "input_pct": income_drop_pct,
            "projection": income_projection,
            "net_6m": round(float(income_projection["net"].sum()) if not income_projection.empty else 0.0, 2),
        },
        "rent_increase": {
            "input_amount": rent_increase_amount,
            "input_after_month": rent_increase_after_month,
            "projection": rent_projection,
            "net_6m": round(float(rent_projection["net"].sum()) if not rent_projection.empty else 0.0, 2),
        },
        "fx_move": {
            "current_eurusd": round(current_eurusd, 6),
            "target_eurusd": float(eurusd_target),
            "implied_stress_pct": round(stress_pct * 100.0, 2),
            "forecast": fx_summary.__dict__,
            "table": fx_forecast,
        },
    }


def save_scenario_task(session, title: str, note: str):
    ref = f"scenario:{date.today().isoformat()}:{title.lower().replace(' ', '-')[:50]}"
    exists = session.scalar(select(models.Task).where(models.Task.reference_id == ref))
    if exists:
        return exists
    task = models.Task(title=title, task_type="scenario_plan", note=note, reference_id=ref)
    session.add(task)
    session.commit()
    session.refresh(task)
    track_recommendation_feedback(
        session,
        recommendation_key=ref,
        source="scenario_lab",
        title=title,
        accepted=True,
        context={"note": note},
    )
    return task
