from __future__ import annotations

from datetime import date, timedelta
import calendar

import pandas as pd
from sqlalchemy import select

from db import models


PAY_DAYS = {"weekly": 7, "biweekly": 14, "monthly": None}


PERSONAL_BILL_PACK = [
    {"name": "Rent", "amount": 1228.00, "due_day": 1, "category": "Housing", "autopay": False, "is_recurring": True},
    {"name": "Water", "amount": 41.00, "due_day": 15, "category": "Utilities", "autopay": False, "is_recurring": True},
    {"name": "Electric (SRP)", "amount": 60.00, "due_day": 10, "category": "Utilities", "autopay": False, "is_recurring": True},
    {"name": "Internet (Cox)", "amount": 190.00, "due_day": 17, "category": "Utilities", "autopay": False, "is_recurring": True},
    {"name": "Google One", "amount": 20.00, "due_day": 20, "category": "Subscriptions", "autopay": True, "is_recurring": True},
    {"name": "Just Insure", "amount": 65.00, "due_day": 14, "category": "Insurance", "autopay": False, "is_recurring": True},
    {"name": "Medical Expense", "amount": 111.98, "due_day": 24, "category": "Debt", "autopay": False, "is_recurring": True},
    {"name": "Bridgecrest (Car)", "amount": 300.00, "due_day": 18, "category": "Auto", "autopay": False, "is_recurring": True},
    {"name": "Capital One Minimum", "amount": 35.00, "due_day": 25, "category": "Debt", "autopay": False, "is_recurring": True},
]


PERSONAL_LIABILITY_PACK = [
    {"name": "Affirm - Expedia", "statement_balance": 684.30, "min_due": 136.86, "due_day": 1, "apr": None},
    {"name": "Affirm - American Airlines", "statement_balance": 1453.14, "min_due": 80.73, "due_day": 4, "apr": None},
    {"name": "Affirm - Valerion", "statement_balance": 4620.75, "min_due": 308.05, "due_day": 7, "apr": None},
    {"name": "Affirm - SeatGeek", "statement_balance": 865.48, "min_due": 61.82, "due_day": 24, "apr": None},
    {"name": "Medical Expense", "statement_balance": 614.86, "min_due": 111.98, "due_day": 24, "apr": None},
    {"name": "Capital One Card", "statement_balance": 1877.32, "min_due": 35.00, "due_day": 25, "apr": None},
    {"name": "Bridgecrest (Car)", "statement_balance": 0.0, "min_due": 300.00, "due_day": 18, "apr": None},
]


def get_or_create_income_profile(session):
    profile = session.scalar(select(models.IncomeProfile).where(models.IncomeProfile.name == "Primary Income"))
    if not profile:
        profile = models.IncomeProfile(name="Primary Income", monthly_amount=0, pay_frequency="monthly", is_recurring=True)
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return profile


def _next_month_same_day(d: date, preferred_day: int | None = None) -> date:
    preferred_day = preferred_day or d.day
    next_month = d.month % 12 + 1
    next_year = d.year + (1 if d.month == 12 else 0)
    day = min(preferred_day, calendar.monthrange(next_year, next_month)[1])
    return date(next_year, next_month, day)


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


def load_personal_bill_and_debt_pack(session):
    profile = save_income_profile(
        session,
        monthly_amount=4060.90,
        pay_frequency="biweekly",
        next_pay_date=date.today().replace(day=min(3, calendar.monthrange(date.today().year, date.today().month)[1])),
        current_checking_balance=float(get_or_create_income_profile(session).current_checking_balance or 0.0),
        is_recurring=True,
    )

    bill_count = 0
    for item in PERSONAL_BILL_PACK:
        add_bill(
            session,
            name=item["name"],
            amount=float(item["amount"]),
            due_day=int(item["due_day"]),
            category=item["category"],
            autopay=bool(item["autopay"]),
            next_due_date=date(date.today().year, date.today().month, min(int(item["due_day"]), calendar.monthrange(date.today().year, date.today().month)[1])),
            is_recurring=bool(item["is_recurring"]),
        )
        bill_count += 1

    liability_count = 0
    for item in PERSONAL_LIABILITY_PACK:
        due_date = date(date.today().year, date.today().month, min(int(item["due_day"]), calendar.monthrange(date.today().year, date.today().month)[1]))
        existing = session.scalar(select(models.Liability).where(models.Liability.name == item["name"]))
        if existing:
            existing.statement_balance = float(item["statement_balance"])
            existing.min_due = float(item["min_due"])
            existing.due_date = due_date
            existing.apr = item["apr"]
        else:
            session.add(
                models.Liability(
                    name=item["name"],
                    statement_balance=float(item["statement_balance"]),
                    min_due=float(item["min_due"]),
                    due_date=due_date,
                    apr=item["apr"],
                )
            )
        liability_count += 1

    session.commit()
    return {
        "income": float(profile.monthly_amount),
        "bills_loaded": bill_count,
        "liabilities_loaded": liability_count,
    }


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
    liabilities = session.scalars(
        select(models.Liability).order_by(models.Liability.apr.desc().nullslast(), models.Liability.statement_balance.desc())
    ).all()
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


