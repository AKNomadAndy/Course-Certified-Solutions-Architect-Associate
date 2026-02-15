from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from db import models


def render(session):
    st.header("Activity Feed & Audit")

    runs = session.scalars(select(models.Run).order_by(models.Run.created_at.desc())).all()
    rows = [
        {
            "run_id": r.id,
            "rule_id": r.rule_id,
            "event_key": r.event_key,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in runs
    ]
    df = pd.DataFrame(rows)

    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Runs", len(df))
        c2.metric("Completed", int((df["status"] == "completed").sum()))
        c3.metric("Failures", int((df["status"].isin(["action_failed", "condition_failed"])).sum()))

        st.subheader("Run Volume & Status")
        timeline = df.set_index("created_at").resample("D").size().rename("runs").reset_index()
        mix = df.groupby("status", as_index=False).size().rename(columns={"size": "count"})

        a, b = st.columns(2)
        try:
            import altair as alt

            line = (
                alt.Chart(timeline)
                .mark_area(line={"color": "#69db7c"}, color="#69db7c33")
                .encode(x="created_at:T", y="runs:Q", tooltip=["created_at:T", "runs:Q"])
                .properties(height=280, title="Run Volume Over Time")
            )
            bars = (
                alt.Chart(mix)
                .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
                .encode(x="status:N", y="count:Q", color=alt.value("#4dabf7"), tooltip=["status", "count"])
                .properties(height=280, title="Status Mix")
            )
            a.altair_chart(line, use_container_width=True)
            b.altair_chart(bars, use_container_width=True)
        except Exception:
            a.area_chart(timeline.set_index("created_at")["runs"])
            b.bar_chart(mix, x="status", y="count", color="#4dabf7")

        st.subheader("Run Timeline")
        st.dataframe(df, use_container_width=True)
        st.download_button("Export CSV", data=df.to_csv(index=False), file_name="activity_feed.csv", mime="text/csv")
    else:
        st.info("No runs yet. Execute a simulation or scheduled tick to populate activity.")

    st.subheader("Latest run explanation")
    if runs:
        st.json(runs[0].trace)
