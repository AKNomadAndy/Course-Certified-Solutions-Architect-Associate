from datetime import date

from services.planner import build_cash_runway_projection, save_income_profile, add_bill


def test_cash_runway_projection_includes_checkpoints_and_bills(session):
    save_income_profile(
        session,
        monthly_amount=4000.0,
        pay_frequency="biweekly",
        next_pay_date=date.today(),
        current_checking_balance=1000.0,
        is_recurring=True,
    )
    add_bill(session, "Rent", 1200.0, due_day=date.today().day, category="Housing", autopay=False, next_due_date=date.today())

    out = build_cash_runway_projection(session, horizon_days=56)

    assert "checkpoints" in out
    assert "4_weeks" in out["checkpoints"]
    assert "8_weeks" in out["checkpoints"]
    assert out["upcoming_bills"].shape[0] >= 1
    assert out["daily"].shape[0] >= 1
