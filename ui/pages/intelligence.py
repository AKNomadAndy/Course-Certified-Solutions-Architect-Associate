from __future__ import annotations

from datetime import date

import streamlit as st

from services.personal_intelligence import apply_adaptive_policy_tweaks, generate_adaptive_policy_tweaks, generate_monthly_retrospective
from services.user_settings import RISK_TOLERANCES, get_or_create_user_settings, save_user_settings


def _metric_card(title: str, value: str, help_text: str | None = None):
    st.metric(title, value)
    if help_text:
        st.caption(help_text)


def render(session):
    st.header("Personal Intelligence Memory")
    st.caption("Behavior-aware insights: retrospectives, recommendation acceptance, adaptive thresholds, and policy tweaks.")

    settings = get_or_create_user_settings(session)

    st.subheader("Risk Preference & Adaptation")
    c1, c2 = st.columns([2, 1])
    with c1:
        selected = st.selectbox(
            "Risk tolerance",
            options=list(RISK_TOLERANCES),
            index=max(0, list(RISK_TOLERANCES).index(settings.risk_tolerance if settings.risk_tolerance in RISK_TOLERANCES else "balanced")),
            help="Conservative = tighter guardrails, Aggressive = looser guardrails.",
        )
    with c2:
        adaptive_enabled = st.checkbox("Enable adaptive thresholds", value=bool(settings.adaptive_thresholds_enabled))

    if st.button("Save risk preference"):
        save_user_settings(session, settings.user_name, settings.base_currency, risk_tolerance=selected, adaptive_thresholds_enabled=adaptive_enabled)
        st.success("Risk preference saved.")

    st.divider()
    st.subheader("Monthly Retrospective")
    retrospective = generate_monthly_retrospective(session, for_month=date.today())
    cur = retrospective["current"]
    prev = retrospective["previous"]

    r1, r2, r3, r4 = st.columns(4)
    with r1:
        _metric_card("Net cashflow", f"${cur['net_cashflow']:,.2f}", f"Prev: ${prev['net_cashflow']:,.2f}")
    with r2:
        _metric_card("Run success rate", f"{cur['run_success_rate']:.0%}", f"Prev: {prev['run_success_rate']:.0%}")
    with r3:
        _metric_card("Tasks done", str(cur["tasks_done"]), f"Prev: {prev['tasks_done']}")
    with r4:
        _metric_card(
            "Recommendation acceptance",
            f"{cur['recommendation_acceptance_rate']:.0%}",
            f"Prev: {prev['recommendation_acceptance_rate']:.0%}",
        )

    c_improved, c_worsened = st.columns(2)
    with c_improved:
        st.markdown("#### ✅ Improved")
        improved = retrospective.get("improved", [])
        if improved:
            st.dataframe(improved, use_container_width=True, hide_index=True)
        else:
            st.info("No material improvements yet this month.")
    with c_worsened:
        st.markdown("#### ⚠️ Worsened")
        worsened = retrospective.get("worsened", [])
        if worsened:
            st.dataframe(worsened, use_container_width=True, hide_index=True)
        else:
            st.info("No worsened indicators this month.")

    st.divider()
    st.subheader("Auto-generated Monthly Policy Tweaks")
    tweaks = generate_adaptive_policy_tweaks(session)
    i1, i2, i3 = st.columns(3)
    i1.metric("Spend volatility", f"{tweaks['inputs']['spend_volatility']:.2f}")
    i2.metric("Paycheck timing score", f"{tweaks['inputs']['paycheck_timing_score']:.2f}")
    i3.metric("Risk profile", tweaks["inputs"]["risk_tolerance"].capitalize())

    st.caption("Current vs suggested guardrails")
    rows = []
    for key, current_value in tweaks["current"].items():
        rows.append({"setting": key, "current": current_value, "suggested": tweaks["suggested"].get(key)})
    st.dataframe(rows, use_container_width=True, hide_index=True)

    if st.button("Apply suggested policy tweaks", type="primary", disabled=not adaptive_enabled):
        updated = apply_adaptive_policy_tweaks(session, tweaks)
        st.success(
            "Applied policy tweaks: floor ${:.2f}, risk pause {:.2f}, max category/day ${:.2f}".format(
                float(updated.guardrail_min_checking_floor or 0.0),
                float(updated.guardrail_risk_pause_threshold or 0.0),
                float(updated.guardrail_max_category_daily or 0.0),
            )
        )
    if not adaptive_enabled:
        st.info("Enable adaptive thresholds above to apply monthly suggested guardrails.")
