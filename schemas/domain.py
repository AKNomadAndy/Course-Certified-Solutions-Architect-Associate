from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, Field


class UserSettingsSchema(BaseModel):
    user_name: str = "Personal User"
    base_currency: str = "USD"


class AccountSchema(BaseModel):
    name: str
    type: str
    currency: str = "USD"
    institution: str | None = None


class PodSchema(BaseModel):
    name: str
    target_balance: float = 0
    current_balance: float = 0


class LiabilitySchema(BaseModel):
    name: str
    statement_balance: float
    min_due: float
    due_date: date | None = None
    apr: float | None = None


class TransactionSchema(BaseModel):
    date: date
    description: str
    amount: float
    account: str | None = None
    category: str | None = None
    merchant: str | None = None
    currency: str | None = "USD"


class RuleSchema(BaseModel):
    name: str
    priority: int = 100
    trigger_type: str
    trigger_config: dict = Field(default_factory=dict)
    conditions: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    enabled: bool = True


class TaskSchema(BaseModel):
    title: str
    task_type: str
    due_date: date | None = None
    note: str | None = None


class SimulationReport(BaseModel):
    rule_name: str
    traces: list[dict]
    summary: dict
    generated_at: datetime = Field(default_factory=datetime.utcnow)
