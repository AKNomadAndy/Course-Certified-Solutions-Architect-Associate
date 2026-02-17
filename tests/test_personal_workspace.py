from db import models
from services.personal_workspace import load_full_personal_workspace


def test_load_full_personal_workspace_populates_core_entities(session):
    summary = load_full_personal_workspace(session)

    assert summary["accounts"] >= 2
    assert summary["pods"] >= 3
    assert summary["liabilities"] >= 6
    assert summary["rules"] >= 4
    assert summary["transactions"] > 10

    assert session.query(models.MoneyMapNode).count() > 0
    assert session.query(models.MoneyMapEdge).count() > 0


def test_load_full_personal_workspace_idempotent(session):
    load_full_personal_workspace(session)
    first = {
        "accounts": session.query(models.Account).count(),
        "pods": session.query(models.Pod).count(),
        "liabilities": session.query(models.Liability).count(),
        "rules": session.query(models.Rule).count(),
    }

    load_full_personal_workspace(session)
    second = {
        "accounts": session.query(models.Account).count(),
        "pods": session.query(models.Pod).count(),
        "liabilities": session.query(models.Liability).count(),
        "rules": session.query(models.Rule).count(),
    }

    assert first == second
