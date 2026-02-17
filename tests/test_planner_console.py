from datetime import date, timedelta

from db import models
from services.planner import (
    add_bill,
    build_debt_payoff_schedule,
    build_personal_weekly_actions,
    build_today_console,
    save_income_profile,
    summarize_debt_payoff,
)


def _seed_cashflow(session):
    session.add(models.Account(name="Main Checking", type="checking", currency="USD"))
    session.add(models.Liability(name="Card", statement_balance=1000, min_due=50, apr=24.0))
    session.commit()

    save_income_profile(
        session,
        monthly_amount=4000,
        pay_frequency="monthly",
        next_pay_date=date.today() + timedelta(days=3),
        current_checking_balance=200,
        is_recurring=True,
    )
    add_bill(
        session,
        name="Rent",
        amount=1200,
        due_day=(date.today() + timedelta(days=2)).day,
        category="Housing",
        autopay=False,
        next_due_date=date.today() + timedelta(days=2),
        is_recurring=False,
    )


def test_today_console_only_counts_upcoming_7_days(session):
    _seed_cashflow(session)

    add_bill(
        session,
        name="Old Bill",
        amount=999,
        due_day=(date.today() - timedelta(days=2)).day,
        category="Other",
        autopay=False,
        next_due_date=date.today() - timedelta(days=2),
        is_recurring=False,
    )

    out = build_today_console(session)
    assert out["due_7d"] == 1200.0
    assert out["income_7d"] == 4000.0


def test_weekly_actions_contains_due_bill_and_income_review(session):
    _seed_cashflow(session)

    actions = build_personal_weekly_actions(session)
    labels = [a["action"] for a in actions]

    assert any(label.startswith("Pay Rent") for label in labels)
    assert "Review paycheck allocation" in labels


def test_debt_payoff_summary_has_interest_and_months(session):
    _seed_cashflow(session)
    schedule = build_debt_payoff_schedule(session, monthly_extra_payment=100, months=12)
    summary = summarize_debt_payoff(schedule)

    assert summary["months"] >= 1
    assert summary["total_interest"] > 0
