from __future__ import annotations

import streamlit as st

from services.command_center import accept_weekly_plan, build_command_center


RISK_COLORS = {
    "low": "#2f9e44",
    "medium": "#f08c00",
    "high": "#e03131",
}


def render(session):
    st.header("Personal Command Center")
    st.caption("Your unified daily operating console: decisions, risk, deltas, and one-click weekly acceptance.")

    model = build_command_center(session)
    decisions = model["top_decisions"]
    risk = model["weekly_cash_risk"]
    changes = model["changes_since_yesterday"]

    st.subheader("Today's Top 3 Decisions")
    dcols = st.columns(3)
    for idx in range(3):
        item = decisions[idx] if idx < len(decisions) else {"title": "No decision", "detail": "", "impact": "low"}
        with dcols[idx]:
            st.container(border=True)
            st.markdown(f"**{item['title']}**")
            st.caption(item["detail"])
            st.caption(f"Impact: {str(item['impact']).upper()}")

    st.subheader("This Week's Cash Risk")
    c1, c2, c3 = st.columns(3)
    c1.metric("Risk level", risk["level"].upper())
    c2.metric("P(Negative) 7d proxy", f"{risk['probability_negative_7d_proxy']:.0%}")
    c3.metric("Safe-to-spend 7d proxy", f"${risk['safe_to_spend_7d_proxy']:.2f}")

    try:
        import altair as alt

        risk_df = risk["forecast"][["date", "balance_p10", "balance_p50", "balance_p90"]].melt(
            id_vars=["date"], var_name="band", value_name="balance"
        )
        line = (
            alt.Chart(risk_df)
            .mark_line(strokeWidth=3)
            .encode(
                x="date:T",
                y="balance:Q",
                color=alt.Color(
                    "band:N",
                    scale=alt.Scale(
                        domain=["balance_p10", "balance_p50", "balance_p90"],
                        range=["#ffa94d", RISK_COLORS.get(risk["level"], "#4dabf7"), "#69db7c"],
                    ),
                ),
                tooltip=["date:T", "band:N", "balance:Q"],
            )
            .properties(height=300)
        )
        st.altair_chart(line, use_container_width=True)
    except Exception:
        st.line_chart(risk["forecast"].set_index("date")[["balance_p10", "balance_p50", "balance_p90"]])

    st.subheader("What Changed Since Yesterday")
    ch1, ch2, ch3 = st.columns(3)
    ch1.metric("Net cash delta", f"${changes['net_delta']:.2f}", delta=f"vs yesterday: ${changes['net_yesterday']:.2f}")
    ch2.metric("Run count delta", str(changes["runs_today"]), delta=f"{changes['runs_delta']} vs yesterday")
    ch3.metric("New tasks today", str(changes["new_tasks_today"]))

    st.divider()
    if st.button("Accept Weekly Plan", type="primary"):
        result = accept_weekly_plan(session)
        st.success(
            f"Weekly plan accepted. Created {result['created_plan_task']} plan task and "
            f"{result['created_bill_tasks']} bill task(s)."
        )
        st.caption(f"Reference: {result['reference_id']}")
