from datetime import date, timedelta

from db import models
from services.command_center import accept_weekly_plan
from services.personal_intelligence import (
    apply_adaptive_policy_tweaks,
    generate_adaptive_policy_tweaks,
    generate_monthly_retrospective,
    track_recommendation_feedback,
)


def _seed_activity(session):
    today = date.today()
    session.add_all(
        [
            models.Transaction(tx_hash="n1", date=today, description="Paycheck", amount=2500),
            models.Transaction(tx_hash="n2", date=today, description="Rent", amount=-1200),
            models.Transaction(tx_hash="n3", date=today - timedelta(days=1), description="Groceries", amount=-80),
            models.Transaction(tx_hash="n4", date=today - timedelta(days=15), description="Gas", amount=-60),
            models.Run(rule_id=1, event_key="rk1", status="completed", trace={}),
            models.Task(title="Pay bill", task_type="bill_payment", status="done"),
            models.IncomeProfile(
                name="Primary Income",
                monthly_amount=4000,
                pay_frequency="monthly",
                is_recurring=True,
                next_pay_date=today + timedelta(days=9),
                current_checking_balance=1800,
            ),
        ]
    )
    session.commit()


def test_track_recommendation_feedback_idempotent(session):
    first = track_recommendation_feedback(session, "rec:1", "scenario_lab", "Try plan", True)
    second = track_recommendation_feedback(session, "rec:1", "scenario_lab", "Try plan", True)

    assert first is not None
    assert second.id == first.id


def test_monthly_retrospective_contains_improved_worsened_lists(session):
    _seed_activity(session)
    accept_weekly_plan(session)

    out = generate_monthly_retrospective(session)

    assert out["month_key"]
    assert "improved" in out
    assert "worsened" in out
    assert isinstance(out["current"]["recommendation_acceptance_rate"], float)


def test_adaptive_tweaks_generate_and_apply(session):
    _seed_activity(session)
    tweaks = generate_adaptive_policy_tweaks(session)
    assert "suggested" in tweaks
    assert tweaks["suggested"]["guardrail_min_checking_floor"] >= 0

    updated = apply_adaptive_policy_tweaks(session, tweaks)
    assert updated.guardrail_min_checking_floor == tweaks["suggested"]["guardrail_min_checking_floor"]
