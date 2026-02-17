from __future__ import annotations

import streamlit as st

from services.health import build_health_report


def render(session):
    st.header("System Health")
    st.caption("Local-first reliability status: scheduler, imports, tasks, and staleness warnings.")

    report = build_health_report(session)

    c1, c2, c3 = st.columns(3)
    c1.metric("Scheduler", report["scheduler"]["state"].upper())
    c2.metric("Open tasks", str(report["open_tasks"]))
    last_quality = report["last_import"]["quality_score"]
    c3.metric("Last import quality", f"{last_quality:.1f}" if isinstance(last_quality, float) else "N/A")

    st.subheader("Heartbeat")
    st.json(report["scheduler"], expanded=False)

    st.subheader("Last scheduled run")
    st.json(report["last_schedule_run"], expanded=False)

    st.subheader("Last import")
    st.json(report["last_import"], expanded=False)

    if report["warnings"]:
        st.warning("\n".join(report["warnings"]))
    else:
        st.success("No stale-data or scheduler heartbeat warnings detected.")
