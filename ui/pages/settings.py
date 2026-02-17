from __future__ import annotations

import pandas as pd
import streamlit as st

from services.backup import create_db_snapshot, create_encrypted_backup, latest_backup, list_backups, restore_encrypted_backup
from services.demo_loader import load_demo_data
from services.fx import (
    available_currencies,
    currency_exposure,
    ensure_default_fx_rates,
    list_fx_rates,
    list_fx_snapshots,
    upsert_fx_rate,
    upsert_fx_snapshot,
)
from services.imports import (
    ingest_transactions,
    list_import_profiles,
    list_merchant_category_rules,
    upsert_merchant_category_rule,
)
from services.user_settings import AUTOPILOT_MODES, get_or_create_user_settings, save_user_settings


def _quality_badge(score: float) -> str:
    if score >= 85:
        return "🟢"
    if score >= 65:
        return "🟡"
    return "🔴"


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
    st.subheader("Backup & Disaster Recovery")
    with st.form("backup_form"):
        passphrase = st.text_input("Backup passphrase", type="password", help="Used to encrypt/decrypt local backup archives.")
        label = st.text_input("Backup label", value="manual")
        backup_submit = st.form_submit_button("Create encrypted backup")
    if backup_submit:
        try:
            result = create_encrypted_backup(passphrase=passphrase, label=label)
            st.success(f"Encrypted backup created: {result.path}")
        except Exception as exc:
            st.error(f"Backup failed: {exc}")

    snapshots_col, restore_col = st.columns(2)
    with snapshots_col:
        if st.button("Create DB snapshot"):
            try:
                snap = create_db_snapshot(reason="manual")
                st.success(f"Snapshot created: {snap.path}")
            except Exception as exc:
                st.error(f"Snapshot failed: {exc}")
    with restore_col:
        backup_files = list_backups(limit=20)
        selected = st.selectbox("Restore from encrypted backup", options=backup_files, index=0 if backup_files else None)
        restore_passphrase = st.text_input("Restore passphrase", type="password")
        if st.button("Restore backup", type="primary", disabled=not bool(backup_files)):
            try:
                out = restore_encrypted_backup(selected, restore_passphrase, snapshot_before_restore=True)
                st.success(f"Restore complete. Database restored to {out['restored_to']}")
                if out.get("snapshot"):
                    st.caption(f"Pre-restore snapshot: {out['snapshot']}")
            except Exception as exc:
                st.error(f"Restore failed: {exc}")

    newest = latest_backup()
    if newest:
        st.caption(f"Latest encrypted backup: {newest}")

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
        floor = c1.number_input("Guardrail: minimum checking floor", min_value=0.0, value=float(profile.guardrail_min_checking_floor or 0.0), step=25.0)
        category_cap = c2.number_input("Guardrail: max daily category spend (0 disables)", min_value=0.0, value=float(profile.guardrail_max_category_daily or 0.0), step=25.0)
        risk_pause = c3.slider("Guardrail: pause when risk spike score >=", min_value=0.0, max_value=1.0, value=float(profile.guardrail_risk_pause_threshold or 0.6), step=0.05)
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
        st.dataframe([{"base": r.base_currency, "quote": r.quote_currency, "rate": r.rate, "source": r.source, "updated_at": r.updated_at} for r in rates], use_container_width=True)

    with st.form("fx_snapshot_form"):
        s1, s2, s3, s4 = st.columns(4)
        snap_base = s1.text_input("Snapshot from", value="USD", max_chars=8)
        snap_quote = s2.text_input("Snapshot to", value="EUR", max_chars=8)
        snap_rate = s3.number_input("Snapshot rate", min_value=0.000001, value=0.92, step=0.01, format="%.6f")
        snap_date = s4.date_input("Snapshot date")
        snap_submit = st.form_submit_button("Save FX Snapshot")
    if snap_submit:
        snap = upsert_fx_snapshot(session, snap_base, snap_quote, snap_rate, snap_date)
        st.success(f"Saved historical FX {snap.base_currency}->{snap.quote_currency} @ {snap.rate:.6f} for {snap.snapshot_date}")

    snapshots = list_fx_snapshots(session)
    if snapshots:
        st.caption("Historical FX snapshots")
        st.dataframe([{"date": s.snapshot_date, "base": s.base_currency, "quote": s.quote_currency, "rate": s.rate, "source": s.source} for s in snapshots[:120]], use_container_width=True)

    st.caption(f"Available currencies: {', '.join(available_currencies(session))}")

    st.subheader("Portfolio Currency Exposure")
    exposure_rows = currency_exposure(session, base_currency=profile.base_currency)
    if exposure_rows:
        st.dataframe(exposure_rows, use_container_width=True)

    st.divider()
    st.subheader("Data Quality + Ingestion Moat")

    with st.form("merchant_rule_form"):
        m1, m2 = st.columns(2)
        merchant_pattern = m1.text_input("Merchant match (contains)", value="")
        merchant_category = m2.text_input("Always map to category", value="")
        save_merchant_rule = st.form_submit_button("Save Merchant Category Rule")
    if save_merchant_rule and merchant_pattern.strip() and merchant_category.strip():
        upsert_merchant_category_rule(session, merchant_pattern, merchant_category)
        st.success("Saved merchant category rule")

    merchant_rules = list_merchant_category_rules(session)
    if merchant_rules:
        st.caption("Categorization feedback loop rules")
        st.dataframe(
            [{"merchant_pattern": r.merchant_pattern, "category": r.category, "created_at": r.created_at} for r in merchant_rules],
            use_container_width=True,
        )

    profiles = list_import_profiles(session)
    if profiles:
        st.caption("Remembered column mappings by export format")
        st.dataframe(
            [
                {
                    "institution": p.institution_label,
                    "export_key": p.export_key,
                    "sample_columns": ", ".join(p.sample_columns[:8]),
                    "mapping": p.column_mapping,
                    "updated_at": p.updated_at,
                }
                for p in profiles
            ],
            use_container_width=True,
        )

    st.subheader("Import Transactions")
    uploads = st.file_uploader("Upload one or more transactions CSV files", accept_multiple_files=True, type=["csv"])
    if uploads and st.button("Import CSV Files"):
        try:
            create_db_snapshot(reason="before_import")
        except Exception:
            pass
        total_created = 0
        quality_rows = []
        for up in uploads:
            try:
                result = ingest_transactions(session, up, filename=up.name)
                total_created += result["created"]
                report = result.get("report", {})
                quality_rows.append(
                    {
                        "file": up.name,
                        "created": result["created"],
                        "quality": report.get("quality_score", 0),
                        "rows_total": report.get("rows_total", 0),
                        "duplicates": report.get("exact_duplicates", 0),
                        "conflicts": report.get("conflict_duplicates", 0),
                        "anomalies": len(report.get("anomalies", [])),
                        "_conflicts": result.get("conflicts", []),
                        "_anomalies": report.get("anomalies", []),
                    }
                )
            except Exception as exc:
                quality_rows.append({"file": up.name, "created": 0, "quality": 0, "error": str(exc), "_conflicts": [], "_anomalies": []})

        st.success(f"Imported {total_created} new transactions across {len(uploads)} file(s)")

        for row in quality_rows:
            if row.get("error"):
                st.error(f"{row['file']}: failed - {row['error']}")
                continue
            st.markdown(f"**{row['file']}** — Quality score: {_quality_badge(row['quality'])} {row['quality']}/100")
            st.caption(
                f"created={row['created']} | rows={row['rows_total']} | duplicates={row['duplicates']} | "
                f"conflicts={row['conflicts']} | anomalies={row['anomalies']}"
            )
            if row["_conflicts"]:
                st.warning("Potential duplicate conflicts detected (smart dedupe resolver):")
                st.dataframe(pd.DataFrame(row["_conflicts"]), use_container_width=True)
            if row["_anomalies"]:
                st.info("Anomaly detector flagged these rows:")
                st.dataframe(pd.DataFrame(row["_anomalies"]), use_container_width=True)

    if st.button("Load Demo Data"):
        try:
            create_db_snapshot(reason="before_demo_load")
        except Exception:
            pass
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
