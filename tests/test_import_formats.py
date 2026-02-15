from io import StringIO

from services.imports import _normalize_dataframe
import pandas as pd


def test_normalize_canonical_columns():
    raw = StringIO("date,description,amount\n2026-01-01,Payroll,1000\n")
    df = pd.read_csv(raw)
    out = _normalize_dataframe(df)
    assert list(out.columns).count("date") == 1
    assert float(out.iloc[0]["amount"]) == 1000.0


def test_normalize_alt_statement_columns():
    raw = StringIO(
        "statement_period_start,statement_period_end,card_last4,section,trans_date,post_date,description,amount_usd,foreign_amount,foreign_currency,exchange_rate\n"
        "2026-01-01,2026-01-31,4242,Dining,2026-01-04,2026-01-05,Coffee,-4.50,-4.50,USD,1.0\n"
    )
    df = pd.read_csv(raw)
    out = _normalize_dataframe(df)
    assert out.iloc[0]["description"] == "Coffee"
    assert float(out.iloc[0]["amount"]) == -4.5
    assert str(out.iloc[0]["account"]).startswith("Card")
    assert out.iloc[0]["category"] == "Dining"
