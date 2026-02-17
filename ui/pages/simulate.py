from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import select

from db import models
from services.simulator import simulate_rule


def _forecast_cashflow(transactions: list[models.Transaction], horizon_days: int = 30) -> pd.DataFrame:
    if not transactions:
        return pd.DataFrame(columns=["date", "projected_net"])

    df = pd.DataFrame([{"date": t.date, "amount": t.amount} for t in transactions])
    daily = df.groupby("date", as_index=False)["amount"].sum().sort_values("date")
    daily["date"] = pd.to_datetime(daily["date"])

    daily["rolling"] = daily["amount"].rolling(7, min_periods=2).mean()
    recent = daily.tail(min(14, len(daily))).copy()
    if len(recent) < 2:
        slope = 0.0
    else:
        x0 = recent["date"].min()
        recent["x"] = (recent["date"] - x0).dt.days
        x_mean = recent["x"].mean()
        y_mean = recent["rolling"].fillna(recent["amount"]).mean()
        num = ((recent["x"] - x_mean) * (recent["rolling"].fillna(recent["amount"]) - y_mean)).sum()
        den = ((recent["x"] - x_mean) ** 2).sum()
        slope = float(num / den) if den else 0.0

    base = float(daily["rolling"].iloc[-1] if pd.notna(daily["rolling"].iloc[-1]) else daily["amount"].iloc[-1])
    start = daily["date"].max() + timedelta(days=1)
    projection = []
    for i in range(horizon_days):
        projection.append({"date": start + timedelta(days=i), "projected_net": round(base + slope * i, 2)})

    return pd.DataFrame(projection)


def render(session):
    st.header("Simulator")
    st.caption("Run deterministic dry-run simulations and inspect projected cashflow trends.")

    rules = session.scalars(select(models.Rule).order_by(models.Rule.priority.desc())).all()
    if not rules:
        st.info("No rules yet")
        return

    picked = st.selectbox("Rule", rules, format_func=lambda r: f"{r.name} (p={r.priority})")
    days = st.number_input("Lookback days", min_value=7, max_value=365, value=90)

    if st.button("Run simulation", type="primary"):
        report = simulate_rule(session, picked.id, days=days)

        c1, c2, c3 = st.columns(3)
        c1.metric("Warnings", len(report.summary.get("warnings", [])))
        c2.metric("Tasks Created", report.summary.get("tasks_created", 0))
        c3.metric("Pods Allocated", len(report.summary.get("totals_allocated_per_pod", {})))

        st.subheader("Allocation Breakdown")
        totals = report.summary.get("totals_allocated_per_pod", {})
        if totals:
            alloc_df = pd.DataFrame([{"pod": str(k), "allocated": v} for k, v in totals.items()])
            st.bar_chart(alloc_df, x="pod", y="allocated", color="#69db7c")
        else:
            st.info("No allocations in selected period.")

        st.subheader("Cashflow Projection (next 30 days)")
        txs = session.scalars(select(models.Transaction).order_by(models.Transaction.date)).all()
        forecast_df = _forecast_cashflow(txs, horizon_days=30)
        if not forecast_df.empty:
            st.line_chart(forecast_df.set_index("date"))
            st.dataframe(forecast_df.tail(10), use_container_width=True)
        else:
            st.info("Not enough history to generate projection.")

        with st.expander("Step-by-step trace"):
            for t in report.traces[:60]:
                st.write(f"Tx {t['transaction_id']}: {t['status']}")
                explain = (t.get("trace") or {}).get("explainability", {})
                fired = (t.get("trace") or {}).get("rule_fired", {})
                if explain:
                    st.caption(f"Why: {explain.get('why_recommendation', 'n/a')}")
                    st.caption(f"If skipped: {explain.get('what_if_skip', 'n/a')}")
                    badge = explain.get("confidence_badge", "low")
                    icon = "🟢" if badge == "high" else ("🟡" if badge == "medium" else "🔴")
                    st.caption(f"Confidence: {icon} {badge.title()}")
                if fired:
                    st.caption(
                        f"Rule fired: #{fired.get('rule_id')} {fired.get('rule_name')} "
                        f"(base {fired.get('base_currency')}, priority {fired.get('priority')})"
                    )
                st.json(t["trace"])
