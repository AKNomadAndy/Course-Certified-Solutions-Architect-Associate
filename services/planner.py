from __future__ import annotations

from datetime import date
import calendar

import pandas as pd
from sqlalchemy import select

from db import models


def get_or_create_income_profile(session):
    profile = session.scalar(select(models.IncomeProfile).where(models.IncomeProfile.name == "Primary Income"))
    if not profile:
        profile = models.IncomeProfile(name="Primary Income", monthly_amount=0, pay_frequency="monthly")
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return profile


def save_income_profile(session, monthly_amount: float, pay_frequency: str):
    profile = get_or_create_income_profile(session)
    profile.monthly_amount = float(monthly_amount)
    profile.pay_frequency = pay_frequency
    session.commit()
    return profile


def add_bill(session, name: str, amount: float, due_day: int, category: str, autopay: bool):
    existing = session.scalar(select(models.Bill).where(models.Bill.name == name))
    if existing:
        existing.amount = float(amount)
        existing.due_day = int(due_day)
        existing.category = category
        existing.autopay = autopay
        existing.is_active = True
        session.commit()
        return existing

    bill = models.Bill(name=name, amount=float(amount), due_day=int(due_day), category=category, autopay=autopay)
    session.add(bill)
    session.commit()
    session.refresh(bill)
    return bill


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
                "bill": b.name,
                "amount": b.amount,
                "due_day": b.due_day,
                "category": b.category,
                "autopay": b.autopay,
            }
            for b in bills
        ]
    )

    return {
        "income": profile.monthly_amount,
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
        due = date(year, month, min(max(1, bill.due_day), max_day))
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
