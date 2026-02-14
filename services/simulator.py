from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy import select

from db import models
from schemas.domain import SimulationReport
from services.rules_engine import run_rule


def simulate_rule(session, rule_id: int, days: int = 90) -> SimulationReport:
    rule = session.get(models.Rule, rule_id)
    start_date = datetime.utcnow().date() - timedelta(days=days)
    txs = session.scalars(select(models.Transaction).where(models.Transaction.date >= start_date).order_by(models.Transaction.date)).all()
    traces = []
    total_allocated = {}
    tasks_created = 0
    warnings = []

    for tx in txs:
        event = {"type": "transaction", "event_key": f"simulate:{rule_id}:{tx.id}", "transaction_id": tx.id}
        run, results = run_rule(session, rule, event, tx=tx, dry_run=True)
        traces.append({"transaction_id": tx.id, "status": run.status, "trace": run.trace})
        for res in results:
            allocated = res.payload.get("allocated", 0)
            pod_id = res.payload.get("pod_id", "unknown")
            total_allocated[pod_id] = total_allocated.get(pod_id, 0) + allocated
            if res.payload.get("task_title"):
                tasks_created += 1
        if run.status in {"action_failed", "condition_failed"}:
            warnings.append(f"Run {run.id} ended with {run.status}")

    return SimulationReport(
        rule_name=rule.name,
        traces=traces,
        summary={"totals_allocated_per_pod": total_allocated, "tasks_created": tasks_created, "warnings": warnings},
    )
