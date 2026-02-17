from __future__ import annotations

import streamlit as st

from services.demo_loader import load_demo_data
from services.fx import available_currencies, ensure_default_fx_rates, list_fx_rates, upsert_fx_rate
from services.imports import ingest_transactions
from services.user_settings import AUTOPILOT_MODES, get_or_create_user_settings, save_user_settings


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
    st.subheader("Personal Autopilot")
    mode_labels = {
        "suggest_only": "Suggest only (no automatic side effects)",
        "auto_create_tasks": "Auto-create tasks (manual execution checklist)",
        "auto_apply_internal_allocations": "Auto-apply internal allocations (pods only, no money movement)",
    }
    with st.form("autopilot_form"):
        mode = st.selectbox(
            "Autopilot mode",
            list(AUTOPILOT_MODES),
            index=list(AUTOPILOT_MODES).index(profile.autopilot_mode if profile.autopilot_mode in AUTOPILOT_MODES else "suggest_only"),
            format_func=lambda x: mode_labels.get(x, x),
        )
        c1, c2, c3 = st.columns(3)
        floor = c1.number_input(
            "Guardrail: minimum checking floor",
            min_value=0.0,
            value=float(profile.guardrail_min_checking_floor or 0.0),
            step=25.0,
        )
        category_cap = c2.number_input(
            "Guardrail: max daily category spend (0 disables)",
            min_value=0.0,
            value=float(profile.guardrail_max_category_daily or 0.0),
            step=25.0,
        )
        risk_pause = c3.slider(
            "Guardrail: pause when risk spike score >=",
            min_value=0.0,
            max_value=1.0,
            value=float(profile.guardrail_risk_pause_threshold or 0.6),
            step=0.05,
        )
        autopilot_submit = st.form_submit_button("Save autopilot settings")

    if autopilot_submit:
        updated = save_user_settings(
            session,
            user_name=profile.user_name,
            base_currency=profile.base_currency,
            autopilot_mode=mode,
            guardrail_min_checking_floor=floor,
            guardrail_max_category_daily=category_cap,
            guardrail_risk_pause_threshold=risk_pause,
        )
        st.success(f"Autopilot updated: {mode_labels.get(updated.autopilot_mode, updated.autopilot_mode)}")

    st.info(
        "Autopilot guardrails are enforced during scheduled runs: checking floor protection, "
        "category daily cap, and automatic pause on spending risk spikes."
    )

    st.divider()
    st.subheader("Multi-currency FX Controls")
    if st.button("Seed default FX rates"):
        created = ensure_default_fx_rates(session)
        st.success(f"Added {created} default FX pair(s)")

    with st.form("fx_form"):
        c1, c2, c3 = st.columns(3)
        fx_base = c1.text_input("From currency", value="USD", max_chars=8)
        fx_quote = c2.text_input("To currency", value="EUR", max_chars=8)
        fx_rate = c3.number_input("Rate", min_value=0.000001, value=0.92, step=0.01, format="%.6f")
        fx_submit = st.form_submit_button("Save FX Rate")
    if fx_submit:
        row = upsert_fx_rate(session, fx_base, fx_quote, fx_rate)
        st.success(f"Saved FX {row.base_currency}->{row.quote_currency} @ {row.rate:.6f}")

    rates = list_fx_rates(session)
    if rates:
        st.dataframe(
            [
                {
                    "base": r.base_currency,
                    "quote": r.quote_currency,
                    "rate": r.rate,
                    "source": r.source,
                    "updated_at": r.updated_at,
                }
                for r in rates
            ],
            use_container_width=True,
        )
    else:
        st.info("No FX rates yet. Add a pair to enable cross-currency controls in forecasting and rules.")

    st.caption(f"Available currencies: {', '.join(available_currencies(session))}")

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
