# FlowLedger

FlowLedger is a personal-only money router MVP built as an original, dry-run-first product. It imports read-only transaction data, evaluates deterministic routing rules, simulates outcomes, and generates manual action checklists.

## PRD (Concise)

### MVP
- Single-user Streamlit monolith (no auth), explicit personal-use profile settings
- Accounts, Pods (virtual buckets), Liabilities, Income & Bills planner
- Read-only CSV transaction import (single or multiple files) + manual balances
- Money Map view (streamlit-agraph, then PyVis fallback, then built-in SVG graph, then table fallback)
- Deterministic rules engine: Trigger -> Conditions -> ordered Actions (stop-on-failure)
- Simulator with trace over last N days (default 90) plus 30-day cashflow projection chart
- Cashflow Forecast page with hybrid deterministic + stochastic confidence bands (P10/P50/P90), overdraft probability, and safe-to-spend
- Activity feed with trend charts + audit export CSV
- Next Actions checklist (manual tasks only) + bill task generation
- Demo Mode idempotent loader with seeded entities, 60+ tx, 8+ rules

### V1
- ✅ Better rule templates and richer condition builder UI
- ✅ Scheduled background tick via APScheduler in-app
- ✅ Better graph editing (inline edge/rule editing)

### V2
- ✅ Multi-currency controls (FX table + forecast/rules-aware conversions)
- ✅ Historical FX snapshots + date-aware conversion + FX stress testing
- ✅ Portfolio exposure by currency + per-account/pod currency policies
- ✅ Rule versioning and rollback snapshots
- ✅ Personal autopilot modes with guardrails (suggest-only / auto-task / internal auto-apply)
- ✅ Explainability layer (why recommendation, what-if-skip, rule-fired inputs, confidence badges)
- ✅ Data quality ingestion moat (mapping memory, smart dedupe conflicts, categorization loop, quality/anomaly scoring)
- ✅ Scenario lab / decision simulator (debt, income, rent, FX what-if)
- Package split to API + frontend while keeping service layer unchanged

## Domain model (entities + examples)

```json
{
  "UserSettings": {"id": 1, "user_name": "Demo User", "base_currency": "USD"},
  "Account": {"id": 1, "name": "Main Checking", "type": "checking", "currency": "USD"},
  "Pod": {"id": 1, "name": "Essentials", "currency": "USD", "target_balance": 1000.0, "current_balance": 200.0},
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
  evaluate scheduled rules (autopilot mode applies)
  enforce guardrails: checking floor, category daily cap, risk spike pause
  generate tasks/internal pod allocations based on mode
```

## Streamlit UX map

- **Command Center**
  - Daily brief card (headline + today priorities)
  - Keyboard-first quick actions (command box + one-click actions)
  - Empty-state setup wizard for first-run onboarding
  - Today's top 3 decisions
  - This week's cash risk with balance-band chart
  - What changed since yesterday (cash/runs/tasks)
  - Why this recommendation + what-if-I-skip explainers
  - One-click weekly plan acceptance
- **Personal Intelligence**
  - Monthly retrospective (what improved vs worsened)
  - Recommendation acceptance tracking summary
  - Adaptive thresholds from risk tolerance + spend volatility + paycheck timing
  - Auto-generated monthly policy tweaks with one-click apply
- **Money Map**
  - Per-account and per-pod currency policies
  - Graph canvas using `streamlit-agraph`
  - Fallback #1: embedded PyVis interactive graph
  - Fallback #2: built-in SVG graph (no extra deps)
  - Fallback #3: node table + adjacency list
  - Quick create for account/pod/liability + map nodes
  - Inline edge create/edit/delete manager
  - Edit/delete accounts, pods, liabilities in-place (including Main Checking rename)
- **Income & Bills**
  - Enter monthly income and pay frequency with recurring toggle
  - Add bills with calendar due dates, recurring toggle, category, autopay
  - Mark bills paid with one click and reset paid flags
  - Set next pay date + current checking amount
  - Visual calendar timeline of upcoming income and bills
  - Clean cash-runway projection (4/8/12-week balances + shortfall warning date)
  - Upcoming-bills table with due countdown for easier payment planning
  - Visualize due-day load + category mix + remaining cash
  - Generate current-month bill tasks
  - One-click load of your full provided bill + debt list
  - One-click load of your complete personal workspace across pages (map/rules/activity/planner)
  - Generate debt reduction/payment plan from liabilities + remaining cash
  - View debt payoff schedule projection with monthly trend and interest summary
- **Rule Builder**
  - Trigger selector (transaction/schedule/manual)
  - JSON-based condition/action wizard + quick templates + no-code helper
  - Currency-aware rule conditions/triggers (`currency_eq`, optional trigger currency)
  - Clean editor with create/update/delete + enabled toggle + simulate latest transaction
- **Simulator**
  - Rule picker + lookback days (default 90)
  - Step trace and summary (allocations/tasks/warnings)
- **Scenario Lab**
  - If I pay extra debt monthly
  - If income drops by X%
  - If rent increases in month N
  - If EURUSD moves to target X
  - One-click accept scenario to task
- **Cashflow Forecast**
  - Deterministic schedule from bills + income
  - Stochastic remainder from historical daily behavior
  - P10/P50/P90 balance bands, overdraft risk, and safe-to-spend metric
  - Forecast currency selector with FX-aware stochastic conversion
  - Historical FX snapshot-aware backtesting + +/- shock stress table
  - Forecast confidence badge + explainers
- **Health**
  - Scheduler heartbeat and last scheduled-run status
  - Stale-data warnings (scheduler/import freshness)
  - Local reliability summary for open tasks and import quality
- **Activity**
  - Run timeline, trace view, CSV export
  - Human-readable explanation, skip-impact summary, rule-fired context, confidence badge
- **Next Actions**
  - Manual checklist with mark done + note + reference id
- **Settings**
  - Encrypted local backup/export + restore
  - Automatic DB snapshots before imports/demo-load and pre-restore
  - Historical FX snapshot management
  - Portfolio currency exposure table
  - Import mapping memory by export format
  - Smart dedupe conflict resolver table
  - Merchant→category feedback loop
  - Import quality score + anomaly detection
  - Personal profile + base currency
  - Personal autopilot modes (suggest only / auto-create tasks / auto-apply internal pod allocations)
  - Guardrails: minimum checking floor, max daily category spend, risk-spike pause threshold
  - FX rates table management for personal multi-currency planning
  - Multi-file CSV import + idempotent demo loader
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
  backup.py
  health.py
  repositories.py
  imports.py
  rules_engine.py
  simulator.py
  tasks.py
  demo_loader.py
  personal_intelligence.py
ui/pages/
  intelligence.py
  health.py
  map_view.py
  rules.py
  simulate.py
  activity.py
  tasks_view.py
  settings.py
  command_center.py
data/
  demo_transactions.csv
  generate_demo_data.py
tests/
  conftest.py
  test_rules_engine.py
  test_demo_loader.py
```

## Defaults
- UI layout: left sidebar nav + quick-navigation buttons + wide pages + top-level title
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
- Personal-use mode is intentional: one local profile, no multi-tenant workflow, and local SQLite state.
- This MVP never initiates real money movement.
- Outputs support personal autopilot modes with guardrails; no external money movement is ever initiated.


## One-command disaster recovery

```bash
python scripts/disaster_recovery.py --backup latest --passphrase "<your-passphrase>"
```
