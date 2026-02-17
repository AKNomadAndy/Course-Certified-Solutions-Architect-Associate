from datetime import date, datetime, timedelta

from db import models
from services.command_center import accept_weekly_plan, build_command_center


def _seed_minimum(session):
    session.add(models.Account(name="Main Checking", type="checking", currency="USD"))
    session.add(models.BalanceSnapshot(source_type="account", source_id=1, balance=2000))
    session.add(
        models.IncomeProfile(
            name="Primary Income",
            monthly_amount=3000,
            pay_frequency="monthly",
            is_recurring=True,
            current_checking_balance=2000,
            next_pay_date=date.today() + timedelta(days=5),
        )
    )
    session.add(
        models.Bill(
            name="Rent",
            amount=1200,
            due_day=date.today().day,
            category="Housing",
            autopay=False,
            is_active=True,
            is_recurring=True,
            next_due_date=date.today() + timedelta(days=2),
        )
    )
    session.add(models.Transaction(tx_hash="t1", date=date.today(), description="Coffee", amount=-8, category="Food"))
    session.add(models.Transaction(tx_hash="t2", date=date.today() - timedelta(days=1), description="Groceries", amount=-25, category="Food"))
    session.add(
        models.Run(
            rule_id=1,
            event_key="e1",
            status="action_failed",
            created_at=datetime.utcnow(),
            trace={},
        )
    )
    session.commit()


def test_build_command_center_has_required_sections(session):
    _seed_minimum(session)
    model = build_command_center(session)

    assert "top_decisions" in model
    assert "weekly_cash_risk" in model
    assert "changes_since_yesterday" in model
    assert len(model["top_decisions"]) >= 1


def test_accept_weekly_plan_is_idempotent(session):
    _seed_minimum(session)
    first = accept_weekly_plan(session)
    second = accept_weekly_plan(session)

    assert first["created_plan_task"] in (0, 1)
    assert second["created_plan_task"] == 0
