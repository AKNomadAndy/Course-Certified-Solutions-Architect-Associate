from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from db import models
from services.explainability import (
    build_what_if_skip,
    build_why_recommendation,
    confidence_badge_for_rule,
)
from services.fx import convert_amount
from services.user_settings import get_or_create_user_settings


def sort_rules(rules: list[models.Rule]) -> list[models.Rule]:
    return sorted(rules, key=lambda r: (-r.priority, r.created_at, r.id))


def trigger_matches(rule: models.Rule, event: dict, tx: models.Transaction | None = None) -> bool:
    etype = event.get("type")
    if rule.trigger_type == "manual":
        return etype == "manual"
    if rule.trigger_type == "transaction":
        if etype != "transaction" or not tx:
            return False
        contains = rule.trigger_config.get("description_contains")
        wanted_currency = (rule.trigger_config.get("currency") or "").upper()
        currency_ok = True if not wanted_currency else (tx.currency or "").upper() == wanted_currency
        contains_ok = contains.lower() in tx.description.lower() if contains else True
        return contains_ok and currency_ok
    if rule.trigger_type == "schedule":
        return etype == "schedule"
    return False


def check_condition(
    session,
    condition: dict,
    tx: models.Transaction | None,
    latest_balance: float | None,
    base_currency: str = "USD",
    now: datetime | None = None,
) -> tuple[bool, str]:
    now = now or datetime.utcnow()
    ctype = condition.get("type")
    if ctype == "amount_gte":
        tx_amount = convert_amount(session, tx.amount, tx.currency or base_currency, base_currency) if tx else None
        ok = tx is not None and float(tx_amount) >= float(condition["value"])
        return ok, f"amount {round(float(tx_amount), 2) if tx else 'n/a'} {base_currency} >= {condition['value']}"
    if ctype == "amount_lte":
        tx_amount = convert_amount(session, tx.amount, tx.currency or base_currency, base_currency) if tx else None
        ok = tx is not None and float(tx_amount) <= float(condition["value"])
        return ok, f"amount {round(float(tx_amount), 2) if tx else 'n/a'} {base_currency} <= {condition['value']}"
    if ctype == "currency_eq":
        tx_ccy = (tx.currency or base_currency).upper() if tx else "n/a"
        expected = str(condition.get("value", "")).upper()
        ok = tx is not None and tx_ccy == expected
        return ok, f"currency {tx_ccy} == {expected}"
    if ctype == "day_of_month_eq":
        ok = now.day == int(condition["value"])
        return ok, f"day {now.day} == {condition['value']}"
    if ctype == "balance_gte":
        ok = latest_balance is not None and latest_balance >= float(condition["value"])
        return ok, f"balance {latest_balance} >= {condition['value']}"
    return False, "unknown condition"


def _risk_spike_score(session) -> float:
    txs = session.scalars(
        select(models.Transaction).order_by(models.Transaction.date.desc()).limit(30)
    ).all()
    if len(txs) < 10:
        return 0.0

    negatives = [abs(float(t.amount)) for t in txs if float(t.amount) < 0]
    if not negatives:
        return 0.0

    recent = negatives[:7] if len(negatives) >= 7 else negatives
    baseline = negatives[7:] if len(negatives) > 7 else negatives
    recent_avg = sum(recent) / max(1, len(recent))
    baseline_avg = sum(baseline) / max(1, len(baseline))
    if baseline_avg <= 0:
        return 0.0
    score = (recent_avg - baseline_avg) / baseline_avg
    return max(0.0, min(1.0, float(score)))


def _category_daily_total(session, tx: models.Transaction | None) -> float:
    if not tx or not tx.category or not tx.date:
        return 0.0
    total = session.scalar(
        select(func.sum(func.abs(models.Transaction.amount))).where(
            models.Transaction.date == tx.date,
            models.Transaction.category == tx.category,
            models.Transaction.amount < 0,
        )
    )
    return float(total or 0.0)


