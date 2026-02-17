from __future__ import annotations


def list_rule_templates():
    return {
        "Income to Essentials (50%)": {
            "trigger_type": "transaction",
            "trigger_config": {"description_contains": "Payroll"},
            "conditions": [{"type": "amount_gte", "value": 100}],
            "actions": [{"type": "allocate_percent", "pod_id": 1, "percent": 50}],
            "priority": 200,
        },
        "Large Expense Alert Task": {
            "trigger_type": "transaction",
            "trigger_config": {"description_contains": ""},
            "conditions": [{"type": "amount_lte", "value": -250}],
            "actions": [{"type": "liability_suggestion", "title": "Review large expense", "note": "Transaction exceeded threshold"}],
            "priority": 120,
        },
        "Monthly Debt Reminder": {
            "trigger_type": "schedule",
            "trigger_config": {"hour_utc": 9},
            "conditions": [],
            "actions": [{"type": "liability_suggestion", "title": "Review debt plan", "note": "Run debt payoff check this month"}],
            "priority": 110,
        },
    }


def build_template_payload(template_name: str, *, pod_id: int | None = None):
    templates = list_rule_templates()
    if template_name not in templates:
        raise KeyError(f"Unknown template: {template_name}")
    payload = templates[template_name].copy()
    payload["conditions"] = [c.copy() for c in payload["conditions"]]
    payload["actions"] = [a.copy() for a in payload["actions"]]

    if pod_id is not None:
        for action in payload["actions"]:
            if "pod_id" in action:
                action["pod_id"] = pod_id

    return payload
