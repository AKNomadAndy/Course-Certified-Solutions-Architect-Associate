from __future__ import annotations

from datetime import datetime
from sqlalchemy import select
from db import models


def sort_rules(rules: list[models.Rule]) -> list[models.Rule]:
    return sorted(rules, key=lambda r: (-r.priority, r.created_at, r.id))


def trigger_matches(rule: models.Rule, event: dict, tx: models.Transaction | None = None) -> bool:
    if rule.trigger_type == "manual":
        return event.get("type") == "manual"
    if rule.trigger_type == "transaction":
        if not tx:
            return False
        contains = rule.trigger_config.get("description_contains")
        return contains.lower() in tx.description.lower() if contains else True
    if rule.trigger_type == "schedule":
        return event.get("type") == "schedule"
    return False


def check_condition(condition: dict, tx: models.Transaction | None, latest_balance: float | None, now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.utcnow()
    ctype = condition.get("type")
    if ctype == "amount_gte":
        ok = tx is not None and tx.amount >= float(condition["value"])
        return ok, f"amount {tx.amount if tx else 'n/a'} >= {condition['value']}"
    if ctype == "amount_lte":
        ok = tx is not None and tx.amount <= float(condition["value"])
        return ok, f"amount {tx.amount if tx else 'n/a'} <= {condition['value']}"
    if ctype == "day_of_month_eq":
        ok = now.day == int(condition["value"])
        return ok, f"day {now.day} == {condition['value']}"
    if ctype == "balance_gte":
        ok = latest_balance is not None and latest_balance >= float(condition["value"])
        return ok, f"balance {latest_balance} >= {condition['value']}"
    return False, "unknown condition"


def run_rule(session, rule: models.Rule, event: dict, tx: models.Transaction | None = None, dry_run: bool = True):
    existing = session.scalar(select(models.Run).where(models.Run.rule_id == rule.id, models.Run.event_key == event["event_key"]))
    if existing:
        return existing, []

    trace = {"trigger": False, "conditions": [], "actions": []}
    latest_snapshot = session.scalar(select(models.BalanceSnapshot).order_by(models.BalanceSnapshot.snapshot_at.desc()))
    latest_balance = latest_snapshot.balance if latest_snapshot else None

    if not trigger_matches(rule, event, tx):
        trace["trigger"] = False
        run = models.Run(rule_id=rule.id, event_key=event["event_key"], status="skipped", trace=trace)
        session.add(run)
        session.commit()
        return run, []

    trace["trigger"] = True
    for condition in rule.conditions:
        ok, message = check_condition(condition, tx, latest_balance)
        trace["conditions"].append({"condition": condition, "ok": ok, "message": message})
        if not ok:
            run = models.Run(rule_id=rule.id, event_key=event["event_key"], status="condition_failed", trace=trace)
            session.add(run)
            session.commit()
            return run, []

    run = models.Run(rule_id=rule.id, event_key=event["event_key"], status="completed", trace=trace)
    session.add(run)
    session.flush()

    allocated = 0.0
    results = []
    for idx, action in enumerate(rule.actions):
        kind = action["type"]
        status = "success"
        message = ""
        payload = {}
        if kind == "allocate_fixed":
            amount = float(action["amount"])
            up_to = action.get("up_to_available", False)
            available = (latest_balance or 0) - allocated
            actual = min(amount, max(0.0, available)) if up_to else amount
            if up_to and actual <= 0:
                status = "failed"
                message = "No available funds"
            else:
                allocated += actual
                message = f"Allocated {actual} to pod {action['pod_id']}"
                payload = {"allocated": actual}
        elif kind == "allocate_percent":
            base = abs(tx.amount) if tx else 0
            raw = base * (float(action["percent"]) / 100)
            amount = round(raw, 2)
            allocated += amount
            leftover = round(base - amount, 2)
            message = f"Allocated {amount} ({action['percent']}%), leftover {leftover}"
            payload = {"allocated": amount, "leftover": leftover}
        elif kind == "top_up_pod":
            pod = session.get(models.Pod, int(action["pod_id"]))
            target = float(action["target"])
            need = max(target - (pod.current_balance if pod else 0), 0)
            allocated += need
            message = f"Top up suggestion {need}"
            payload = {"allocated": need}
        elif kind == "liability_suggestion":
            task = models.Task(title=action.get("title", "Pay liability"), task_type="liability_payment", note=action.get("note"))
            session.add(task)
            message = "Task created"
            payload = {"task_title": task.title}
        else:
            status = "failed"
            message = f"Unsupported action {kind}"

        result = models.ActionResult(run_id=run.id, action_index=idx, status=status, message=message, payload=payload)
        session.add(result)
        trace["actions"].append({"action": action, "status": status, "message": message})
        results.append(result)

        if status == "failed":
            run.status = "action_failed"
            break

    run.trace = trace
    session.commit()
    return run, results


def evaluate_rules_for_event(session, event: dict):
    tx = None
    if event.get("transaction_id"):
        tx = session.get(models.Transaction, event["transaction_id"])
    rules = session.scalars(select(models.Rule).where(models.Rule.enabled == True)).all()  # noqa: E712
    ordered = sort_rules(rules)
    runs = []
    for rule in ordered:
        if trigger_matches(rule, event, tx):
            run, _ = run_rule(session, rule, event, tx=tx, dry_run=True)
            runs.append(run)
    return runs


def scheduler_tick(session):
    event = {"type": "schedule", "event_key": f"schedule:{datetime.utcnow().strftime('%Y%m%d%H')}"}
    return evaluate_rules_for_event(session, event)
