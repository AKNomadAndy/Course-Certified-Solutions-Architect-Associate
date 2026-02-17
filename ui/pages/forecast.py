from __future__ import annotations

import streamlit as st

from services.forecasting import generate_hybrid_forecast, summarize_forecast
from services.fx import available_currencies
from services.user_settings import get_or_create_user_settings


def render(session):
    st.header("Cashflow Forecast")
    st.caption("Hybrid deterministic + stochastic forecast with multi-currency conversion controls.")

    settings = get_or_create_user_settings(session)
    currencies = available_currencies(session)
    default_idx = currencies.index(settings.base_currency) if settings.base_currency in currencies else 0

    c1, c2, c3 = st.columns(3)
    starting_balance = c1.number_input("Starting balance", value=0.0, step=50.0)
    horizon_days = c2.number_input("Horizon days", min_value=14, max_value=90, value=30)
    forecast_currency = c3.selectbox("Forecast currency", currencies, index=default_idx)

    if st.button("Run Forecast", type="primary"):
        forecast_df = generate_hybrid_forecast(
            session,
            starting_balance=starting_balance,
            horizon_days=int(horizon_days),
            base_currency=forecast_currency,
        )
        summary = summarize_forecast(forecast_df)

        m1, m2, m3 = st.columns(3)
        m1.metric("P(Negative) 14d", f"{summary.probability_negative_14d:.0%}")
        m2.metric("Expected Min Bal 14d", f"{forecast_currency} {summary.expected_min_balance_14d:,.2f}")
        m3.metric("Safe-to-Spend (14d, P90)", f"{forecast_currency} {summary.safe_to_spend_14d_p90:,.2f}")

        st.subheader("Balance Confidence Bands")
        chart_df = forecast_df[["date", "balance_p10", "balance_p50", "balance_p90"]].copy()
        chart_df = chart_df.set_index("date")
        st.line_chart(chart_df)

        st.subheader("Daily Overdraft Risk")
        risk_df = forecast_df[["date", "p_negative"]].set_index("date")
        st.area_chart(risk_df)

        st.subheader("Forecast Detail")
        st.dataframe(forecast_df, use_container_width=True)
