from __future__ import annotations

import streamlit as st

from services.demo_loader import load_demo_data
from services.imports import ingest_transactions


def render(session):
    st.header("Settings & Data")

    uploads = st.file_uploader("Upload one or more transactions CSV files", accept_multiple_files=True, type=["csv"])
    if uploads and st.button("Import CSV Files", type="primary"):
        total_created = 0
        file_results = []
        for up in uploads:
            try:
                result = ingest_transactions(session, up)
                total_created += result["created"]
                file_results.append((up.name, result["created"], None))
            except Exception as exc:
                file_results.append((up.name, 0, str(exc)))

        st.success(f"Imported {total_created} new transactions across {len(uploads)} file(s)")
        for name, created, err in file_results:
            if err:
                st.error(f"{name}: failed - {err}")
            else:
                st.info(f"{name}: imported {created}")

    if st.button("Load Demo Data"):
        load_demo_data(session, ".")
        st.toast("Demo loaded")
        st.success("Demo data is ready. Visit Money Map.")

    st.markdown(
        """
**CSV Defaults (Canonical)**
- Required columns: `date` (YYYY-MM-DD), `description`, `amount` (+inflow, -outflow)
- Optional columns: `account`, `category`, `merchant`, `currency`

**Also supported (Card Statement format)**
- `statement_period_start`, `statement_period_end`, `card_last4`, `section`, `trans_date`, `post_date`, `description`, `amount_usd`, `foreign_amount`, `foreign_currency`, `exchange_rate`
- Mapping used: `trans_date -> date`, `amount_usd -> amount`, `card_last4 -> account`, `section -> category`, `foreign_currency -> currency`

- Imports are read-only and deduplicated by transaction hash.
        """
    )
