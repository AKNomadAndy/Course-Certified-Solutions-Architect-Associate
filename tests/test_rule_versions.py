from db import models
from services.rule_versions import list_rule_versions, rollback_to_version, snapshot_rule, version_diff


def test_rule_snapshot_and_increment(session):
    rule = models.Rule(
        name="Versioned Rule",
        priority=100,
        trigger_type="manual",
        trigger_config={},
        conditions=[],
        actions=[],
        enabled=True,
        lifecycle_state="draft",
    )
    session.add(rule)
    session.flush()

    snapshot_rule(session, rule, change_note="initial")
    rule.priority = 200
    snapshot_rule(session, rule, change_note="updated priority")
    session.commit()

    versions = list_rule_versions(session, rule.id)
    assert len(versions) == 2
    assert versions[0].version_number == 2
    assert versions[1].version_number == 1


def test_rule_diff_and_rollback(session):
    rule = models.Rule(
        name="Rollback Rule",
        priority=100,
        trigger_type="manual",
        trigger_config={},
        conditions=[],
        actions=[],
        enabled=True,
        lifecycle_state="draft",
    )
    session.add(rule)
    session.flush()
    v1 = snapshot_rule(session, rule, change_note="v1")

    rule.priority = 300
    rule.lifecycle_state = "active"
    v2 = snapshot_rule(session, rule, change_note="v2")

    diff_text = version_diff(v1, v2)
    assert "priority" in diff_text

    rollback_to_version(session, rule, v1)
    session.commit()

    assert rule.priority == 100
    assert rule.lifecycle_state == "draft"

    versions = list_rule_versions(session, rule.id)
    assert versions[0].is_rollback is True
