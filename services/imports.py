from __future__ import annotations

import hashlib
from io import BytesIO
import pandas as pd
from sqlalchemy import select

from db import models

REQUIRED_COLUMNS = ["date", "description", "amount"]
OPTIONAL_COLUMNS = ["account", "category", "merchant", "currency"]

# Alternate card statement format support.
ALT_COLUMN_MAP = {
    "trans_date": "date",
    "trans_dat": "date",
    "post_date": "posted_date",
    "amount_usd": "amount",
    "section": "category",
    "foreign_currency": "currency",
}



def _read_csv(csv_path_or_buffer):
    if hasattr(csv_path_or_buffer, "read"):
        raw = csv_path_or_buffer.read()
        if hasattr(csv_path_or_buffer, "seek"):
            csv_path_or_buffer.seek(0)
        return pd.read_csv(BytesIO(raw))
    return pd.read_csv(csv_path_or_buffer)



def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cols = [c.lower().strip() for c in df.columns]
    df.columns = cols

    # If canonical required fields exist, use directly.
    if all(c in df.columns for c in REQUIRED_COLUMNS):
        pass
    else:
        # Try alternate statement schema mapping.
        renamed = {col: ALT_COLUMN_MAP[col] for col in df.columns if col in ALT_COLUMN_MAP}
        df = df.rename(columns=renamed)

        if "description" not in df.columns and "section" in cols:
            # Fallback: compose description from section + raw description if needed.
            df["description"] = df.get("description", "")

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                "Missing required columns after mapping: "
                f"{missing}. Supported canonical columns: {REQUIRED_COLUMNS}; "
                "or statement format columns including trans_date, description, amount_usd."
            )

    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Type normalization.
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["description"] = df["description"].astype(str).str.strip()

        # Fill richer values from alternate columns when present.
    if "card_last4" in df.columns:
        card_series = df["card_last4"].astype(str).str.strip()
        formatted = card_series.apply(lambda x: f"Card {x}" if x and x.lower() != "nan" else None)
        if "account" not in df.columns:
            df["account"] = None
        df["account"] = df["account"].where(df["account"].notna(), formatted)
    if "foreign_currency" in df.columns:
        df["currency"] = df["currency"].fillna(df["foreign_currency"])

    # Drop invalid rows.
    df = df[df["date"].notna() & df["amount"].notna() & (df["description"] != "")]
    return df



def ingest_transactions(session, csv_path_or_buffer):
    df = _read_csv(csv_path_or_buffer)
    df = _normalize_dataframe(df)

    created, events = 0, []
    for row in df.to_dict(orient="records"):
        tx_hash = hashlib.sha1(f"{row['date']}|{row['description']}|{row['amount']}|{row.get('account')}".encode()).hexdigest()
        exists = session.scalar(select(models.Transaction).where(models.Transaction.tx_hash == tx_hash))
        if exists:
            continue
        tx = models.Transaction(
            tx_hash=tx_hash,
            date=row["date"],
            description=row["description"],
            amount=float(row["amount"]),
            account=row.get("account"),
            category=row.get("category"),
            merchant=row.get("merchant"),
            currency=row.get("currency"),
        )
        session.add(tx)
        session.flush()
        events.append({"event_key": f"tx:{tx.id}", "transaction_id": tx.id})
        created += 1
    session.commit()
    return {"created": created, "events": events}
