from __future__ import annotations

import hashlib
from io import BytesIO, StringIO
from statistics import mean, pstdev

import pandas as pd
from sqlalchemy import select

from db import models

REQUIRED_COLUMNS = ["date", "description", "amount"]
OPTIONAL_COLUMNS = ["account", "category", "merchant", "currency"]

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
        if isinstance(raw, str):
            return pd.read_csv(StringIO(raw))
        return pd.read_csv(BytesIO(raw))
    return pd.read_csv(csv_path_or_buffer)


def _export_key_from_columns(columns: list[str]) -> str:
    normalized = [c.lower().strip() for c in columns]
    return "|".join(sorted(normalized))


def _detect_institution_label(df: pd.DataFrame) -> str:
    cols = set(df.columns)
    if {"card_last4", "statement_period_start", "amount_usd"}.issubset(cols):
        return "Card Statement Export"
    if {"date", "description", "amount"}.issubset(cols):
        return "Canonical CSV"
    return "Unknown Export"


def remember_column_mapping(session, raw_columns: list[str], institution_label: str, mapping: dict):
    export_key = _export_key_from_columns(raw_columns)
    row = session.scalar(select(models.ImportProfile).where(models.ImportProfile.export_key == export_key))
    if not row:
        row = models.ImportProfile(
            institution_label=institution_label,
            export_key=export_key,
            column_mapping=mapping,
            sample_columns=raw_columns,
        )
        session.add(row)
    else:
        row.institution_label = institution_label
        row.column_mapping = mapping
        row.sample_columns = raw_columns
    session.commit()
    return row


def list_import_profiles(session):
    return session.scalars(select(models.ImportProfile).order_by(models.ImportProfile.updated_at.desc())).all()


def upsert_merchant_category_rule(session, merchant_pattern: str, category: str):
    pattern = (merchant_pattern or "").strip().lower()
    if not pattern:
        raise ValueError("Merchant pattern is required")
    row = session.scalar(select(models.MerchantCategoryRule).where(models.MerchantCategoryRule.merchant_pattern == pattern))
    if not row:
        row = models.MerchantCategoryRule(merchant_pattern=pattern, category=category.strip())
        session.add(row)
    else:
        row.category = category.strip()
    session.commit()
    return row


def list_merchant_category_rules(session):
    return session.scalars(select(models.MerchantCategoryRule).order_by(models.MerchantCategoryRule.merchant_pattern)).all()


def _apply_merchant_category_rules(session, df: pd.DataFrame) -> pd.DataFrame:
    rules = list_merchant_category_rules(session)
    if not rules or df.empty:
        return df
    out = df.copy()
    out["merchant"] = out["merchant"].fillna(out["description"]).astype(str)
    for r in rules:
        mask = out["merchant"].str.lower().str.contains(r.merchant_pattern, na=False)
        out.loc[mask, "category"] = out.loc[mask, "category"].fillna(r.category)
    return out


def _normalize_dataframe(df: pd.DataFrame, profile_mapping: dict | None = None) -> pd.DataFrame:
    df = df.copy()
    cols = [c.lower().strip() for c in df.columns]
    df.columns = cols

    if profile_mapping:
        remap = {k: v for k, v in profile_mapping.items() if k in df.columns}
        if remap:
            df = df.rename(columns=remap)

    if not all(c in df.columns for c in REQUIRED_COLUMNS):
        renamed = {col: ALT_COLUMN_MAP[col] for col in df.columns if col in ALT_COLUMN_MAP}
        df = df.rename(columns=renamed)
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

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["description"] = df["description"].astype(str).str.strip()

    if "card_last4" in df.columns:
        card_series = df["card_last4"].astype(str).str.strip()
        formatted = card_series.apply(lambda x: f"Card {x}" if x and x.lower() != "nan" else None)
        df["account"] = df["account"].where(df["account"].notna(), formatted)
    if "foreign_currency" in df.columns:
        df["currency"] = df["currency"].fillna(df["foreign_currency"])

    df = df[df["date"].notna() & df["amount"].notna() & (df["description"] != "")]
    return df