def _execute_actions(
    session,
    rule: models.Rule,
    tx: models.Transaction | None,
    latest_balance: float | None,
    execution_mode: str,
    min_checking_floor: float,
):
    allocated = 0.0
    trace_actions = []
    action_rows = []
    final_status = "completed"

    for idx, action in enumerate(rule.actions):
        kind = action["type"]
        status = "success"
        message = ""
        payload: dict = {}

        if kind == "allocate_fixed":
            amount = float(action["amount"])
            up_to = action.get("up_to_available", False)
            available_total = max(0.0, (latest_balance or 0.0) - min_checking_floor)
            available = available_total - allocated
            actual = min(amount, max(0.0, available)) if up_to else amount
            if up_to and actual <= 0:
                status = "failed"
                message = "No available funds above floor"
            else:
                # Non-up_to allocations must also respect floor for auto-apply mode.
                projected_balance = (latest_balance or 0.0) - (allocated + actual)
                if execution_mode == "auto_apply_internal_allocations" and projected_balance < min_checking_floor:
                    status = "failed"
                    message = "Guardrail blocked: minimum checking floor would be breached"
                else:
                    allocated += actual
                    pod_id = int(action.get("pod_id", 0)) if action.get("pod_id") is not None else None
                    if execution_mode == "auto_apply_internal_allocations" and pod_id:
                        pod = session.get(models.Pod, pod_id)
                        if pod:
                            pod.current_balance = float(pod.current_balance or 0.0) + actual
                    message = f"Allocated {actual} to pod {action['pod_id']}"
                    payload = {"allocated": actual, "pod_id": action.get("pod_id")}
        elif kind == "allocate_percent":
            base = abs(tx.amount) if tx else 0.0
            raw = base * (float(action["percent"]) / 100)
            amount = round(raw, 2)
            projected_balance = (latest_balance or 0.0) - (allocated + amount)
            if execution_mode == "auto_apply_internal_allocations" and projected_balance < min_checking_floor:
                status = "failed"
                message = "Guardrail blocked: minimum checking floor would be breached"
            else:
                allocated += amount
                leftover = round(base - amount, 2)
                pod_id = int(action.get("pod_id", 0)) if action.get("pod_id") is not None else None
                if execution_mode == "auto_apply_internal_allocations" and pod_id:
                    pod = session.get(models.Pod, pod_id)
                    if pod:
                        pod.current_balance = float(pod.current_balance or 0.0) + amount
                message = f"Allocated {amount} ({action['percent']}%), leftover {leftover}"
                payload = {"allocated": amount, "leftover": leftover, "pod_id": action.get("pod_id")}
        elif kind == "top_up_pod":
            pod = session.get(models.Pod, int(action["pod_id"]))
            target = float(action["target"])
            need = max(target - (pod.current_balance if pod else 0), 0)
            projected_balance = (latest_balance or 0.0) - (allocated + need)
            if execution_mode == "auto_apply_internal_allocations" and projected_balance < min_checking_floor:
                status = "failed"
                message = "Guardrail blocked: minimum checking floor would be breached"
            else:
                allocated += need
                if execution_mode == "auto_apply_internal_allocations" and pod:
                    pod.current_balance = float(pod.current_balance or 0.0) + need
                message = f"Top up suggestion {need}"
                payload = {"allocated": need, "pod_id": action.get("pod_id")}
        elif kind == "liability_suggestion":
            message = "Task suggested"
            payload = {
                "task_title": action.get("title", "Pay liability"),
                "task_note": action.get("note"),
            }
        else:
            status = "failed"
            message = f"Unsupported action {kind}"

        trace_actions.append({"action": action, "status": status, "message": message, "payload": payload})
        action_rows.append((idx, status, message, payload))
        if status == "failed":
            final_status = "action_failed"
            break

    return final_status, trace_actions, action_rows