def build_debt_payoff_schedule(session, monthly_extra_payment: float = 0.0, months: int = 24):
    plan = build_debt_payment_plan(session, monthly_extra_payment)
    if plan.empty:
        return pd.DataFrame(columns=["month", "liability", "starting_balance", "interest", "payment", "ending_balance"])

    balances = {row["liability"]: float(row["statement_balance"]) for _, row in plan.iterrows()}
    aprs = {row["liability"]: float(row["apr"] or 0.0) for _, row in plan.iterrows()}
    min_dues = {row["liability"]: float(row["min_due"]) for _, row in plan.iterrows()}
    target = plan.iloc[0]["liability"]
    extra_pool = max(0.0, monthly_extra_payment)

    rows = []
    for month in range(1, months + 1):
        all_zero = all(v <= 0.01 for v in balances.values())
        if all_zero:
            break

        for liability in list(balances.keys()):
            bal = balances[liability]
            if bal <= 0.01:
                continue
            monthly_rate = (aprs[liability] / 100) / 12
            interest = bal * monthly_rate
            payment = min_dues[liability]
            if liability == target:
                payment += extra_pool
            payment = min(payment, bal + interest)
            end_bal = max(0.0, bal + interest - payment)
            balances[liability] = end_bal

            rows.append(
                {
                    "month": month,
                    "liability": liability,
                    "starting_balance": round(bal, 2),
                    "interest": round(interest, 2),
                    "payment": round(payment, 2),
                    "ending_balance": round(end_bal, 2),
                }
            )

    return pd.DataFrame(rows)


def build_income_bill_calendar(session, horizon_days: int = 60):
    profile = get_or_create_income_profile(session)
    bills = list_bills(session)

    start = date.today()
    end = start + timedelta(days=horizon_days)
    rows = []

    # Income events
    if profile.monthly_amount > 0 and profile.next_pay_date:
        pay_date = profile.next_pay_date
        while pay_date < start:
            if profile.pay_frequency == "weekly":
                pay_date = pay_date + timedelta(days=7)
            elif profile.pay_frequency == "biweekly":
                pay_date = pay_date + timedelta(days=14)
            else:
                pay_date = _next_month_same_day(pay_date)

        while pay_date <= end:
            paycheck = profile.monthly_amount if profile.pay_frequency == "monthly" else profile.monthly_amount / (4 if profile.pay_frequency == "weekly" else 2)
            rows.append({"date": pay_date, "event_type": "income", "name": "Paycheck", "amount": float(paycheck)})
            if profile.pay_frequency == "weekly":
                pay_date = pay_date + timedelta(days=7)
            elif profile.pay_frequency == "biweekly":
                pay_date = pay_date + timedelta(days=14)
            else:
                pay_date = _next_month_same_day(pay_date)

    # Bill events
    for bill in bills:
        due = bill.next_due_date or start
        while due < start:
            due = _next_month_same_day(due, preferred_day=bill.due_day)

        if bill.is_recurring:
            cursor = due
            while cursor <= end:
                rows.append({"date": cursor, "event_type": "bill", "name": bill.name, "amount": -float(bill.amount)})
                cursor = _next_month_same_day(cursor, preferred_day=bill.due_day)
        elif due <= end:
            rows.append({"date": due, "event_type": "bill", "name": bill.name, "amount": -float(bill.amount)})

    if not rows:
        return pd.DataFrame(columns=["date", "event_type", "name", "amount", "net"])

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    daily = df.groupby("date", as_index=False)["amount"].sum().rename(columns={"amount": "net"})
    return df.merge(daily, on="date", how="left").sort_values(["date", "event_type", "name"])


