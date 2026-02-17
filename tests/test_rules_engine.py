from datetime import date

from db import models
from services.rules_engine import check_condition, run_rule, trigger_matches
from services.user_settings import save_user_settings


def seed_rule(session, actions=None, conditions=None):
    rule = models.Rule(
        name="R1",
        priority=100,
        trigger_type="transaction",
        trigger_config={"description_contains": "Payroll"},
        actions=actions or [{"type": "allocate_fixed", "pod_id": 1, "amount": 50, "up_to_available": True}],
        conditions=conditions or [{"type": "amount_gte", "value": 100}],
        lifecycle_state="active",
    )
    session.add(rule)
    session.add(models.BalanceSnapshot(source_type="account", source_id=1, balance=40))
    session.add(models.Pod(name="Essentials", current_balance=0))
    tx = models.Transaction(tx_hash="x1", date=date(2024, 1, 1), description="Payroll Deposit", amount=200)
    session.add(tx)
    session.commit()
    return rule, tx


def test_trigger_matching(session):
    rule, tx = seed_rule(session)
    assert trigger_matches(rule, {"type": "transaction"}, tx)


def test_condition_eval(session):
    tx = models.Transaction(date=date(2024, 1, 1), description="x", amount=12, tx_hash="z")
    ok, _ = check_condition(session, {"type": "amount_gte", "value": 10}, tx, None)
    assert ok


def test_action_order_stop_on_failure(session):
    actions = [{"type": "unknown_action"}, {"type": "allocate_fixed", "pod_id": 1, "amount": 10}]
    rule, tx = seed_rule(session, actions=actions, conditions=[])
    run, results = run_rule(session, rule, {"event_key": "e1", "type": "transaction"}, tx)
    assert run.status == "action_failed"
    assert len(results) == 1


def test_percent_rounding_and_up_to(session):
    actions = [
        {"type": "allocate_percent", "pod_id": 1, "percent": 33},
        {"type": "allocate_fixed", "pod_id": 1, "amount": 50, "up_to_available": True},
    ]
    rule, tx = seed_rule(session, actions=actions, conditions=[])
    _, results = run_rule(session, rule, {"event_key": "e2", "type": "transaction"}, tx)
    assert round(results[0].payload["allocated"], 2) == 66.0
    assert results[1].status == "failed"


def test_idempotent_run_creation(session):
    rule, tx = seed_rule(session, conditions=[])
    run1, _ = run_rule(session, rule, {"event_key": "same", "type": "transaction"}, tx)
    run2, _ = run_rule(session, rule, {"event_key": "same", "type": "transaction"}, tx)
    assert run1.id == run2.id


def test_currency_condition(session):
    tx = models.Transaction(date=date(2024, 1, 1), description="x", amount=12, tx_hash="zc", currency="EUR")
    ok, _ = check_condition(session, {"type": "currency_eq", "value": "EUR"}, tx, None)
    assert ok


def test_autopilot_auto_create_tasks_mode(session):
    actions = [{"type": "liability_suggestion", "title": "Pay min due", "note": "Card payment"}]
    rule, tx = seed_rule(session, actions=actions, conditions=[])
    save_user_settings(session, "Personal User", "USD", autopilot_mode="auto_create_tasks")

    run_rule(session, rule, {"event_key": "ap-task", "type": "transaction"}, tx, dry_run=False)
    tasks = session.query(models.Task).all()
    assert len(tasks) == 1
    assert tasks[0].title == "Pay min due"


def test_autopilot_auto_apply_internal_allocations_updates_pod(session):
    actions = [{"type": "allocate_fixed", "pod_id": 1, "amount": 20, "up_to_available": True}]
    rule, tx = seed_rule(session, actions=actions, conditions=[])
    save_user_settings(
        session,
        "Personal User",
        "USD",
        autopilot_mode="auto_apply_internal_allocations",
        guardrail_min_checking_floor=0,
    )

    run_rule(session, rule, {"event_key": "ap-apply", "type": "transaction"}, tx, dry_run=False)
    pod = session.get(models.Pod, 1)
    assert round(float(pod.current_balance), 2) == 20.0


def test_autopilot_min_floor_blocks_allocation(session):
    actions = [{"type": "allocate_fixed", "pod_id": 1, "amount": 30, "up_to_available": False}]
    rule, tx = seed_rule(session, actions=actions, conditions=[])
    save_user_settings(
        session,
        "Personal User",
        "USD",
        autopilot_mode="auto_apply_internal_allocations",
        guardrail_min_checking_floor=35,
    )

    run, _ = run_rule(session, rule, {"event_key": "ap-floor", "type": "transaction"}, tx, dry_run=False)
    assert run.status == "action_failed"


def test_run_trace_includes_explainability_and_rule_fired(session):
    rule, tx = seed_rule(session, conditions=[])
    run, _ = run_rule(session, rule, {"event_key": "trace-1", "type": "transaction"}, tx)

    assert "explainability" in run.trace
    assert "rule_fired" in run.trace
    assert run.trace["rule_fired"]["base_currency"] == "USD"
    assert run.trace["explainability"]["confidence_badge"] in {"high", "medium", "low"}
