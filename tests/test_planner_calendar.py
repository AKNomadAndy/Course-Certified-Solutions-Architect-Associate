from datetime import date

from db import models
from services.planner import build_income_bill_calendar, save_income_profile, add_bill


def test_calendar_contains_income_and_bill_events(session):
    session.add(models.Account(name="Main Checking", type="checking", currency="USD"))
    session.commit()

    save_income_profile(session, 4000, "monthly", next_pay_date=date.today(), current_checking_balance=1000, is_recurring=True)
    add_bill(session, "Rent", 1200, due_day=date.today().day, category="Housing", autopay=True, next_due_date=date.today(), is_recurring=True)

    cal = build_income_bill_calendar(session, horizon_days=30)
    assert not cal.empty
    assert set(cal["event_type"].unique()) >= {"income", "bill"}
