from __future__ import annotations

import streamlit as st

from services.demo_loader import load_demo_data
from services.imports import ingest_transactions
from services.user_settings import get_or_create_user_settings, save_user_settings


def render(session):
    st.header("Settings & Data")

    st.subheader("Personal Profile")
    profile = get_or_create_user_settings(session)
    with st.form("profile_form"):
        user_name = st.text_input("Display name", value=profile.user_name)
        base_currency = st.text_input("Base currency", value=profile.base_currency, max_chars=8)
        submitted = st.form_submit_button("Save profile", type="primary")
    if submitted:
        updated = save_user_settings(session, user_name=user_name, base_currency=base_currency)
        st.success(f"Saved profile for {updated.user_name} ({updated.base_currency})")

    st.caption("Personal-use mode: no auth, no multi-tenant sharing, local dry-run planning only.")

    st.divider()
    st.subheader("Import Transactions")
    uploads = st.file_uploader("Upload one or more transactions CSV files", accept_multiple_files=True, type=["csv"])
    if uploads and st.button("Import CSV Files"):
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