def build_today_console(session):
    today = date.today()
    cal_df = build_income_bill_calendar(session, horizon_days=30)
    profile = get_or_create_income_profile(session)

    if cal_df.empty:
        return {
            "due_7d": 0.0,
            "income_7d": 0.0,
            "unpaid_count": 0,
            "next_paycheck": profile.next_pay_date,
            "projected_low_balance_30d": profile.current_checking_balance,
            "negative_risk_30d": 0.0,
        }

    upcoming = cal_df[(cal_df["date"] >= today) & (cal_df["date"] <= (today + timedelta(days=7)))]
    due_7d = -float(upcoming[upcoming["event_type"] == "bill"]["amount"].sum()) if not upcoming.empty else 0.0
    income_7d = float(upcoming[upcoming["event_type"] == "income"]["amount"].sum()) if not upcoming.empty else 0.0

    balance = float(profile.current_checking_balance or 0.0)
    daily_net = cal_df.groupby("date", as_index=False)["net"].first().sort_values("date")
    cumulative = []
    for n in daily_net["net"].tolist():
        balance += float(n)
        cumulative.append(balance)

    projected_low = min(cumulative) if cumulative else float(profile.current_checking_balance or 0.0)
    negative_days = sum(1 for b in cumulative if b < 0)
    negative_risk = (negative_days / len(cumulative)) if cumulative else 0.0

    unpaid_count = len(session.scalars(select(models.Bill).where(models.Bill.is_active == True, models.Bill.is_paid == False)).all())  # noqa: E712

    future_income = cal_df[(cal_df["event_type"] == "income") & (cal_df["date"] >= today)].sort_values("date")
    next_paycheck = future_income.iloc[0]["date"] if not future_income.empty else profile.next_pay_date

    return {
        "due_7d": round(due_7d, 2),
        "income_7d": round(income_7d, 2),
        "unpaid_count": unpaid_count,
        "next_paycheck": next_paycheck,
        "projected_low_balance_30d": round(projected_low, 2),
        "negative_risk_30d": round(negative_risk, 4),
    }


def build_personal_weekly_actions(session):
    today = date.today()
    cal_df = build_income_bill_calendar(session, horizon_days=7)
    actions = []

    if cal_df.empty:
        return actions

    window = cal_df[(cal_df["date"] >= today) & (cal_df["date"] <= (today + timedelta(days=7)))]
    bills = window[window["event_type"] == "bill"].sort_values("date")
    incomes = window[window["event_type"] == "income"].sort_values("date")

    for _, row in bills.iterrows():
        actions.append({
            "date": row["date"],
            "action": f"Pay {row['name']}",
            "amount": round(abs(float(row["amount"])), 2),
            "priority": "high",
            "reason": "Scheduled bill due within 7 days",
        })

    for _, row in incomes.iterrows():
        actions.append({
            "date": row["date"],
            "action": "Review paycheck allocation",
            "amount": round(float(row["amount"]), 2),
            "priority": "medium",
            "reason": "Income event expected within 7 days",
        })

    return sorted(actions, key=lambda x: (x["date"], 0 if x["priority"] == "high" else 1, x["action"]))


def summarize_debt_payoff(schedule_df: pd.DataFrame):
    if schedule_df.empty:
        return {"months": 0, "total_interest": 0.0, "ending_total_balance": 0.0}

    months = int(schedule_df["month"].max())
    total_interest = float(schedule_df["interest"].sum())
    ending_total_balance = float(
        schedule_df.sort_values(["liability", "month"]).groupby("liability", as_index=False)["ending_balance"].last()["ending_balance"].sum()
    )

    return {
        "months": months,
        "total_interest": round(total_interest, 2),
        "ending_total_balance": round(ending_total_balance, 2),
    }
