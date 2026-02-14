from __future__ import annotations

import streamlit as st

from services.demo_loader import load_demo_data
from services.imports import ingest_transactions


def render(session):
    st.header("Settings & Data")
    up = st.file_uploader("Upload transactions CSV")
    if up and st.button("Import CSV"):
        result = ingest_transactions(session, up)
        st.success(f"Imported {result['created']} transactions")

    if st.button("Load Demo Data"):
        load_demo_data(session, ".")
        st.toast("Demo loaded")
        st.success("Demo data is ready. Visit Money Map.")

    st.markdown(
        """
**CSV Defaults**
- Required columns: `date` (YYYY-MM-DD), `description`, `amount` (+inflow, -outflow)
- Optional columns: `account`, `category`, `merchant`, `currency`
- Imports are read-only and deduplicated by content hash.
        """
    )
