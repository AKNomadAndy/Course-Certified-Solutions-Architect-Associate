from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.engine import Base


class UserSettings(Base):
    __tablename__ = "user_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_name: Mapped[str] = mapped_column(String(120), default="Personal User")
    base_currency: Mapped[str] = mapped_column(String(8), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    type: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    institution: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Pod(Base):
    __tablename__ = "pods"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    target_balance: Mapped[float] = mapped_column(Float, default=0)
    current_balance: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Liability(Base):
    __tablename__ = "liabilities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    account_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    statement_balance: Mapped[float] = mapped_column(Float, default=0)
    min_due: Mapped[float] = mapped_column(Float, default=0)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    apr: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tx_hash: Mapped[str] = mapped_column(String(160), unique=True)
    date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float] = mapped_column(Float)
    account: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(120), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[int] = mapped_column(Integer)
    balance: Mapped[float] = mapped_column(Float)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MoneyMapNode(Base):
    __tablename__ = "money_map_nodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_type: Mapped[str] = mapped_column(String(20))
    ref_id: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(120))


class MoneyMapEdge(Base):
    __tablename__ = "money_map_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_node_id: Mapped[int] = mapped_column(ForeignKey("money_map_nodes.id"))
    target_node_id: Mapped[int] = mapped_column(ForeignKey("money_map_nodes.id"))
    label: Mapped[str] = mapped_column(String(120), default="routes to")


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    trigger_type: Mapped[str] = mapped_column(String(32))
    trigger_config: Mapped[dict] = mapped_column(JSON, default=dict)
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"))
    event_key: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(24), default="completed")
    trace: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("rule_id", "event_key", name="uq_run_rule_event"),)


class ActionResult(Base):
    __tablename__ = "action_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    action_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class ErrorLog(Base):
    __tablename__ = "error_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    task_type: Mapped[str] = mapped_column(String(40))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
