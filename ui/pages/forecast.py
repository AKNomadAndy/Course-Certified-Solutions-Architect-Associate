from __future__ import annotations

import streamlit as st

from services.explainability import confidence_badge_for_forecast
from services.forecasting import generate_fx_stress_table, generate_hybrid_forecast, summarize_forecast
from services.fx import available_currencies
from services.user_settings import get_or_create_user_settings


def render(session):
    st.header("Cashflow Forecast")
    st.caption("Hybrid deterministic + stochastic forecast with multi-currency conversion controls and FX stress scenarios.")

    settings = get_or_create_user_settings(session)
    currencies = available_currencies(session)
    default_idx = currencies.index(settings.base_currency) if settings.base_currency in currencies else 0

    c1, c2, c3, c4 = st.columns(4)
    starting_balance = c1.number_input("Starting balance", value=0.0, step=50.0)
    horizon_days = c2.number_input("Horizon days", min_value=14, max_value=90, value=30)
    forecast_currency = c3.selectbox("Forecast currency", currencies, index=default_idx)
    fx_stress_pct = c4.slider("FX stress (%)", min_value=-30, max_value=30, value=0, step=5)

    if st.button("Run Forecast", type="primary"):
        forecast_df = generate_hybrid_forecast(
            session,
            starting_balance=starting_balance,
            horizon_days=int(horizon_days),
            base_currency=forecast_currency,
            fx_stress_pct=float(fx_stress_pct) / 100.0,
        )
        summary = summarize_forecast(forecast_df)

        m1, m2, m3 = st.columns(3)
        m1.metric("P(Negative) 14d", f"{summary.probability_negative_14d:.0%}")
        m2.metric("Expected Min Bal 14d", f"{forecast_currency} {summary.expected_min_balance_14d:,.2f}")
        m3.metric("Safe-to-Spend (14d, P90)", f"{forecast_currency} {summary.safe_to_spend_14d_p90:,.2f}")

        band_width = float((forecast_df["balance_p90"] - forecast_df["balance_p10"]).abs().mean()) if not forecast_df.empty else 0.0
        confidence = confidence_badge_for_forecast(summary.probability_negative_14d, band_width)
        badge = "🟢 High" if confidence == "high" else ("🟡 Medium" if confidence == "medium" else "🔴 Low")
        st.caption(f"Forecast confidence badge: {badge} (avg band width: {band_width:,.2f})")

        with st.expander("Why this recommendation?", expanded=False):
            st.write(
                "Forecast combines deterministic income/bills with stochastic transaction behavior; "
                "safe-to-spend and risk metrics are derived from P10/P50/P90 balance paths."
            )
        with st.expander("What if I skip this?", expanded=False):
            st.write(
                "If you skip acting on forecast warnings, cash volatility may create avoidable short-term stress. "
                "No funds are moved automatically in personal mode."
            )

        st.subheader("Balance Confidence Bands")
        chart_df = forecast_df[["date", "balance_p10", "balance_p50", "balance_p90"]].copy()
        chart_df = chart_df.set_index("date")
        st.line_chart(chart_df)

        st.subheader("Daily Overdraft Risk")
        risk_df = forecast_df[["date", "p_negative"]].set_index("date")
        st.area_chart(risk_df)

        st.subheader("FX Stress Test")
        stress_df = generate_fx_stress_table(
            session,
            starting_balance=float(starting_balance),
            horizon_days=int(horizon_days),
            base_currency=forecast_currency,
            shocks=[-0.1, 0.0, 0.1],
        )
        st.dataframe(stress_df, use_container_width=True)

        st.subheader("Forecast Detail")
        st.dataframe(forecast_df, use_container_width=True)
