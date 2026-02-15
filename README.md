# FlowLedger

FlowLedger is a personal-only money router MVP built as an original, dry-run-first product. It imports read-only transaction data, evaluates deterministic routing rules, simulates outcomes, and generates manual action checklists.

## PRD (Concise)

### MVP
- Single-user Streamlit monolith (no auth)
- Accounts, Pods (virtual buckets), Liabilities, Income & Bills planner
- Read-only CSV transaction import (single or multiple files) + manual balances
- Money Map view (streamlit-agraph, then PyVis fallback, then built-in SVG graph, then table fallback)
- Deterministic rules engine: Trigger -> Conditions -> ordered Actions (stop-on-failure)
- Simulator with trace over last N days (default 90) plus 30-day cashflow projection chart
- Activity feed with trend charts + audit export CSV
- Next Actions checklist (manual tasks only) + bill task generation
- Demo Mode idempotent loader with seeded entities, 60+ tx, 8+ rules

### V1
- Better rule templates and richer condition builder UI
- Scheduled background tick via APScheduler in-app
- Better graph editing (inline edge/rule editing)

### V2
- Multi-currency controls
- Rule versioning and rollback snapshots
- Package split to API + frontend while keeping service layer unchanged

## Domain model (entities + examples)

```json
{
  "UserSettings": {"id": 1, "user_name": "Demo User", "base_currency": "USD"},
  "Account": {"id": 1, "name": "Main Checking", "type": "checking", "currency": "USD"},
  "Pod": {"id": 1, "name": "Essentials", "target_balance": 1000.0, "current_balance": 200.0},
  "Liability": {"id": 1, "name": "Travel Card", "statement_balance": 650.0, "min_due": 35.0, "due_date": null, "apr": null},
  "Transaction": {"id": 10, "date": "2026-01-10", "description": "Payroll Deposit", "amount": 2200.0, "account": "Main Checking"},
  "BalanceSnapshot": {"id": 1, "source_type": "account", "source_id": 1, "balance": 3400.0},
  "MoneyMapNode": {"id": 5, "node_type": "pod", "ref_id": 2, "label": "Goals"},
  "MoneyMapEdge": {"id": 2, "source_node_id": 1, "target_node_id": 5, "label": "auto-route"},
  "Rule": {"id": 1, "name": "Income to Essentials", "priority": 200, "trigger_type": "transaction", "trigger_config": {"description_contains": "Payroll"}},
  "Run": {"id": 44, "rule_id": 1, "event_key": "tx:10", "status": "completed", "trace": {}},
  "ActionResult": {"id": 88, "run_id": 44, "action_index": 0, "status": "success", "message": "Allocated 1100.0 to pod 1"},
  "Error": {"id": 3, "run_id": 44, "message": "Unsupported action type", "details": {}},
  "Notification": {"id": 1, "message": "Demo loaded", "is_read": false},
  "Task": {"id": 12, "title": "Pay loan minimum", "task_type": "liability_payment", "status": "open"}
}
```

### Determinism
- Rule conflict order: `priority DESC`, then `created_at ASC`, then `rule_id ASC`
- Idempotency: unique (`rule_id`, `event_key`) on `Run`
- “Up to available”: latest snapshot for source minus amounts allocated earlier in same run

## Rules engine spec + pseudocode

```text
ingest_transactions(csv):
  read dataframe
  enforce required columns: date, description, amount
  normalize optional columns
  for each row:
    compute tx_hash
    skip if exists
    create transaction
    create event {event_key: "tx:<id>", transaction_id: id}
  return transactions/events

evaluate_rules(event):
  load enabled rules
  sort by priority desc, created_at asc, id asc
  for each rule:
    if trigger matches event:
      run_rule(rule, context)

run_rule(rule, context):
  if run(rule_id,event_key) exists -> return existing
  evaluate trigger
  evaluate all conditions as pure checks
  if any condition fails -> stop
  execute actions in order
  if an action fails -> stop-on-failure
  log trace + action results
  return run + results

simulate_rule(rule, events_range):
  for event in range:
    run_rule in dry-run mode with unique simulation event keys
    collect trigger/condition/action trace
  summarize allocations, tasks, warnings

scheduler_tick():
  build schedule event key for current interval
  evaluate scheduled rules (dry-run)
  generate tasks for liability/payment suggestions
```

## Streamlit UX map

- **Money Map**
  - Graph canvas using `streamlit-agraph`
  - Fallback #1: embedded PyVis interactive graph
  - Fallback #2: built-in SVG graph (no extra deps)
  - Fallback #3: node table + adjacency list
  - Quick create for account/pod/liability + map nodes
- **Income & Bills**
  - Enter monthly income and pay frequency
  - Add recurring bills with due date, category, autopay
  - Visualize due-day load + category mix + remaining cash
  - Generate current-month bill tasks
- **Rule Builder**
  - Trigger selector (transaction/schedule/manual)
  - JSON-based condition/action wizard for MVP speed
  - Buttons: Simulate, Enable/Disable, Save draft
- **Simulator**
  - Rule picker + lookback days (default 90)
  - Step trace and summary (allocations/tasks/warnings)
- **Activity**
  - Run timeline, trace view, CSV export
- **Next Actions**
  - Manual checklist with mark done + note + reference id
- **Settings**
  - CSV import
  - Idempotent “Load Demo Data”
  - CSV defaults documented in UI

## Repo scaffold

```text
app.py
db/
  engine.py
  models.py
schemas/
  domain.py
services/
  repositories.py
  imports.py
  rules_engine.py
  simulator.py
  tasks.py
  demo_loader.py
ui/pages/
  map_view.py
  rules.py
  simulate.py
  activity.py
  tasks_view.py
  settings.py
data/
  demo_transactions.csv
  generate_demo_data.py
tests/
  conftest.py
  test_rules_engine.py
  test_demo_loader.py
```

## Defaults
- UI layout: left sidebar nav + wide pages + top-level title
- CSV defaults: required `date, description, amount`; optional `account, category, merchant, currency`; also supports card statement schema (`trans_date`, `amount_usd`, `card_last4`, etc.)
- Rule priority default: 100
- Simulator default lookback: 90 days
- Percent rounding: `round(value, 2)`

## How to run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Tests

```bash
pytest -q
```

## Notes
- This MVP never initiates real money movement.
- All outputs are dry-run simulation and manual action suggestions.
