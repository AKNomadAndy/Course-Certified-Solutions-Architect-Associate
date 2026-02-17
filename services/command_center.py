from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select

from db import models
from services.forecasting import generate_hybrid_forecast, summarize_forecast
from services.personal_intelligence import track_recommendation_feedback
from services.planner import generate_monthly_bill_tasks, list_bills


def _top_decisions(session) -> list[dict]:
    today = date.today()
    decisions: list[dict] = []

    open_tasks = session.scalar(select(func.count()).select_from(models.Task).where(models.Task.status == "open")) or 0
    if open_tasks > 0:
        decisions.append(
            {
                "title": "Clear open tasks",
                "detail": f"You have {open_tasks} open manual tasks pending.",
                "impact": "high",
                "why": "Open tasks are unresolved recommendations from prior runs.",
                "skip": "Skipping increases the chance of missed due dates and manual backlog.",
            }
        )

    due_soon_bills = [b for b in list_bills(session) if (b.next_due_date and 0 <= (b.next_due_date - today).days <= 7)]
    if due_soon_bills:
        total_due = round(sum(float(b.amount) for b in due_soon_bills), 2)
        decisions.append(
            {
                "title": "Prepare this week's bill coverage",
                "detail": f"{len(due_soon_bills)} bill(s) due within 7 days totaling ${total_due:.2f}.",
                "impact": "high",
                "why": "Known upcoming obligations should be covered first.",
                "skip": "Skipping can create late-payment risk and fee exposure.",
            }
        )

    latest_run = session.scalar(select(models.Run).order_by(models.Run.created_at.desc()))
    if latest_run and latest_run.status in {"action_failed", "guardrail_blocked", "condition_failed"}:
        decisions.append(
            {
                "title": "Review latest rule execution",
                "detail": f"Most recent run ended as '{latest_run.status}'. Check Activity for trace details.",
                "impact": "medium",
                "why": "A recent rule did not complete successfully and needs review.",
                "skip": "Skipping may repeat failures on future scheduled ticks.",
            }
        )

    forecast = generate_hybrid_forecast(session, starting_balance=0.0, horizon_days=7)
    summary = summarize_forecast(forecast)
    if summary.probability_negative_14d >= 0.25:
        decisions.append(
            {
                "title": "Reduce next-week cash risk",
                "detail": f"Overdraft probability is elevated ({summary.probability_negative_14d:.0%}).",
                "impact": "high",
                "why": "Forecast indicates elevated short-term cash stress.",
                "skip": "Skipping may increase overdraft likelihood in the next week.",
            }
        )

    if not decisions:
        decisions.append(
            {
                "title": "Stay on track",
                "detail": "No urgent financial operations detected today.",
                "impact": "low",
                "why": "Current signals look stable today.",
                "skip": "No urgent downside if you postpone action by a day.",
            }
        )

    return decisions[:3]


def _weekly_cash_risk(session) -> dict:
    forecast = generate_hybrid_forecast(session, starting_balance=0.0, horizon_days=7)
    summary = summarize_forecast(forecast)
    p_negative = float(summary.probability_negative_14d)

    if p_negative >= 0.6:
        level = "high"
    elif p_negative >= 0.3:
        level = "medium"
    else:
        level = "low"

    return {
        "level": level,
        "probability_negative_7d_proxy": p_negative,
        "expected_min_balance_7d_proxy": float(summary.expected_min_balance_14d),
        "safe_to_spend_7d_proxy": float(summary.safe_to_spend_14d_p90),
        "forecast": forecast,
    }


def _changes_since_yesterday(session) -> dict:
    today = date.today()
    yesterday = today - timedelta(days=1)

    net_today = session.scalar(
        select(func.sum(models.Transaction.amount)).where(models.Transaction.date == today)
    )
    net_yesterday = session.scalar(
        select(func.sum(models.Transaction.amount)).where(models.Transaction.date == yesterday)
    )

    runs_today = session.scalar(
        select(func.count()).select_from(models.Run).where(func.date(models.Run.created_at) == str(today))
    ) or 0
    runs_yesterday = session.scalar(
        select(func.count()).select_from(models.Run).where(func.date(models.Run.created_at) == str(yesterday))
    ) or 0

    new_tasks_today = session.scalar(
        select(func.count()).select_from(models.Task).where(func.date(models.Task.created_at) == str(today))
    ) or 0

    return {
        "net_today": float(net_today or 0.0),
        "net_yesterday": float(net_yesterday or 0.0),
        "net_delta": float((net_today or 0.0) - (net_yesterday or 0.0)),
        "runs_today": int(runs_today),
        "runs_yesterday": int(runs_yesterday),
        "runs_delta": int(runs_today - runs_yesterday),
        "new_tasks_today": int(new_tasks_today),
    }


def build_command_center(session) -> dict:
    open_tasks = session.scalar(select(func.count()).select_from(models.Task).where(models.Task.status == "open")) or 0
    recent_runs = session.scalar(select(func.count()).select_from(models.Run).where(models.Run.created_at >= date.today() - timedelta(days=1))) or 0
    tx_count = session.scalar(select(func.count()).select_from(models.Transaction)) or 0
    account_count = session.scalar(select(func.count()).select_from(models.Account)) or 0
    rule_count = session.scalar(select(func.count()).select_from(models.Rule)) or 0

    setup_steps = []
    if account_count == 0:
        setup_steps.append({"title": "Add first account", "hint": "Go to Money Map and create checking/savings."})
    if tx_count == 0:
        setup_steps.append({"title": "Import transactions", "hint": "Use Settings -> Import Transactions (multi-file supported)."})
    if rule_count == 0:
        setup_steps.append({"title": "Create first rule", "hint": "Open Rule Builder and save an active rule."})

    daily_brief = {
        "headline": "Stay steady today" if open_tasks == 0 else "Focus on your top tasks first",
        "open_tasks": int(open_tasks),
        "recent_runs_24h": int(recent_runs),
        "priority_note": "No urgent backlog detected." if open_tasks == 0 else f"You have {open_tasks} open task(s) to clear.",
    }

    return {
        "top_decisions": _top_decisions(session),
        "weekly_cash_risk": _weekly_cash_risk(session),
        "changes_since_yesterday": _changes_since_yesterday(session),
        "daily_brief": daily_brief,
        "setup_wizard": {
            "is_empty_state": bool(setup_steps),
            "steps": setup_steps,
        },
    }


def accept_weekly_plan(session) -> dict:
    created_bill_tasks = generate_monthly_bill_tasks(session)
    week_ref = f"weekly-plan:{date.today().isocalendar().year}-W{date.today().isocalendar().week:02d}"
    existing = session.scalar(select(models.Task).where(models.Task.reference_id == week_ref))
    created = 0
    if not existing:
        session.add(
            models.Task(
                title="Execute accepted weekly plan",
                task_type="weekly_plan",
                note="Weekly command-center plan accepted. Follow top decisions and review Activity mid-week.",
                reference_id=week_ref,
            )
        )
        created = 1
    session.commit()

    track_recommendation_feedback(
        session,
        recommendation_key=week_ref,
        source="command_center",
        title="Accept Weekly Plan",
        accepted=True,
        context={"created_plan_task": created, "created_bill_tasks": int(created_bill_tasks)},
    )
    return {
        "created_plan_task": created,
        "created_bill_tasks": int(created_bill_tasks),
        "reference_id": week_ref,
    }
