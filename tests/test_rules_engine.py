from datetime import date

from db import models
from services.rules_engine import check_condition, run_rule, trigger_matches


def seed_rule(session, actions=None, conditions=None):
    rule = models.Rule(
        name="R1",
        priority=100,
        trigger_type="transaction",
        trigger_config={"description_contains": "Payroll"},
        actions=actions or [{"type": "allocate_fixed", "pod_id": 1, "amount": 50, "up_to_available": True}],
        conditions=conditions or [{"type": "amount_gte", "value": 100}],
    )
    session.add(rule)
    session.add(models.BalanceSnapshot(source_type="account", source_id=1, balance=40))
    session.add(models.Pod(name="Essentials"))
    tx = models.Transaction(tx_hash="x1", date=date(2024, 1, 1), description="Payroll Deposit", amount=200)
    session.add(tx)
    session.commit()
    return rule, tx


def test_trigger_matching(session):
    rule, tx = seed_rule(session)
    assert trigger_matches(rule, {"type": "transaction"}, tx)


def test_condition_eval(session):
    tx = models.Transaction(date=date(2024, 1, 1), description="x", amount=12, tx_hash="z")
    ok, _ = check_condition({"type": "amount_gte", "value": 10}, tx, None)
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
    # balance 40 with 66 already allocated means up_to should clamp to 0 and fail
    assert results[1].status == "failed"


def test_idempotent_run_creation(session):
    rule, tx = seed_rule(session, conditions=[])
    run1, _ = run_rule(session, rule, {"event_key": "same", "type": "transaction"}, tx)
    run2, _ = run_rule(session, rule, {"event_key": "same", "type": "transaction"}, tx)
    assert run1.id == run2.id
