from db import models
from services.planner import build_debt_payment_plan


def test_build_debt_plan_targets_highest_apr(session):
    session.add_all(
        [
            models.Liability(name="Low APR", statement_balance=1000, min_due=30, apr=5.0),
            models.Liability(name="High APR", statement_balance=800, min_due=25, apr=24.0),
        ]
    )
    session.commit()

    plan = build_debt_payment_plan(session, monthly_extra_payment=100)
    assert not plan.empty
    assert plan.iloc[0]["liability"] == "High APR"
    assert plan.iloc[0]["suggested_payment"] == 125.0
