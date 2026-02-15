from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///moneymesh.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _ensure_column(table: str, column: str, ddl: str) -> None:
    with engine.begin() as conn:
        cols = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        names = {c[1] for c in cols}
        if column not in names:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def init_db() -> None:
    from db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Lightweight schema evolution for existing local DBs.
    _ensure_column("income_profiles", "is_recurring", "is_recurring BOOLEAN DEFAULT 1")
    _ensure_column("income_profiles", "next_pay_date", "next_pay_date DATE")
    _ensure_column("income_profiles", "current_checking_balance", "current_checking_balance FLOAT DEFAULT 0")
    _ensure_column("bills", "is_recurring", "is_recurring BOOLEAN DEFAULT 1")
    _ensure_column("bills", "next_due_date", "next_due_date DATE")
    _ensure_column("bills", "is_paid", "is_paid BOOLEAN DEFAULT 0")
    _ensure_column("bills", "last_paid_date", "last_paid_date DATE")
