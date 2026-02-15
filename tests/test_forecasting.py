import pandas as pd

from services.forecasting import summarize_forecast


def test_summarize_forecast_outputs_non_negative_safe_spend():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=3),
            "p_negative": [0.0, 0.2, 0.4],
            "balance_p10": [100.0, 80.0, -10.0],
            "balance_p50": [140.0, 120.0, 90.0],
        }
    )
    summary = summarize_forecast(df)
    assert summary.probability_negative_14d == 0.4
    assert summary.expected_min_balance_14d == 90.0
    assert summary.safe_to_spend_14d_p90 == 0.0
