from __future__ import annotations

import streamlit as st

from services.command_center import accept_weekly_plan, build_command_center
from services.demo_loader import load_demo_data
from services.planner import generate_monthly_bill_tasks
from services.rules_engine import scheduler_tick


RISK_COLORS = {
    "low": "#2f9e44",
    "medium": "#f08c00",
    "high": "#e03131",
}


def render(session):
    st.header("Personal Command Center")
    st.caption("Your unified daily operating console: decisions, risk, deltas, and one-click weekly acceptance.")

    model = build_command_center(session)
    brief = model["daily_brief"]
    wizard = model["setup_wizard"]
    decisions = model["top_decisions"]
    risk = model["weekly_cash_risk"]
    changes = model["changes_since_yesterday"]

    st.subheader("Daily Brief")
    b1, b2, b3 = st.columns(3)
    b1.metric("Open tasks", str(brief["open_tasks"]))
    b2.metric("Rule runs (24h)", str(brief["recent_runs_24h"]))
    b3.metric("Focus", "Backlog" if brief["open_tasks"] else "Stable")
    st.info(f"{brief['headline']} — {brief['priority_note']}")

    st.subheader("Quick Actions")
    st.caption("Keyboard-first: use quick command box (`a`,`s`,`b`,`d`) then press Enter.")
    quick_cols = st.columns(4)
    if quick_cols[0].button("Accept weekly plan"):
        result = accept_weekly_plan(session)
        st.success(f"Accepted weekly plan ({result['created_bill_tasks']} bill task(s) created).")
    if quick_cols[1].button("Run scheduler now"):
        runs = scheduler_tick(session)
        st.success(f"Scheduler executed now. Runs evaluated: {len(runs)}")
    if quick_cols[2].button("Generate bill tasks"):
        created = generate_monthly_bill_tasks(session)
        st.success(f"Created {created} bill task(s).")
    if quick_cols[3].button("Load demo data"):
        load_demo_data(session, ".")
        st.success("Demo data loaded.")

    with st.form("quick_command_form"):
        quick_cmd = st.text_input("Quick command", value="", placeholder="a=accept weekly, s=scheduler tick, b=bill tasks, d=demo")
        run_quick = st.form_submit_button("Run quick command")
    if run_quick and quick_cmd:
        cmd = quick_cmd.strip().lower()
        if cmd == "a":
            result = accept_weekly_plan(session)
            st.success(f"Quick action complete: accepted weekly plan ({result['created_bill_tasks']} bill task(s)).")
        elif cmd == "s":
            runs = scheduler_tick(session)
            st.success(f"Quick action complete: scheduler tick executed ({len(runs)} run(s)).")
        elif cmd == "b":
            created = generate_monthly_bill_tasks(session)
            st.success(f"Quick action complete: created {created} bill task(s).")
        elif cmd == "d":
            load_demo_data(session, ".")
            st.success("Quick action complete: demo data loaded.")
        else:
            st.warning("Unknown quick command. Use a/s/b/d.")

    if wizard["is_empty_state"]:
        st.subheader("Setup Wizard")
        st.caption("It looks like this is a fresh setup. Follow these defaults to get started in under 2 minutes.")
        for idx, step in enumerate(wizard["steps"], start=1):
            st.markdown(f"**{idx}. {step['title']}**")
            st.caption(step["hint"])

    st.subheader("Today's Top 3 Decisions")
    dcols = st.columns(3)
    for idx in range(3):
        item = decisions[idx] if idx < len(decisions) else {"title": "No decision", "detail": "", "impact": "low"}
        with dcols[idx]:
            st.container(border=True)
            st.markdown(f"**{item['title']}**")
            st.caption(item["detail"])
            st.caption(f"Impact: {str(item['impact']).upper()}")
            with st.expander("Why this recommendation?", expanded=False):
                st.write(item.get("why", "Based on your current rules, tasks, and risk signals."))
            with st.expander("What if I skip this?", expanded=False):
                st.write(item.get("skip", "Skipping may delay progress but does not move money automatically."))

    st.subheader("This Week's Cash Risk")
    c1, c2, c3 = st.columns(3)
    c1.metric("Risk level", risk["level"].upper())
    badge = "🟢 High confidence" if risk["level"] == "low" else ("🟡 Medium confidence" if risk["level"] == "medium" else "🔴 Lower confidence")
    st.caption(f"Forecast confidence badge: {badge}")
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
