from datetime import date

from db import models
from services.forecasting import generate_fx_stress_table, generate_hybrid_forecast
from services.fx import convert_amount, currency_exposure, ensure_default_fx_rates, upsert_fx_rate, upsert_fx_snapshot
from services.user_settings import save_user_settings


def test_convert_amount_direct_and_inverse(session):
    upsert_fx_rate(session, "USD", "EUR", 0.9)
    assert round(convert_amount(session, 100, "USD", "EUR"), 2) == 90.0
    assert round(convert_amount(session, 90, "EUR", "USD"), 2) == 100.0


def test_date_aware_snapshot_conversion(session):
    upsert_fx_rate(session, "EUR", "USD", 2.0)
    upsert_fx_snapshot(session, "EUR", "USD", 3.0, date(2025, 1, 1))
    out = convert_amount(session, 10, "EUR", "USD", at_date=date(2025, 1, 10))
    assert round(out, 2) == 30.0


def test_forecast_uses_base_currency_conversion(session):
    save_user_settings(session, user_name="Alex", base_currency="USD")
    upsert_fx_rate(session, "EUR", "USD", 2.0)
    session.add(models.Transaction(tx_hash="f1", date=date(2025, 1, 1), description="Expense", amount=-10, currency="EUR"))
    session.commit()

    out = generate_hybrid_forecast(session, starting_balance=0, horizon_days=14, base_currency="USD")
    assert not out.empty
    assert out.iloc[0]["currency"] == "USD"


def test_stress_table_and_exposure(session):
    session.add(models.Account(name="Main Checking", type="checking", currency="USD", is_active=True))
    session.add(models.Pod(name="Travel", currency="EUR", current_balance=100))
    session.add(models.BalanceSnapshot(source_type="account", source_id=1, balance=1000))
    session.commit()

    upsert_fx_rate(session, "EUR", "USD", 1.1)
    exposure = currency_exposure(session, base_currency="USD")
    assert len(exposure) >= 2

    stress = generate_fx_stress_table(session, starting_balance=0, horizon_days=14, base_currency="USD", shocks=[-0.1, 0.0, 0.1])
    assert len(stress) == 3


def test_seed_default_fx_rates(session):
    created = ensure_default_fx_rates(session)
    assert created >= 1
