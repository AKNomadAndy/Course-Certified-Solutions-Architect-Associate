from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from db import models


def render(session):
    st.header("Activity Feed & Audit")
    runs = session.scalars(select(models.Run).order_by(models.Run.created_at.desc())).all()
    rows = [{"run_id": r.id, "rule_id": r.rule_id, "event_key": r.event_key, "status": r.status, "created_at": r.created_at} for r in runs]
    df = pd.DataFrame(rows)
    st.dataframe(df)
    if not df.empty:
        st.download_button("Export CSV", data=df.to_csv(index=False), file_name="activity_feed.csv", mime="text/csv")

    st.subheader("Latest run explanation")
    if runs:
        st.json(runs[0].trace)
