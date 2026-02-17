from datetime import date

from db import models
from services.scenario_lab import run_scenarios


def _seed(session):
    session.add(models.Account(name="Main Checking", type="checking", currency="USD", is_active=True))
    session.add(models.BalanceSnapshot(source_type="account", source_id=1, balance=2500))
    session.add(
        models.IncomeProfile(
            name="Primary Income",
            monthly_amount=4000,
            pay_frequency="monthly",
            current_checking_balance=2500,
            is_recurring=True,
        )
    )
    session.add(models.Bill(name="Rent", amount=1500, due_day=1, category="Housing", autopay=True, is_active=True, is_recurring=True))
    session.add(models.Liability(name="Card", statement_balance=2000, min_due=80, apr=22.0))
    session.add(models.Transaction(tx_hash="s1", date=date(2025, 1, 1), description="Expense EUR", amount=-20, currency="EUR"))
    session.add(models.FxRate(base_currency="EUR", quote_currency="USD", rate=1.1, source="manual"))
    session.commit()


def test_run_scenarios_outputs_all_sections(session):
    _seed(session)
    out = run_scenarios(session, extra_debt_payment=300, income_drop_pct=15, rent_increase_amount=200, rent_increase_after_month=2, eurusd_target=1.2)

    assert "baseline" in out
    assert "extra_debt_payment" in out
    assert "income_drop" in out
    assert "rent_increase" in out
    assert "fx_move" in out
    assert out["fx_move"]["implied_stress_pct"] != 0
