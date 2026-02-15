from __future__ import annotations

from datetime import date
import calendar

import pandas as pd
from sqlalchemy import select

from db import models


def get_or_create_income_profile(session):
    profile = session.scalar(select(models.IncomeProfile).where(models.IncomeProfile.name == "Primary Income"))
    if not profile:
        profile = models.IncomeProfile(name="Primary Income", monthly_amount=0, pay_frequency="monthly", is_recurring=True)
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return profile


def save_income_profile(
    session,
    monthly_amount: float,
    pay_frequency: str,
    next_pay_date=None,
    current_checking_balance: float = 0.0,
    is_recurring: bool = True,
):
    profile = get_or_create_income_profile(session)
    profile.monthly_amount = float(monthly_amount)
    profile.pay_frequency = pay_frequency
    profile.next_pay_date = next_pay_date
    profile.current_checking_balance = float(current_checking_balance)
    profile.is_recurring = is_recurring
    session.commit()

    checking = session.scalar(select(models.Account).where(models.Account.type == "checking").order_by(models.Account.id))
    if checking:
        session.add(
            models.BalanceSnapshot(
                source_type="account",
                source_id=checking.id,
                balance=profile.current_checking_balance,
            )
        )
        session.commit()

    return profile


def add_bill(session, name: str, amount: float, due_day: int, category: str, autopay: bool, next_due_date=None, is_recurring: bool = True):
    existing = session.scalar(select(models.Bill).where(models.Bill.name == name))
    if existing:
        existing.amount = float(amount)
        existing.due_day = int(due_day)
        existing.next_due_date = next_due_date
        existing.category = category
        existing.autopay = autopay
        existing.is_recurring = is_recurring
        existing.is_active = True
        session.commit()
        return existing

    bill = models.Bill(
        name=name,
        amount=float(amount),
        due_day=int(due_day),
        next_due_date=next_due_date,
        category=category,
        autopay=autopay,
        is_recurring=is_recurring,
    )
    session.add(bill)
    session.commit()
    session.refresh(bill)
    return bill


def mark_bill_paid(session, bill_id: int, paid_on: date):
    bill = session.get(models.Bill, bill_id)
    if not bill:
        return None
    bill.is_paid = True
    bill.last_paid_date = paid_on
    session.commit()
    return bill


def reset_bill_paid_flags(session):
    bills = session.scalars(select(models.Bill).where(models.Bill.is_active == True)).all()  # noqa: E712
    for b in bills:
        b.is_paid = False
    session.commit()


def list_bills(session):
    return session.scalars(select(models.Bill).where(models.Bill.is_active == True).order_by(models.Bill.due_day, models.Bill.name)).all()  # noqa: E712


def monthly_plan_summary(session):
    profile = get_or_create_income_profile(session)
    bills = list_bills(session)
    total_bills = sum(b.amount for b in bills)
    remaining = profile.monthly_amount - total_bills
    autopay_total = sum(b.amount for b in bills if b.autopay)

    bills_df = pd.DataFrame(
        [
            {
                "id": b.id,
                "bill": b.name,
                "amount": b.amount,
                "due_day": b.due_day,
                "next_due_date": b.next_due_date,
                "category": b.category,
                "autopay": b.autopay,
                "is_recurring": b.is_recurring,
                "is_paid": b.is_paid,
                "last_paid_date": b.last_paid_date,
            }
            for b in bills
        ]
    )

    return {
        "income": profile.monthly_amount,
        "income_recurring": profile.is_recurring,
        "next_pay_date": profile.next_pay_date,
        "checking_balance": profile.current_checking_balance,
        "total_bills": round(total_bills, 2),
        "remaining": round(remaining, 2),
        "autopay_total": round(autopay_total, 2),
        "bills_df": bills_df,
    }


def generate_monthly_bill_tasks(session):
    today = date.today()
    year, month = today.year, today.month
    _, max_day = calendar.monthrange(year, month)
    created = 0

    for bill in list_bills(session):
        if not bill.is_recurring:
            continue
        due = bill.next_due_date or date(year, month, min(max(1, bill.due_day), max_day))
        ref = f"bill:{bill.id}:{year}-{month:02d}"
        exists = session.scalar(select(models.Task).where(models.Task.reference_id == ref))
        if exists:
            continue
        session.add(
            models.Task(
                title=f"Pay {bill.name}",
                task_type="bill_payment",
                due_date=due,
                note=f"Amount ${bill.amount:.2f} ({bill.category})",
                reference_id=ref,
            )
        )
        created += 1

    session.commit()
    return created


def build_debt_payment_plan(session, monthly_extra_payment: float = 0.0):
    liabilities = session.scalars(select(models.Liability).order_by(models.Liability.apr.desc().nullslast(), models.Liability.statement_balance.desc())).all()
    if not liabilities:
        return pd.DataFrame(columns=["liability", "statement_balance", "min_due", "apr", "suggested_payment", "strategy"])

    rows = []
    extra_pool = max(0.0, monthly_extra_payment)
    for idx, debt in enumerate(liabilities):
        min_due = float(debt.min_due or 0.0)
        suggested = min_due
        strategy = "minimum"
        if idx == 0 and extra_pool > 0:
            suggested += extra_pool
            strategy = "avalanche_target"

        rows.append(
            {
                "liability": debt.name,
                "statement_balance": float(debt.statement_balance or 0.0),
                "min_due": min_due,
                "apr": float(debt.apr or 0.0),
                "suggested_payment": round(suggested, 2),
                "strategy": strategy,
            }
        )

    return pd.DataFrame(rows)
