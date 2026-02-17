from __future__ import annotations

from datetime import date, datetime, timedelta
from hashlib import sha256

from sqlalchemy import select

from db import models
from services.planner import PERSONAL_BILL_PACK, load_personal_bill_and_debt_pack


PERSONAL_ACCOUNTS = [
    {"name": "Main Checking", "type": "checking", "currency": "USD", "institution": "Personal Bank"},
    {"name": "Capital One Card", "type": "credit", "currency": "USD", "institution": "Capital One"},
]

PERSONAL_PODS = [
    {"name": "Bills Buffer", "target_balance": 1500.0, "current_balance": 400.0, "currency": "USD"},
    {"name": "Debt Attack", "target_balance": 1000.0, "current_balance": 150.0, "currency": "USD"},
    {"name": "Emergency", "target_balance": 3000.0, "current_balance": 200.0, "currency": "USD"},
]

PERSONAL_RULES = [
    {
        "name": "Paycheck to Bills Buffer",
        "priority": 260,
        "trigger_type": "transaction",
        "trigger_config": {"description_contains": "Paycheck"},
        "conditions": [{"type": "amount_gte", "value": 1500}],
        "actions": [{"type": "allocate_percent", "pod_id": 1, "percent": 40}],
        "enabled": True,
        "lifecycle_state": "active",
    },
    {
        "name": "Paycheck to Debt Attack",
        "priority": 255,
        "trigger_type": "transaction",
        "trigger_config": {"description_contains": "Paycheck"},
        "conditions": [{"type": "amount_gte", "value": 1500}],
        "actions": [{"type": "allocate_fixed", "pod_id": 2, "amount": 300, "up_to_available": True}],
        "enabled": True,
        "lifecycle_state": "active",
    },
    {
        "name": "Monthly Debt Review Task",
        "priority": 210,
        "trigger_type": "schedule",
        "trigger_config": {"freq": "monthly"},
        "conditions": [],
        "actions": [{"type": "liability_suggestion", "title": "Review debt payoff and pay extra"}],
        "enabled": True,
        "lifecycle_state": "active",
    },
    {
        "name": "Cap non-essential spend",
        "priority": 180,
        "trigger_type": "transaction",
        "trigger_config": {"description_contains": "Google One"},
        "conditions": [{"type": "amount_lte", "value": -10}],
        "actions": [{"type": "liability_suggestion", "title": "Check discretionary subscriptions"}],
        "enabled": True,
        "lifecycle_state": "active",
    },
]


def _upsert_accounts_and_pods(session):
    accounts = []
    for item in PERSONAL_ACCOUNTS:
        row = session.scalar(select(models.Account).where(models.Account.name == item["name"]))
        if row:
            row.type = item["type"]
            row.currency = item["currency"]
            row.institution = item["institution"]
            row.is_active = True
        else:
            row = models.Account(**item)
            session.add(row)
        accounts.append(row)

    pods = []
    for item in PERSONAL_PODS:
        row = session.scalar(select(models.Pod).where(models.Pod.name == item["name"]))
        if row:
            row.target_balance = item["target_balance"]
            row.current_balance = item["current_balance"]
            row.currency = item["currency"]
        else:
            row = models.Pod(**item)
            session.add(row)
        pods.append(row)

    session.commit()
    return accounts, pods


def _sync_money_map(session):
    for account in session.scalars(select(models.Account)).all():
        node = session.scalar(
            select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "account", models.MoneyMapNode.ref_id == account.id)
        )
        if not node:
            session.add(models.MoneyMapNode(node_type="account", ref_id=account.id, label=account.name))
        else:
            node.label = account.name

    for pod in session.scalars(select(models.Pod)).all():
        node = session.scalar(select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "pod", models.MoneyMapNode.ref_id == pod.id))
        if not node:
            session.add(models.MoneyMapNode(node_type="pod", ref_id=pod.id, label=pod.name))
        else:
            node.label = pod.name

    for debt in session.scalars(select(models.Liability)).all():
        node = session.scalar(
            select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "liability", models.MoneyMapNode.ref_id == debt.id)
        )
        if not node:
            session.add(models.MoneyMapNode(node_type="liability", ref_id=debt.id, label=debt.name))
        else:
            node.label = debt.name

    session.commit()

    account_nodes = session.scalars(select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "account")).all()
    pod_nodes = session.scalars(select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "pod")).all()
    liability_nodes = session.scalars(select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "liability")).all()

    for a in account_nodes:
        for p in pod_nodes:
            edge = session.scalar(
                select(models.MoneyMapEdge).where(models.MoneyMapEdge.source_node_id == a.id, models.MoneyMapEdge.target_node_id == p.id)
            )
            if not edge:
                session.add(models.MoneyMapEdge(source_node_id=a.id, target_node_id=p.id, label="funds"))

    debt_target = pod_nodes[1] if len(pod_nodes) > 1 else (pod_nodes[0] if pod_nodes else None)
    if debt_target:
        for d in liability_nodes:
            edge = session.scalar(
                select(models.MoneyMapEdge).where(models.MoneyMapEdge.source_node_id == debt_target.id, models.MoneyMapEdge.target_node_id == d.id)
            )
            if not edge:
                session.add(models.MoneyMapEdge(source_node_id=debt_target.id, target_node_id=d.id, label="paydown"))
    session.commit()


