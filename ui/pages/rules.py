from __future__ import annotations

import json

import streamlit as st
from sqlalchemy import select

from db import models
from services.rules_engine import run_rule


def _load_json(label: str, value: str, expected_type):
    try:
        parsed = json.loads(value)
        if not isinstance(parsed, expected_type):
            st.error(f"{label} must be {expected_type.__name__}.")
            return None
        return parsed
    except json.JSONDecodeError as exc:
        st.error(f"Invalid JSON for {label}: {exc}")
        return None


def render(session):
    st.header("Rule Builder")
    st.caption("Create, edit, enable, and test rules with a clean editor.")

    rules = session.scalars(select(models.Rule).order_by(models.Rule.priority.desc(), models.Rule.created_at.asc())).all()
    picked = st.selectbox("Edit existing rule", [None] + rules, format_func=lambda r: "Create new rule" if r is None else f"#{r.id} {r.name}")

    base = {
        "name": "",
        "priority": 100,
        "trigger_type": "transaction",
        "trigger_config": '{"description_contains": "Payroll"}',
        "conditions": '[{"type":"amount_gte","value":100}]',
        "actions": '[{"type":"allocate_fixed","pod_id":1,"amount":50,"up_to_available":true}]',
        "enabled": False,
    }
    if picked:
        base = {
            "name": picked.name,
            "priority": picked.priority,
            "trigger_type": picked.trigger_type,
            "trigger_config": json.dumps(picked.trigger_config, indent=2),
            "conditions": json.dumps(picked.conditions, indent=2),
            "actions": json.dumps(picked.actions, indent=2),
            "enabled": picked.enabled,
        }

    name = st.text_input("Rule name", value=base["name"])
    c1, c2 = st.columns(2)
    priority = c1.number_input("Priority (higher wins)", min_value=1, max_value=999, value=int(base["priority"]))
    enabled = c2.checkbox("Enabled", value=bool(base["enabled"]))

    trigger_type = st.selectbox("Trigger", ["transaction", "schedule", "manual"], index=["transaction", "schedule", "manual"].index(base["trigger_type"]))
    trigger_config_text = st.text_area("Trigger config JSON", value=base["trigger_config"], height=100)
    conditions_text = st.text_area("Conditions JSON list", value=base["conditions"], height=120)
    actions_text = st.text_area("Actions JSON list", value=base["actions"], height=140)

    save_col, sim_col, del_col = st.columns(3)
    if save_col.button("Save Rule", type="primary"):
        trigger_config = _load_json("trigger_config", trigger_config_text, dict)
        conditions = _load_json("conditions", conditions_text, list)
        actions = _load_json("actions", actions_text, list)
        if trigger_config is not None and conditions is not None and actions is not None and name.strip():
            target = picked or models.Rule(name=name.strip())
            if not picked:
                session.add(target)
            target.name = name.strip()
            target.priority = int(priority)
            target.trigger_type = trigger_type
            target.trigger_config = trigger_config
            target.conditions = conditions
            target.actions = actions
            target.enabled = enabled
            session.commit()
            st.success(f"Saved rule: {target.name}")

    if sim_col.button("Simulate on latest transaction"):
        rule = picked
        tx = session.scalar(select(models.Transaction).order_by(models.Transaction.created_at.desc()))
        if rule and tx:
            run, _ = run_rule(
                session,
                rule,
                {"type": "transaction", "event_key": f"manual-sim:{rule.id}:{tx.id}", "transaction_id": tx.id},
                tx=tx,
            )
            st.json(run.trace)
        else:
            st.info("Select a saved rule and ensure at least one transaction exists.")

    if del_col.button("Delete Rule") and picked:
        session.delete(picked)
        session.commit()
        st.success("Rule deleted")

    st.subheader("All Rules")
    st.dataframe(
        [
            {
                "id": r.id,
                "name": r.name,
                "priority": r.priority,
                "trigger": r.trigger_type,
                "enabled": r.enabled,
                "created_at": r.created_at,
            }
            for r in rules
        ],
        use_container_width=True,
    )
