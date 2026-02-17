from services.rule_templates import build_template_payload, list_rule_templates


def test_templates_exist():
    templates = list_rule_templates()
    assert "Income to Essentials (50%)" in templates
    assert "Monthly Debt Reminder" in templates


def test_build_template_replaces_pod_id():
    payload = build_template_payload("Income to Essentials (50%)", pod_id=42)
    assert payload["actions"][0]["pod_id"] == 42


def test_unknown_template_raises():
    try:
        build_template_payload("unknown")
        assert False, "expected KeyError"
    except KeyError:
        assert True