def _seed_rules(session):
    for idx, rule in enumerate(PERSONAL_RULES):
        row = session.scalar(select(models.Rule).where(models.Rule.name == rule["name"]))
        payload = dict(rule)
        if row:
            row.priority = payload["priority"]
            row.trigger_type = payload["trigger_type"]
            row.trigger_config = payload["trigger_config"]
            row.conditions = payload["conditions"]
            row.actions = payload["actions"]
            row.enabled = payload["enabled"]
            row.lifecycle_state = payload["lifecycle_state"]
        else:
            # map first two rules to first two pods once pods exist
            if idx == 0:
                pod = session.scalar(select(models.Pod).where(models.Pod.name == "Bills Buffer"))
                if pod:
                    payload["actions"][0]["pod_id"] = pod.id
            if idx == 1:
                pod = session.scalar(select(models.Pod).where(models.Pod.name == "Debt Attack"))
                if pod:
                    payload["actions"][0]["pod_id"] = pod.id
            session.add(models.Rule(**payload))
    session.commit()


def _seed_transactions(session):
    today = date.today()
    start = today - timedelta(days=90)

    def add_tx(tx_date: date, desc: str, amount: float, category: str, account: str = "Main Checking", merchant: str | None = None):
        key = f"{tx_date.isoformat()}|{desc}|{amount}|{account}"
        tx_hash = sha256(key.encode("utf-8")).hexdigest()
        exists = session.scalar(select(models.Transaction).where(models.Transaction.tx_hash == tx_hash))
        if exists:
            return
        session.add(
            models.Transaction(
                tx_hash=tx_hash,
                date=tx_date,
                description=desc,
                amount=float(amount),
                account=account,
                category=category,
                merchant=merchant or desc,
                currency="USD",
            )
        )

    cursor = start
    while cursor <= today:
        # paychecks roughly 3rd and 17th
        if cursor.day in {3, 17}:
            add_tx(cursor, "Paycheck Deposit", 2030.45, "Income")
        # recurring bills based on user list (monthly)
        for bill in PERSONAL_BILL_PACK:
            if cursor.day == bill["due_day"]:
                add_tx(cursor, bill["name"], -float(bill["amount"]), bill["category"], account="Capital One Card")
        cursor += timedelta(days=1)

    # weekly groceries/transport/misc
    for i in range(13):
        d = start + timedelta(days=i * 7 + 2)
        add_tx(d, "Groceries", -75.0, "Groceries")
        add_tx(d + timedelta(days=1), "Transportation", -35.0, "Transportation")
        add_tx(d + timedelta(days=3), "Misc Spend", -25.0, "Misc")

    session.commit()


def _seed_activity(session):
    # create one open task + one run for activity/next actions visibility
    if not session.scalar(select(models.Task).where(models.Task.reference_id == "personal:weekly:seed")):
        session.add(
            models.Task(
                title="Review this week's debt attack amount",
                task_type="weekly_plan",
                note="Use surplus to target the next payoff debt.",
                reference_id="personal:weekly:seed",
            )
        )

    sample_rule = session.scalar(select(models.Rule).where(models.Rule.name == "Paycheck to Bills Buffer"))
    if sample_rule and not session.scalar(select(models.Run).where(models.Run.event_key == "personal-seed:run")):
        run = models.Run(rule_id=sample_rule.id, event_key="personal-seed:run", status="completed", trace={"seeded": True})
        session.add(run)
        session.flush()
        session.add(models.ActionResult(run_id=run.id, action_index=0, status="ok", message="Seeded sample action", payload={}))

    session.commit()


def load_full_personal_workspace(session):
    load_personal_bill_and_debt_pack(session)
    _upsert_accounts_and_pods(session)
    _sync_money_map(session)
    _seed_rules(session)
    _seed_transactions(session)
    _seed_activity(session)

    # baseline snapshot for checking
    checking = session.scalar(select(models.Account).where(models.Account.name == "Main Checking"))
    profile = session.scalar(select(models.IncomeProfile).where(models.IncomeProfile.name == "Primary Income"))
    if checking and profile:
        session.add(
            models.BalanceSnapshot(
                source_type="account",
                source_id=checking.id,
                balance=float(profile.current_checking_balance or 0.0),
            )
        )
        session.commit()

    return {
        "accounts": session.query(models.Account).count(),
        "pods": session.query(models.Pod).count(),
        "liabilities": session.query(models.Liability).count(),
        "rules": session.query(models.Rule).count(),
        "transactions": session.query(models.Transaction).count(),
    }
