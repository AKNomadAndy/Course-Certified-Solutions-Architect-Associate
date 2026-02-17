from __future__ import annotations

import streamlit as st

from services.scenario_lab import run_scenarios, save_scenario_task


def render(session):
    st.header("Scenario Lab")
    st.caption("Fast decision simulator for strategic what-if planning.")

    c1, c2 = st.columns(2)
    extra_debt = c1.number_input("If I pay extra toward debt monthly ($)", min_value=0.0, value=300.0, step=25.0)
    income_drop = c2.slider("If income drops (%)", min_value=0, max_value=60, value=15, step=1)

    c3, c4 = st.columns(2)
    rent_up = c3.number_input("If rent increases by ($)", min_value=0.0, value=200.0, step=25.0)
    rent_after = c4.number_input("...starting in month #", min_value=1, max_value=12, value=2)

    eurusd_target = st.number_input("If FX EURUSD moves to X", min_value=0.1, max_value=5.0, value=1.0, step=0.01, format="%.4f")

    if st.button("Run Scenario Lab", type="primary"):
        out = run_scenarios(
            session,
            extra_debt_payment=float(extra_debt),
            income_drop_pct=float(income_drop),
            rent_increase_amount=float(rent_up),
            rent_increase_after_month=int(rent_after),
            eurusd_target=float(eurusd_target),
        )

        st.subheader("Baseline")
        b1, b2, b3 = st.columns(3)
        b1.metric("Baseline P(Negative) 14d", f"{out['baseline']['forecast']['probability_negative_14d']:.0%}")
        b2.metric("Baseline debt interest (24m)", f"${out['baseline']['debt'].get('total_interest', 0):,.2f}")
        b3.metric("Generated on", out["generated_on"])

        st.subheader("Scenario Results")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Debt ending balance Δ", f"${out['extra_debt_payment']['ending_balance_delta']:,.2f}")
        s2.metric("Debt interest Δ", f"${out['extra_debt_payment']['interest_delta']:,.2f}")
        s3.metric("Income-drop net (6m)", f"${out['income_drop']['net_6m']:,.2f}")
        s4.metric("Rent-up net (6m)", f"${out['rent_increase']['net_6m']:,.2f}")

        st.markdown("### 1) If I pay extra debt monthly")
        st.dataframe(out["extra_debt_payment"]["table"], use_container_width=True)
        if st.button("Accept scenario: extra debt payment"):
            task = save_scenario_task(
                session,
                title="Apply extra monthly debt payment plan",
                note=f"Scenario accepted: add ${extra_debt:.2f}/mo to debt payoff plan.",
            )
            st.success(f"Created/kept scenario task #{task.id}")

        st.markdown("### 2) If income drops")
        st.dataframe(out["income_drop"]["projection"], use_container_width=True)

        st.markdown("### 3) If rent increases in future months")
        st.dataframe(out["rent_increase"]["projection"], use_container_width=True)

        st.markdown("### 4) If EURUSD moves to target")
        fx = out["fx_move"]
        st.caption(
            f"Current EURUSD: {fx['current_eurusd']} | Target: {fx['target_eurusd']} | "
            f"Implied stress: {fx['implied_stress_pct']}%"
        )
        st.metric("FX scenario P(Negative) 14d", f"{fx['forecast']['probability_negative_14d']:.0%}")
        st.dataframe(fx["table"], use_container_width=True)
