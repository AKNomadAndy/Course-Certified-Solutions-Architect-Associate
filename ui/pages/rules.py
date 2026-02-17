from __future__ import annotations

import json

import streamlit as st
from sqlalchemy import select

from db import models
from services.fx import available_currencies
from services.rule_templates import build_template_payload, list_rule_templates
from services.rule_versions import list_rule_versions, rollback_to_version, snapshot_rule, version_diff
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


def _state_index(options: list[str], value: str) -> int:
    return options.index(value) if value in options else 0


def render(session):
    st.header("Rule Builder")
    st.caption("Create personal automation rules with templates, form builder, and JSON editor.")

    templates = list_rule_templates()
    pods = session.scalars(select(models.Pod).order_by(models.Pod.name)).all()
    currencies = available_currencies(session)

    with st.expander("Quick-start templates", expanded=True):
        tcol1, tcol2, tcol3 = st.columns([2, 1, 1])
        template_name = tcol1.selectbox("Template", list(templates.keys()))
        pod_map = {"Default pod #1": 1, **{f"{p.name} (#{p.id})": p.id for p in pods}}
        template_pod = tcol2.selectbox("Target pod", list(pod_map.keys()))
        apply_template = tcol3.button("Apply template")

        if apply_template:
            payload = build_template_payload(template_name, pod_id=pod_map[template_pod])
            st.session_state["rule_name"] = f"{template_name} - Personal"
            st.session_state["rule_priority"] = int(payload["priority"])
            st.session_state["rule_trigger_type"] = payload["trigger_type"]
            st.session_state["rule_trigger_config"] = json.dumps(payload["trigger_config"], indent=2)
            st.session_state["rule_conditions"] = json.dumps(payload["conditions"], indent=2)
            st.session_state["rule_actions"] = json.dumps(payload["actions"], indent=2)
            st.session_state["rule_enabled"] = True
            st.success("Template applied. Review and save below.")

    rules = session.scalars(select(models.Rule).order_by(models.Rule.priority.desc(), models.Rule.created_at.asc())).all()
    rule_options = [None] + [r.id for r in rules]
    selected_rule_id = st.selectbox(
        "Edit existing rule",
        rule_options,
        format_func=lambda rid: "Create new rule" if rid is None else f"#{rid} {session.get(models.Rule, rid).name}",
    )
    picked = session.get(models.Rule, selected_rule_id) if selected_rule_id else None

    base = {
        "name": st.session_state.get("rule_name", ""),
        "priority": st.session_state.get("rule_priority", 100),
        "trigger_type": st.session_state.get("rule_trigger_type", "transaction"),
        "trigger_config": st.session_state.get("rule_trigger_config", '{"description_contains": "Payroll"}'),
        "conditions": st.session_state.get("rule_conditions", '[{"type":"amount_gte","value":100}]'),
        "actions": st.session_state.get("rule_actions", '[{"type":"allocate_fixed","pod_id":1,"amount":50,"up_to_available":true}]'),
        "enabled": st.session_state.get("rule_enabled", False),
        "lifecycle_state": st.session_state.get("rule_lifecycle_state", "draft"),
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
            "lifecycle_state": picked.lifecycle_state,
        }

    with st.expander("No-code condition/action helper"):
        c1, c2, c3, c4 = st.columns(4)
        contains = c1.text_input("Transaction description contains", value="Payroll")
        amount_gte = c2.number_input("Min transaction amount", value=100.0, step=10.0)
        alloc_percent = c3.slider("Allocate percent", min_value=0, max_value=100, value=50)
        helper_currency = c4.selectbox("Transaction currency", currencies, index=0)
        chosen_pod = st.selectbox("Allocate to pod", list(pod_map.keys()), key="helper_pod")
        if st.button("Build rule JSON from helper"):
            helper_payload = {
                "trigger_config": {"description_contains": contains},
                "conditions": [
                    {"type": "amount_gte", "value": float(amount_gte)},
                    {"type": "currency_eq", "value": helper_currency},
                ],
                "actions": [{"type": "allocate_percent", "pod_id": pod_map[chosen_pod], "percent": int(alloc_percent)}],
            }
            st.session_state["rule_trigger_config"] = json.dumps(helper_payload["trigger_config"], indent=2)
            st.session_state["rule_conditions"] = json.dumps(helper_payload["conditions"], indent=2)
            st.session_state["rule_actions"] = json.dumps(helper_payload["actions"], indent=2)
            st.success("Generated JSON fields from helper.")
            st.rerun()

    name = st.text_input("Rule name", value=base["name"], key="rule_name")
    c1, c2, c3 = st.columns(3)
    priority = c1.number_input("Priority (higher wins)", min_value=1, max_value=999, value=int(base["priority"]), key="rule_priority")
    enabled = c2.checkbox("Enabled", value=bool(base["enabled"]), key="rule_enabled")
    lifecycle_options = ["draft", "active"]
    lifecycle_state = c3.selectbox(
        "Lifecycle",
        lifecycle_options,
        index=_state_index(lifecycle_options, str(base["lifecycle_state"])),
        key="rule_lifecycle_state",
    )

    trigger_type = st.selectbox("Trigger", ["transaction", "schedule", "manual"], index=["transaction", "schedule", "manual"].index(base["trigger_type"]), key="rule_trigger_type")
    trigger_config_text = st.text_area("Trigger config JSON", value=base["trigger_config"], height=100, key="rule_trigger_config")
    conditions_text = st.text_area("Conditions JSON list", value=base["conditions"], height=120, key="rule_conditions")
    actions_text = st.text_area("Actions JSON list", value=base["actions"], height=140, key="rule_actions")

    change_note = st.text_input("Change note (optional)", value="", help="Saved to version history.")

    save_col, promote_col, sim_col, del_col = st.columns(4)
    if save_col.button("Save Rule", type="primary"):
        trigger_config = _load_json("trigger_config", trigger_config_text, dict)
        conditions = _load_json("conditions", conditions_text, list)
        actions = _load_json("actions", actions_text, list)
        if trigger_config is not None and conditions is not None and actions is not None and name.strip():
            target = picked or models.Rule(name=name.strip())
            if not picked:
                session.add(target)
                session.flush()
            target.name = name.strip()
            target.priority = int(priority)
            target.trigger_type = trigger_type
            target.trigger_config = trigger_config
            target.conditions = conditions
            target.actions = actions
            target.enabled = enabled
            target.lifecycle_state = lifecycle_state
            snapshot_rule(session, target, change_note=change_note or "Saved from Rule Builder")
            session.commit()
            st.success(f"Saved rule: {target.name}")
            st.rerun()

    if promote_col.button("Promote to Active"):
        if not picked:
            st.info("Select a saved rule first.")
        else:
            target = session.get(models.Rule, picked.id)
            target.lifecycle_state = "active"
            target.enabled = True
            snapshot_rule(session, target, change_note=change_note or "Promoted to active")
            session.commit()
            st.success("Rule promoted to active.")
            st.rerun()

    if sim_col.button("Simulate on latest transaction"):
        rule = session.get(models.Rule, picked.id) if picked else None
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
        target = session.get(models.Rule, picked.id)
        if target:
            session.delete(target)
            session.commit()
            st.success("Rule deleted")
            st.rerun()

    st.subheader("Version History")
    if picked:
        versions = list_rule_versions(session, picked.id)
        st.dataframe(
            [
                {
                    "id": v.id,
                    "version": v.version_number,
                    "name": v.name,
                    "state": v.lifecycle_state,
                    "enabled": v.enabled,
                    "rollback": v.is_rollback,
                    "note": v.change_note,
                    "created_at": v.created_at,
                }
                for v in versions
            ],
            use_container_width=True,
        )
        if len(versions) >= 2:
            col1, col2 = st.columns(2)
            lhs = col1.selectbox("Diff from", versions, format_func=lambda v: f"v{v.version_number} ({v.created_at})", key="diff_lhs")
            rhs = col2.selectbox("Diff to", versions, format_func=lambda v: f"v{v.version_number} ({v.created_at})", key="diff_rhs")
            st.code(version_diff(lhs, rhs) or "No diff")

        rollback_version = st.selectbox(
            "Rollback target",
            versions,
            format_func=lambda v: f"v{v.version_number} - {v.change_note or v.name}",
            key="rollback_target",
        ) if versions else None
        if rollback_version and st.button("Rollback to selected version"):
            target = session.get(models.Rule, picked.id)
            rollback_to_version(session, target, rollback_version)
            session.commit()
            st.success(f"Rolled back to v{rollback_version.version_number}")
            st.rerun()
    else:
        st.info("Select a rule to view version history and rollback controls.")

    st.subheader("All Rules")
    st.dataframe(
        [
            {
                "id": r.id,
                "name": r.name,
                "priority": r.priority,
                "trigger": r.trigger_type,
                "enabled": r.enabled,
                "state": r.lifecycle_state,
                "created_at": r.created_at,
            }
            for r in rules
        ],
        use_container_width=True,
    )