def run_rule(session, rule: models.Rule, event: dict, tx: models.Transaction | None = None, dry_run: bool = True):
    existing = session.scalar(
        select(models.Run).where(models.Run.rule_id == rule.id, models.Run.event_key == event["event_key"])
    )
    if existing:
        return existing, []

    settings = get_or_create_user_settings(session)
    base_currency = settings.base_currency or "USD"
    execution_mode = "suggest_only" if dry_run else (settings.autopilot_mode or "suggest_only")
    min_floor = float(settings.guardrail_min_checking_floor or 0.0)
    category_daily_cap = settings.guardrail_max_category_daily
    risk_threshold = float(settings.guardrail_risk_pause_threshold or 0.6)

    trace: dict = {
        "trigger": False,
        "conditions": [],
        "actions": [],
        "dry_run": dry_run,
        "execution_mode": execution_mode,
        "guardrails": {},
        "rule_fired": {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "priority": rule.priority,
            "base_currency": base_currency,
            "trigger_type": rule.trigger_type,
            "trigger_config": rule.trigger_config,
        },
    }

    latest_snapshot = session.scalar(select(models.BalanceSnapshot).order_by(models.BalanceSnapshot.snapshot_at.desc()))
    latest_balance = latest_snapshot.balance if latest_snapshot else None

    if not trigger_matches(rule, event, tx):
        trace["explainability"] = {
            "why_recommendation": build_why_recommendation(False, 0, 0, execution_mode),
            "what_if_skip": "No action to skip because no recommendation was produced.",
            "confidence_badge": "high",
        }
        run = models.Run(rule_id=rule.id, event_key=event["event_key"], status="skipped", trace=trace)
        session.add(run)
        session.commit()
        return run, []

    trace["trigger"] = True

    risk_score = _risk_spike_score(session)
    trace["guardrails"]["risk_spike_score"] = risk_score
    trace["guardrails"]["risk_pause_threshold"] = risk_threshold
    if not dry_run and risk_score >= risk_threshold:
        trace["guardrails"]["blocked"] = "risk_spike"
        trace["explainability"] = {
            "why_recommendation": build_why_recommendation(True, 0, 0, execution_mode),
            "what_if_skip": "Skipping is advised right now because risk guardrails paused execution.",
            "confidence_badge": confidence_badge_for_rule("guardrail_blocked", risk_spike_score=risk_score),
        }
        run = models.Run(rule_id=rule.id, event_key=event["event_key"], status="guardrail_blocked", trace=trace)
        session.add(run)
        session.commit()
        return run, []

    if not dry_run and category_daily_cap is not None and tx and tx.amount < 0:
        category_spend = _category_daily_total(session, tx)
        trace["guardrails"]["category_daily_total"] = category_spend
        trace["guardrails"]["category_daily_cap"] = float(category_daily_cap)
        if category_spend > float(category_daily_cap):
            trace["guardrails"]["blocked"] = "category_daily_cap"
            trace["explainability"] = {
                "why_recommendation": build_why_recommendation(True, 0, 0, execution_mode),
                "what_if_skip": "Skipping is advised because category daily spend exceeded your cap.",
                "confidence_badge": confidence_badge_for_rule("guardrail_blocked", risk_spike_score=risk_score),
            }
            run = models.Run(rule_id=rule.id, event_key=event["event_key"], status="guardrail_blocked", trace=trace)
            session.add(run)
            session.commit()
            return run, []

    for condition in rule.conditions:
        ok, message = check_condition(session, condition, tx, latest_balance, base_currency=base_currency)
        trace["conditions"].append({"condition": condition, "ok": ok, "message": message})
        if not ok:
            trace["explainability"] = {
                "why_recommendation": build_why_recommendation(True, len(trace["conditions"]), 0, execution_mode),
                "what_if_skip": "No actions executed because conditions did not pass.",
                "confidence_badge": confidence_badge_for_rule("condition_failed", risk_spike_score=risk_score),
            }
            run = models.Run(rule_id=rule.id, event_key=event["event_key"], status="condition_failed", trace=trace)
            session.add(run)
            session.commit()
            return run, []

    status, trace_actions, action_rows = _execute_actions(
        session,
        rule,
        tx,
        latest_balance,
        execution_mode=execution_mode,
        min_checking_floor=min_floor,
    )
    trace["actions"] = trace_actions
    trace["explainability"] = {
        "why_recommendation": build_why_recommendation(True, len(trace["conditions"]), len(trace_actions), execution_mode),
        "what_if_skip": build_what_if_skip([p for _, _, _, p in action_rows]),
        "confidence_badge": confidence_badge_for_rule(status, risk_spike_score=risk_score),
    }

    run = models.Run(rule_id=rule.id, event_key=event["event_key"], status=status, trace=trace)
    session.add(run)
    session.flush()

    results = []
    for idx, a_status, message, payload in action_rows:
        result = models.ActionResult(run_id=run.id, action_index=idx, status=a_status, message=message, payload=payload)
        session.add(result)
        results.append(result)

        should_create_task = not dry_run and execution_mode in {"auto_create_tasks", "auto_apply_internal_allocations"}
        if should_create_task and payload.get("task_title"):
            session.add(
                models.Task(
                    title=payload["task_title"],
                    task_type="liability_payment",
                    note=payload.get("task_note"),
                )
            )

    session.commit()
    return run, results


def evaluate_rules_for_event(session, event: dict, dry_run: bool = True):
    tx = None
    if event.get("transaction_id"):
        tx = session.get(models.Transaction, event["transaction_id"])

    rules = session.scalars(
        select(models.Rule).where(models.Rule.enabled == True, models.Rule.lifecycle_state == "active")
    ).all()  # noqa: E712
    ordered = sort_rules(rules)
    runs = []
    for rule in ordered:
        if trigger_matches(rule, event, tx):
            run, _ = run_rule(session, rule, event, tx=tx, dry_run=dry_run)
            runs.append(run)
    return runs


def scheduler_tick(session):
    event = {"type": "schedule", "event_key": f"schedule:{datetime.utcnow().strftime('%Y%m%d%H')}"}
    return evaluate_rules_for_event(session, event, dry_run=False)
