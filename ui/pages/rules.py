from __future__ import annotations

import json
import streamlit as st
from sqlalchemy import select

from db import models
from services.rules_engine import run_rule


def render(session):
    st.header("Rule Builder")

    rule_name = st.text_input("Rule name")
    priority = st.number_input("Priority (higher wins)", min_value=1, max_value=999, value=100)
    trigger_type = st.selectbox("Trigger", ["transaction", "schedule", "manual"])
    trigger_config = st.text_area("Trigger config JSON", value='{"description_contains": "Payroll"}' if trigger_type == "transaction" else "{}")
    conditions_text = st.text_area("Conditions JSON list", value='[{"type":"amount_gte","value":100}]')
    actions_text = st.text_area("Actions JSON list", value='[{"type":"allocate_fixed","pod_id":1,"amount":50,"up_to_available":true}]')

    c1, c2, c3 = st.columns(3)
    if c1.button("Save draft") and rule_name:
        rule = models.Rule(
            name=rule_name,
            priority=int(priority),
            trigger_type=trigger_type,
            trigger_config=json.loads(trigger_config),
            conditions=json.loads(conditions_text),
            actions=json.loads(actions_text),
            enabled=False,
        )
        session.add(rule)
        session.commit()
        st.success("Draft saved")

    if c2.button("Enable/Disable rule"):
        rules = session.scalars(select(models.Rule).order_by(models.Rule.created_at.desc())).all()
        if rules:
            rules[0].enabled = not rules[0].enabled
            session.commit()
            st.info(f"Toggled {rules[0].name} => {rules[0].enabled}")

    if c3.button("Simulate"):
        rule = session.scalar(select(models.Rule).order_by(models.Rule.created_at.desc()))
        tx = session.scalar(select(models.Transaction).order_by(models.Transaction.created_at.desc()))
        if rule and tx:
            run, _ = run_rule(session, rule, {"type": "transaction", "event_key": f"manual-sim:{rule.id}:{tx.id}", "transaction_id": tx.id}, tx=tx)
            st.json(run.trace)

    st.subheader("Rules")
    rows = []
    for r in session.scalars(select(models.Rule).order_by(models.Rule.priority.desc())).all():
        rows.append({"id": r.id, "name": r.name, "priority": r.priority, "trigger": r.trigger_type, "enabled": r.enabled})
    st.dataframe(rows)
