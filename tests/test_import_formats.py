from db import models
from io import StringIO

import pandas as pd

from services.imports import (
    _normalize_dataframe,
    ingest_transactions,
    list_import_profiles,
    upsert_merchant_category_rule,
)


def test_normalize_canonical_columns():
    raw = StringIO("date,description,amount\n2026-01-01,Payroll,1000\n")
    df = pd.read_csv(raw)
    out = _normalize_dataframe(df)
    assert list(out.columns).count("date") == 1
    assert float(out.iloc[0]["amount"]) == 1000.0


def test_normalize_alt_statement_columns_and_card_account_mapping():
    raw = StringIO(
        "statement_period_start,statement_period_end,card_last4,section,trans_date,post_date,description,amount_usd,foreign_amount,foreign_currency,exchange_rate\n"
        "2026-01-01,2026-01-31,4242,Dining,2026-01-04,2026-01-05,Coffee,-4.50,-4.50,USD,1.0\n"
    )
    df = pd.read_csv(raw)
    out = _normalize_dataframe(df)
    assert out.iloc[0]["description"] == "Coffee"
    assert float(out.iloc[0]["amount"]) == -4.5
    assert str(out.iloc[0]["account"]) == "Card 4242"
    assert out.iloc[0]["category"] == "Dining"


def test_column_mapping_memory_created(session):
    raw = StringIO("date,description,amount\n2026-01-01,Payroll,1000\n")
    ingest_transactions(session, raw, filename="canonical.csv")
    profiles = list_import_profiles(session)
    assert len(profiles) >= 1


def test_categorization_feedback_loop(session):
    upsert_merchant_category_rule(session, "starbucks", "Coffee")
    raw = StringIO("date,description,amount,merchant\n2026-01-01,Latte,-6.5,Starbucks #123\n")
    result = ingest_transactions(session, raw, filename="merchant.csv")
    assert result["created"] == 1
    tx = session.query(models.Transaction).first()
    assert tx.category == "Coffee"


def test_import_quality_and_conflict_detection(session):
    first = StringIO("date,description,amount,account\n2026-01-01,Coffee,-4.5,Card A\n")
    second = StringIO("date,description,amount,account\n2026-01-01,Coffee,-4.5,Card B\n")
    ingest_transactions(session, first, filename="first.csv")
    out = ingest_transactions(session, second, filename="second.csv")
    assert out["report"]["quality_score"] >= 0
    assert out["report"]["conflict_duplicates"] >= 1
