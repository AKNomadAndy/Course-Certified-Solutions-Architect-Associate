from __future__ import annotations

import streamlit as st

from db.engine import SessionLocal, init_db
from services.user_settings import get_or_create_user_settings
from ui.pages import activity, forecast, map_view, planner, rules, settings, simulate, tasks_view

st.set_page_config(page_title="FlowLedger", layout="wide")

init_db()

PAGES = {
    "Money Map": map_view.render,
    "Rule Builder": rules.render,
    "Income & Bills": planner.render,
    "Simulator": simulate.render,
    "Cashflow Forecast": forecast.render,
    "Activity": activity.render,
    "Next Actions": tasks_view.render,
    "Settings": settings.render,
}


@st.cache_resource
def get_session():
    return SessionLocal()


def main():
    st.title("FlowLedger")
    session = get_session()
    profile = get_or_create_user_settings(session)
    st.caption(f"Personal money routing simulator for {profile.user_name} (dry-run only)")
    st.sidebar.info("🔒 Personal-use mode (single-user, local data only)")
    page = st.sidebar.radio("Navigate", list(PAGES.keys()))
    PAGES[page](session)


if __name__ == "__main__":
    main()
