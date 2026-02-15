from __future__ import annotations

import streamlit as st

from db.engine import SessionLocal, init_db
from ui.pages import activity, map_view, rules, settings, simulate, tasks_view

st.set_page_config(page_title="FlowLedger", layout="wide")

init_db()

PAGES = {
    "Money Map": map_view.render,
    "Rule Builder": rules.render,
    "Simulator": simulate.render,
    "Activity": activity.render,
    "Next Actions": tasks_view.render,
    "Settings": settings.render,
}


@st.cache_resource
def get_session():
    return SessionLocal()


def main():
    st.title("FlowLedger")
    st.caption("Personal money routing simulator (dry-run only)")
    session = get_session()
    page = st.sidebar.radio("Navigate", list(PAGES.keys()))
    PAGES[page](session)


if __name__ == "__main__":
    main()
