from __future__ import annotations

from datetime import date, timedelta
import csv
from pathlib import Path
from sqlalchemy import select

from db import models
from services.imports import ingest_transactions


SAMPLE_RULES = [
    {
        "name": "Income to Essentials",
        "priority": 200,
        "trigger_type": "transaction",
        "trigger_config": {"description_contains": "Payroll"},
        "conditions": [{"type": "amount_gte", "value": 1000}],
        "actions": [{"type": "allocate_percent", "pod_id": 1, "percent": 50}],
    },
    {
        "name": "Income to Goals",
        "priority": 180,
        "trigger_type": "transaction",
        "trigger_config": {"description_contains": "Payroll"},
        "conditions": [{"type": "amount_gte", "value": 1000}],
        "actions": [{"type": "allocate_percent", "pod_id": 2, "percent": 20}],
    },
    {
        "name": "Top up Emergency",
        "priority": 170,
        "trigger_type": "schedule",
        "trigger_config": {"freq": "weekly"},
        "conditions": [{"type": "day_of_month_eq", "value": 15}],
        "actions": [{"type": "top_up_pod", "pod_id": 3, "target": 2000}],
    },
    {
        "name": "Small expense cap",
        "priority": 90,
        "trigger_type": "transaction",
        "trigger_config": {"description_contains": "Coffee"},
        "conditions": [{"type": "amount_lte", "value": -3}],
        "actions": [{"type": "allocate_fixed", "pod_id": 4, "amount": 5, "up_to_available": True}],
    },
    {
        "name": "Loan payment checklist",
        "priority": 210,
        "trigger_type": "schedule",
        "trigger_config": {"freq": "monthly"},
        "conditions": [{"type": "balance_gte", "value": 300}],
        "actions": [{"type": "liability_suggestion", "title": "Pay loan minimum"}],
    },
    {
        "name": "Manual sweep",
        "priority": 100,
        "trigger_type": "manual",
        "trigger_config": {},
        "conditions": [],
        "actions": [{"type": "allocate_fixed", "pod_id": 2, "amount": 25, "up_to_available": True}],
    },
    {
        "name": "Biweekly reserve",
        "priority": 140,
        "trigger_type": "schedule",
        "trigger_config": {"freq": "biweekly"},
        "conditions": [],
        "actions": [{"type": "allocate_fixed", "pod_id": 1, "amount": 80, "up_to_available": True}],
    },
    {
        "name": "Daily debt nudge",
        "priority": 110,
        "trigger_type": "schedule",
        "trigger_config": {"freq": "daily"},
        "conditions": [{"type": "balance_gte", "value": 100}],
        "actions": [{"type": "liability_suggestion", "title": "Pay extra toward credit line"}],
    },
]


def generate_demo_csv(path: Path):
    if path.exists():
        return
    start = date.today() - timedelta(days=92)
    merchants = ["Grocer", "Coffee Spot", "Utilities", "Transit", "Payroll", "Rent"]
    rows = []
    for i in range(66):
        d = start + timedelta(days=i)
        if i % 14 == 0:
            desc, amt, cat = "Payroll Deposit", 2200.00, "Income"
        elif i % 30 == 0:
            desc, amt, cat = "Rent Payment", -1200.00, "Housing"
        else:
            merchant = merchants[i % len(merchants)]
            desc = f"{merchant} Purchase"
            amt = -round(10 + (i % 7) * 3.15, 2)
            cat = "Living"
        rows.append([d.isoformat(), desc, amt, "Main Checking", cat, desc.split()[0], "USD"])
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "description", "amount", "account", "category", "merchant", "currency"])
        writer.writerows(rows)


def load_demo_data(session, root_path: str = "."):
    settings = session.scalar(select(models.UserSettings))
    if not settings:
        session.add(models.UserSettings(user_name="Demo User", base_currency="USD"))

    accounts = [
        {"name": "Main Checking", "type": "checking", "currency": "USD"},
        {"name": "Rainy Savings", "type": "savings", "currency": "USD"},
        {"name": "Daily Cash", "type": "cash", "currency": "USD"},
    ]
    for a in accounts:
        if not session.scalar(select(models.Account).where(models.Account.name == a["name"])):
            session.add(models.Account(**a))

    pods = ["Essentials", "Goals", "Emergency", "Fun"]
    for p in pods:
        if not session.scalar(select(models.Pod).where(models.Pod.name == p)):
            session.add(models.Pod(name=p, target_balance=1000, current_balance=200))

    liabilities = [
        {"name": "Travel Card", "statement_balance": 650, "min_due": 35},
        {"name": "Student Loan", "statement_balance": 4200, "min_due": 110},
    ]
    for l in liabilities:
        if not session.scalar(select(models.Liability).where(models.Liability.name == l["name"])):
            session.add(models.Liability(**l))

    session.commit()

    for rule in SAMPLE_RULES:
        if not session.scalar(select(models.Rule).where(models.Rule.name == rule["name"])):
            session.add(models.Rule(**rule, enabled=True))

    if not session.scalar(select(models.BalanceSnapshot)):
        session.add(models.BalanceSnapshot(source_type="account", source_id=1, balance=3400))

    session.commit()

    path = Path(root_path) / "data" / "demo_transactions.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    generate_demo_csv(path)
    ingest_transactions(session, path)

    if session.scalar(select(models.MoneyMapNode).limit(1)):
        return
    for acct in session.scalars(select(models.Account)).all():
        session.add(models.MoneyMapNode(node_type="account", ref_id=acct.id, label=acct.name))
    for pod in session.scalars(select(models.Pod)).all():
        session.add(models.MoneyMapNode(node_type="pod", ref_id=pod.id, label=pod.name))
    for debt in session.scalars(select(models.Liability)).all():
        session.add(models.MoneyMapNode(node_type="liability", ref_id=debt.id, label=debt.name))
    session.commit()

    nodes = session.scalars(select(models.MoneyMapNode)).all()
    by_label = {n.label: n.id for n in nodes}
    edges = [
        ("Main Checking", "Essentials"),
        ("Main Checking", "Goals"),
        ("Main Checking", "Emergency"),
        ("Main Checking", "Travel Card"),
    ]
    for s, t in edges:
        exists = session.scalar(
            select(models.MoneyMapEdge).where(
                models.MoneyMapEdge.source_node_id == by_label[s], models.MoneyMapEdge.target_node_id == by_label[t]
            )
        )
        if not exists:
            session.add(models.MoneyMapEdge(source_node_id=by_label[s], target_node_id=by_label[t], label="auto-route"))
    session.commit()
