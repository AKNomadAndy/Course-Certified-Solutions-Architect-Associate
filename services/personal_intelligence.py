from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from db import models
from services.user_settings import get_or_create_user_settings


def track_recommendation_feedback(
    session,
    recommendation_key: str,
    source: str,
    title: str,
    accepted: bool = True,
    context: dict | None = None,
):
    key = (recommendation_key or "").strip()
    if not key:
        return None

    existing = session.scalar(select(models.RecommendationFeedback).where(models.RecommendationFeedback.recommendation_key == key))
    if existing:
        return existing

    row = models.RecommendationFeedback(
        recommendation_key=key,
        source=(source or "command_center").strip(),
        title=(title or "Recommendation").strip() or "Recommendation",
        accepted=bool(accepted),
        context=context or {},
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _month_range(target: date) -> tuple[date, date]:
    start = date(target.year, target.month, 1)
    if target.month == 12:
        nxt = date(target.year + 1, 1, 1)
    else:
        nxt = date(target.year, target.month + 1, 1)
    return start, nxt


def _month_metrics(session, month_ref: date) -> dict:
    start, end = _month_range(month_ref)
    net = session.scalar(
        select(func.coalesce(func.sum(models.Transaction.amount), 0.0)).where(
            models.Transaction.date >= start,
            models.Transaction.date < end,
        )
    ) or 0.0

    run_total = session.scalar(
        select(func.count()).select_from(models.Run).where(models.Run.created_at >= start, models.Run.created_at < end)
    ) or 0
    run_ok = session.scalar(
        select(func.count()).select_from(models.Run).where(
            models.Run.created_at >= start,
            models.Run.created_at < end,
            models.Run.status == "completed",
        )
    ) or 0

    tasks_done = session.scalar(
        select(func.count()).select_from(models.Task).where(
            models.Task.created_at >= start,
            models.Task.created_at < end,
            models.Task.status == "done",
        )
    ) or 0

    accepted = session.scalar(
        select(func.count()).select_from(models.RecommendationFeedback).where(
            models.RecommendationFeedback.created_at >= start,
            models.RecommendationFeedback.created_at < end,
            models.RecommendationFeedback.accepted.is_(True),
        )
    ) or 0
    total_feedback = session.scalar(
        select(func.count()).select_from(models.RecommendationFeedback).where(
            models.RecommendationFeedback.created_at >= start,
            models.RecommendationFeedback.created_at < end,
        )
    ) or 0

    run_success_rate = float(run_ok) / float(run_total) if run_total else 0.0
    acceptance_rate = float(accepted) / float(total_feedback) if total_feedback else 0.0

    return {
        "month_key": start.strftime("%Y-%m"),
        "net_cashflow": round(float(net), 2),
        "run_success_rate": round(run_success_rate, 4),
        "tasks_done": int(tasks_done),
        "recommendation_acceptance_rate": round(acceptance_rate, 4),
        "feedback_count": int(total_feedback),
    }


def _improvement_label(metric: str, cur: float, prev: float) -> str:
    delta = cur - prev
    if abs(delta) < 1e-6:
        return "stable"
    if metric in {"net_cashflow", "run_success_rate", "tasks_done", "recommendation_acceptance_rate"}:
        return "improved" if delta > 0 else "worsened"
    return "improved" if delta > 0 else "worsened"


def generate_monthly_retrospective(session, for_month: date | None = None) -> dict:
    ref = for_month or date.today()
    cur = _month_metrics(session, ref)
    prev_ref = (date(ref.year - 1, 12, 1) if ref.month == 1 else date(ref.year, ref.month - 1, 1))
    prev = _month_metrics(session, prev_ref)

    improved, worsened = [], []
    for metric in ("net_cashflow", "run_success_rate", "tasks_done", "recommendation_acceptance_rate"):
        label = _improvement_label(metric, float(cur[metric]), float(prev[metric]))
        item = {
            "metric": metric,
            "current": cur[metric],
            "previous": prev[metric],
            "delta": round(float(cur[metric]) - float(prev[metric]), 4),
        }
        if label == "improved":
            improved.append(item)
        elif label == "worsened":
            worsened.append(item)

    summary = {
        "month_key": cur["month_key"],
        "current": cur,
        "previous": prev,
        "improved": improved,
        "worsened": worsened,
        "generated_at": datetime.utcnow().isoformat(),
    }

    row = session.scalar(select(models.MonthlyRetrospective).where(models.MonthlyRetrospective.month_key == cur["month_key"]))
    if row:
        row.summary = summary
        row.generated_at = datetime.utcnow()
    else:
        row = models.MonthlyRetrospective(month_key=cur["month_key"], summary=summary)
        session.add(row)
    session.commit()

    return summary


def generate_adaptive_policy_tweaks(session) -> dict:
    settings = get_or_create_user_settings(session)
    today = date.today()
    lookback_start = today - timedelta(days=60)

    txs = session.scalars(select(models.Transaction).where(models.Transaction.date >= lookback_start)).all()
    outflows = [abs(float(t.amount)) for t in txs if float(t.amount) < 0]
    volatility = 0.0
    if outflows:
        mean = sum(outflows) / len(outflows)
        variance = sum((x - mean) ** 2 for x in outflows) / max(1, len(outflows))
        volatility = (variance ** 0.5) / mean if mean > 0 else 0.0

    profile = session.scalar(select(models.IncomeProfile).order_by(models.IncomeProfile.id))
    paycheck_timing_score = 0.0
    if profile and profile.next_pay_date:
        days_to_pay = (profile.next_pay_date - today).days
        paycheck_timing_score = max(0.0, min(1.0, days_to_pay / 30.0))

    risk_adjust = {"conservative": 1.2, "balanced": 1.0, "aggressive": 0.85}.get(settings.risk_tolerance, 1.0)
    suggested_floor = round(max(settings.guardrail_min_checking_floor, (200 + 600 * volatility) * risk_adjust), 2)
    suggested_risk_pause = max(0.2, min(0.9, round(0.65 - (volatility * 0.2) + (0.1 * paycheck_timing_score), 2)))

    if settings.risk_tolerance == "conservative":
        suggested_daily_cap = 150.0
    elif settings.risk_tolerance == "aggressive":
        suggested_daily_cap = 450.0
    else:
        suggested_daily_cap = 300.0
    suggested_daily_cap = round(suggested_daily_cap * (1 + min(volatility, 0.5)), 2)

    tweaks = {
        "inputs": {
            "risk_tolerance": settings.risk_tolerance,
            "spend_volatility": round(volatility, 4),
            "paycheck_timing_score": round(paycheck_timing_score, 4),
        },
        "current": {
            "guardrail_min_checking_floor": float(settings.guardrail_min_checking_floor or 0.0),
            "guardrail_risk_pause_threshold": float(settings.guardrail_risk_pause_threshold or 0.6),
            "guardrail_max_category_daily": float(settings.guardrail_max_category_daily or 0.0),
        },
        "suggested": {
            "guardrail_min_checking_floor": suggested_floor,
            "guardrail_risk_pause_threshold": suggested_risk_pause,
            "guardrail_max_category_daily": suggested_daily_cap,
        },
    }
    return tweaks


def apply_adaptive_policy_tweaks(session, tweaks: dict) -> models.UserSettings:
    settings = get_or_create_user_settings(session)
    suggested = tweaks.get("suggested", {}) if tweaks else {}
    settings.guardrail_min_checking_floor = float(suggested.get("guardrail_min_checking_floor", settings.guardrail_min_checking_floor))
    settings.guardrail_risk_pause_threshold = float(
        suggested.get("guardrail_risk_pause_threshold", settings.guardrail_risk_pause_threshold)
    )
    settings.guardrail_max_category_daily = float(suggested.get("guardrail_max_category_daily", settings.guardrail_max_category_daily or 0.0))
    session.commit()
    session.refresh(settings)
    return settings
