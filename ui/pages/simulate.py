from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from db import models
from services.simulator import simulate_rule


def render(session):
    st.header("Simulator")
    rules = session.scalars(select(models.Rule).order_by(models.Rule.priority.desc())).all()
    if not rules:
        st.info("No rules yet")
        return
    picked = st.selectbox("Rule", rules, format_func=lambda r: f"{r.name} (p={r.priority})")
    days = st.number_input("Lookback days", min_value=7, max_value=365, value=90)
    if st.button("Run simulation"):
        report = simulate_rule(session, picked.id, days=days)
        st.subheader("Summary")
        st.json(report.summary)
        st.subheader("Step trace")
        for t in report.traces[:40]:
            st.write(f"Tx {t['transaction_id']}: {t['status']}")
            st.json(t["trace"])
