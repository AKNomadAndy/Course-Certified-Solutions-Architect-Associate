from db import models
from services.planner import build_debt_payment_plan, load_personal_bill_and_debt_pack


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


def test_load_personal_bill_and_debt_pack_idempotent(session):
    first = load_personal_bill_and_debt_pack(session)
    second = load_personal_bill_and_debt_pack(session)

    assert first["bills_loaded"] == second["bills_loaded"]
    assert first["liabilities_loaded"] == second["liabilities_loaded"]

    bill_count = session.query(models.Bill).count()
    liability_count = session.query(models.Liability).count()
    assert bill_count == first["bills_loaded"]
    assert liability_count == first["liabilities_loaded"]
