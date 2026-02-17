from __future__ import annotations

import difflib
import json

from sqlalchemy import func, select

from db import models


def snapshot_rule(session, rule: models.Rule, change_note: str | None = None, is_rollback: bool = False) -> models.RuleVersion:
    latest_version = session.scalar(
        select(func.max(models.RuleVersion.version_number)).where(models.RuleVersion.rule_id == rule.id)
    )
    next_version = int(latest_version or 0) + 1
    version = models.RuleVersion(
        rule_id=rule.id,
        version_number=next_version,
        name=rule.name,
        priority=rule.priority,
        trigger_type=rule.trigger_type,
        trigger_config=rule.trigger_config,
        conditions=rule.conditions,
        actions=rule.actions,
        enabled=rule.enabled,
        lifecycle_state=rule.lifecycle_state,
        change_note=change_note,
        is_rollback=is_rollback,
    )
    session.add(version)
    return version


def list_rule_versions(session, rule_id: int) -> list[models.RuleVersion]:
    return session.scalars(
        select(models.RuleVersion)
        .where(models.RuleVersion.rule_id == rule_id)
        .order_by(models.RuleVersion.version_number.desc())
    ).all()


def _version_payload(version: models.RuleVersion) -> dict:
    return {
        "name": version.name,
        "priority": version.priority,
        "trigger_type": version.trigger_type,
        "trigger_config": version.trigger_config,
        "conditions": version.conditions,
        "actions": version.actions,
        "enabled": version.enabled,
        "lifecycle_state": version.lifecycle_state,
    }


def version_diff(before: models.RuleVersion, after: models.RuleVersion) -> str:
    before_text = json.dumps(_version_payload(before), indent=2, sort_keys=True)
    after_text = json.dumps(_version_payload(after), indent=2, sort_keys=True)
    return "\n".join(
        difflib.unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile=f"v{before.version_number}",
            tofile=f"v{after.version_number}",
            lineterm="",
        )
    )


def rollback_to_version(
    session,
    rule: models.Rule,
    version: models.RuleVersion,
    change_note: str | None = None,
) -> models.Rule:
    rule.name = version.name
    rule.priority = version.priority
    rule.trigger_type = version.trigger_type
    rule.trigger_config = version.trigger_config
    rule.conditions = version.conditions
    rule.actions = version.actions
    rule.enabled = version.enabled
    rule.lifecycle_state = version.lifecycle_state
    snapshot_rule(
        session,
        rule,
        change_note=change_note or f"Rollback to v{version.version_number}",
        is_rollback=True,
    )
    return rule
