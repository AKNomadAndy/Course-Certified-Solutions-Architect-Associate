from sqlalchemy import select, func

from db import models
from services.demo_loader import load_demo_data


def test_demo_loader_idempotency(session, tmp_path):
    root = tmp_path
    (root / "data").mkdir(parents=True, exist_ok=True)
    load_demo_data(session, str(root))
    first_accounts = session.scalar(select(func.count()).select_from(models.Account))
    first_rules = session.scalar(select(func.count()).select_from(models.Rule))
    first_tx = session.scalar(select(func.count()).select_from(models.Transaction))

    load_demo_data(session, str(root))
    second_accounts = session.scalar(select(func.count()).select_from(models.Account))
    second_rules = session.scalar(select(func.count()).select_from(models.Rule))
    second_tx = session.scalar(select(func.count()).select_from(models.Transaction))

    assert first_accounts == second_accounts
    assert first_rules == second_rules
    assert first_tx == second_tx
