from __future__ import annotations

import streamlit as st

from db.engine import SessionLocal, init_db
from services.scheduler import start_local_scheduler
from services.user_settings import get_or_create_user_settings
from ui.pages import activity, command_center, forecast, intelligence, map_view, planner, rules, scenario_lab, settings, simulate, tasks_view

st.set_page_config(page_title="FlowLedger", layout="wide")

init_db()

PAGES = {
    "Command Center": command_center.render,
    "Intelligence": intelligence.render,
    "Money Map": map_view.render,
    "Rule Builder": rules.render,
    "Income & Bills": planner.render,
    "Simulator": simulate.render,
    "Cashflow Forecast": forecast.render,
    "Scenario Lab": scenario_lab.render,
    "Activity": activity.render,
    "Next Actions": tasks_view.render,
    "Settings": settings.render,
}


@st.cache_resource
def get_session():
    return SessionLocal()


@st.cache_resource
def get_scheduler():
    return start_local_scheduler(SessionLocal)


def main():
    st.title("FlowLedger")
    session = get_session()
    profile = get_or_create_user_settings(session)

    scheduler = get_scheduler()

    st.caption(f"Personal money routing simulator for {profile.user_name} (dry-run only)")
    st.sidebar.info("🔒 Personal-use mode (single-user, local data only)")
    st.sidebar.success(f"⏱️ Scheduler active: {scheduler.running}")

    page = st.sidebar.radio("Navigate", list(PAGES.keys()))
    PAGES[page](session)


if __name__ == "__main__":
    main()