def _build_anomaly_report(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    amounts = [float(x) for x in df["amount"].tolist()]
    mu = mean(amounts)
    sigma = pstdev(amounts) if len(amounts) > 1 else 0.0
    anomalies = []
    for row in df.to_dict(orient="records"):
        amt = float(row["amount"])
        z = (amt - mu) / sigma if sigma else 0.0
        if abs(z) >= 3 or abs(amt) >= 5000:
            anomalies.append(
                {
                    "date": str(row["date"]),
                    "description": row["description"],
                    "amount": amt,
                    "zscore": round(float(z), 2),
                    "reason": "outlier_amount",
                }
            )
    return anomalies


def _quality_score(total_rows: int, accepted_rows: int, anomalies: list[dict], exact_duplicates: int) -> float:
    if total_rows <= 0:
        return 0.0
    completion = accepted_rows / total_rows
    anomaly_penalty = min(0.3, len(anomalies) / max(1, total_rows))
    duplicate_penalty = min(0.3, exact_duplicates / max(1, total_rows))
    score = max(0.0, min(1.0, completion - anomaly_penalty - duplicate_penalty))
    return round(score * 100, 1)


def ingest_transactions(session, csv_path_or_buffer, filename: str | None = None):
    raw_df = _read_csv(csv_path_or_buffer)
    raw_columns = list(raw_df.columns)
    export_key = _export_key_from_columns(raw_columns)
    profile = session.scalar(select(models.ImportProfile).where(models.ImportProfile.export_key == export_key))
    remembered_mapping = profile.column_mapping if profile else None

    df = _normalize_dataframe(raw_df, profile_mapping=remembered_mapping)
    institution_label = _detect_institution_label(raw_df)

    inferred_mapping = {k: v for k, v in ALT_COLUMN_MAP.items() if k in [c.lower().strip() for c in raw_columns]}
    remember_column_mapping(session, raw_columns, institution_label, inferred_mapping)

    df = _apply_merchant_category_rules(session, df)

    created, events = 0, []
    exact_duplicates = 0
    conflict_duplicates: list[dict] = []

    for row in df.to_dict(orient="records"):
        tx_hash = hashlib.sha1(f"{row['date']}|{row['description']}|{row['amount']}|{row.get('account')}".encode()).hexdigest()
        exists = session.scalar(select(models.Transaction).where(models.Transaction.tx_hash == tx_hash))
        if exists:
            exact_duplicates += 1
            continue

        fuzzy_existing = session.scalar(
            select(models.Transaction).where(
                models.Transaction.date == row["date"],
                models.Transaction.description == row["description"],
                models.Transaction.amount == float(row["amount"]),
            )
        )
        if fuzzy_existing:
            conflict_duplicates.append(
                {
                    "incoming": {
                        "date": str(row["date"]),
                        "description": row["description"],
                        "amount": float(row["amount"]),
                        "account": row.get("account"),
                        "category": row.get("category"),
                    },
                    "existing": {
                        "id": fuzzy_existing.id,
                        "account": fuzzy_existing.account,
                        "category": fuzzy_existing.category,
                        "merchant": fuzzy_existing.merchant,
                    },
                }
            )
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

    anomalies = _build_anomaly_report(df)
    quality = _quality_score(total_rows=len(raw_df), accepted_rows=created, anomalies=anomalies, exact_duplicates=exact_duplicates)

    run_summary = {
        "rows_total": int(len(raw_df)),
        "rows_normalized": int(len(df)),
        "created": int(created),
        "exact_duplicates": int(exact_duplicates),
        "conflict_duplicates": int(len(conflict_duplicates)),
        "anomalies": anomalies[:50],
        "quality_score": quality,
        "export_key": export_key,
    }
    session.add(
        models.ImportRun(
            file_name=filename or getattr(csv_path_or_buffer, "name", "upload.csv"),
            institution_label=institution_label,
            quality_score=quality,
            summary=run_summary,
        )
    )
    session.commit()
    return {"created": created, "events": events, "report": run_summary, "conflicts": conflict_duplicates[:100]}
