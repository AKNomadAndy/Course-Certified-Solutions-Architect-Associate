from __future__ import annotations

import hashlib
import pandas as pd
from sqlalchemy import select

from db import models

REQUIRED_COLUMNS = ["date", "description", "amount"]
OPTIONAL_COLUMNS = ["account", "category", "merchant", "currency"]


def ingest_transactions(session, csv_path_or_buffer):
    df = pd.read_csv(csv_path_or_buffer)
    cols = [c.lower().strip() for c in df.columns]
    df.columns = cols
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df["date"] = pd.to_datetime(df["date"]).dt.date
    created, events = 0, []
    for row in df.to_dict(orient="records"):
        tx_hash = hashlib.sha1(f"{row['date']}|{row['description']}|{row['amount']}|{row.get('account')}".encode()).hexdigest()
        exists = session.scalar(select(models.Transaction).where(models.Transaction.tx_hash == tx_hash))
        if exists:
            continue
        tx = models.Transaction(tx_hash=tx_hash, **row)
        session.add(tx)
        session.flush()
        events.append({"event_key": f"tx:{tx.id}", "transaction_id": tx.id})
        created += 1
    session.commit()
    return {"created": created, "events": events}
