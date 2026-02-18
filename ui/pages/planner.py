from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.planner import (
    add_bill,
    build_debt_payment_plan,
    build_debt_payoff_schedule,
    build_income_bill_calendar,
    build_cash_runway_projection,
    build_personal_weekly_actions,
    build_today_console,
    generate_monthly_bill_tasks,
    get_or_create_income_profile,
    list_bills,
    load_personal_bill_and_debt_pack,
    mark_bill_paid,
    monthly_plan_summary,
    reset_bill_paid_flags,
    save_income_profile,
    summarize_debt_payoff,
)


def _render_today_console(session):
    st.subheader("Today Console (Personal)")
    console = build_today_console(session)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Bills due (7d)", f"${console['due_7d']:.2f}")
    c2.metric("Income expected (7d)", f"${console['income_7d']:.2f}")
    c3.metric("Unpaid bills", int(console["unpaid_count"]))
    c4.metric("Next paycheck", str(console["next_paycheck"] or "N/A"))
    c5.metric("Projected low bal (30d)", f"${console['projected_low_balance_30d']:.2f}")
    c6.metric("Negative risk (30d)", f"{console['negative_risk_30d']:.0%}")

    if console["negative_risk_30d"] > 0:
        st.warning("Checking balance may go negative during this 30-day window. Consider reducing discretionary spend or shifting bill dates.")


def _render_weekly_actions(session):
    st.subheader("Weekly Action Plan")
    actions = build_personal_weekly_actions(session)
    if not actions:
        st.info("No scheduled actions in the next 7 days.")
        return

    df = pd.DataFrame(actions)
    st.dataframe(df, use_container_width=True)


def render(session):
    st.header("Income & Bills Planner")
    st.caption("Personal cash operating system: recurring income/bills, weekly actions, debt payoff, and what-if planning.")

    with st.container(border=True):
        st.subheader("One-Click Personal Bill & Debt Pack")
        st.caption("Load your full provided recurring bill/debt list with defaults in one step.")
        if st.button("Load My Full Bill & Debt List", type="primary"):
            loaded = load_personal_bill_and_debt_pack(session)
            st.success(
                f"Loaded defaults: income ${loaded['income']:.2f}, bills {loaded['bills_loaded']}, liabilities {loaded['liabilities_loaded']}."
            )

    _render_today_console(session)
    _render_weekly_actions(session)

    st.subheader("Bill Calendar & Cash Runway")
    horizon = st.slider("Projection horizon (days)", min_value=28, max_value=120, value=84, step=7)
    runway = build_cash_runway_projection(session, horizon_days=int(horizon))

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Starting checking", f"${runway['starting_balance']:.2f}")
    r2.metric("Projected 4 weeks", f"${runway['checkpoints']['4_weeks']:.2f}")
    r3.metric("Projected 8 weeks", f"${runway['checkpoints']['8_weeks']:.2f}")
    r4.metric("Projected 12 weeks", f"${runway['checkpoints']['12_weeks']:.2f}")

    s1, s2 = st.columns(2)
    s1.metric("Lowest projected balance", f"${runway['minimum_balance']:.2f}", delta=str(runway['minimum_balance_date']))
    shortfall_text = str(runway["first_shortfall_date"]) if runway["first_shortfall_date"] else "None"
    s2.metric("First shortfall date", shortfall_text)

    if runway["first_shortfall_date"]:
        st.error(
            f"Warning: projected negative balance on {runway['first_shortfall_date']}. "
            "Review upcoming bills and reduce discretionary spending."
        )
    else:
        st.success("No negative-balance days projected in this horizon.")

    daily_df = runway["daily"].copy()
    if not daily_df.empty:
        st.line_chart(daily_df.set_index("date")[["running_balance"]])

    st.caption("Upcoming bills to pay")
    if isinstance(runway["upcoming_bills"], pd.DataFrame) and not runway["upcoming_bills"].empty:
        st.dataframe(runway["upcoming_bills"], use_container_width=True)
    else:
        st.info("No upcoming bills in selected horizon.")

    profile = get_or_create_income_profile(session)

    with st.container(border=True):
        st.subheader("Income Setup")
        c1, c2, c3, c4 = st.columns(4)
        monthly_income = c1.number_input("Monthly income", min_value=0.0, value=float(profile.monthly_amount), step=100.0)
        pay_frequency = c2.selectbox(
            "Pay frequency",
            ["weekly", "biweekly", "monthly"],
            index=["weekly", "biweekly", "monthly"].index(profile.pay_frequency if profile.pay_frequency in ["weekly", "biweekly", "monthly"] else "monthly"),
        )
        pay_date = c3.date_input("Next pay date", value=profile.next_pay_date or date.today())
        income_recurring = c4.checkbox("Recurring income", value=bool(getattr(profile, "is_recurring", True)))

        checking_balance = st.number_input(
            "Current checking balance",
            min_value=0.0,
            value=float(profile.current_checking_balance or 0.0),
            step=50.0,
        )

        if st.button("Save Income", type="primary"):
            save_income_profile(session, monthly_income, pay_frequency, pay_date, checking_balance, is_recurring=income_recurring)
            st.success("Income and checking balance updated")

    with st.container(border=True):
        st.subheader("Add / Update Bill")
        c1, c2, c3, c4 = st.columns(4)
        name = c1.text_input("Bill name")
        amount = c2.number_input("Amount", min_value=0.0, step=1.0)
        due_date = c3.date_input("Due date", value=date.today())
        recurring = c4.checkbox("Recurring bill", value=True)
        c5, c6 = st.columns(2)
        category = c5.text_input("Category", value="Utilities")
        autopay = c6.checkbox("Autopay")
        if st.button("Save Bill") and name:
            add_bill(session, name, amount, due_date.day, category, autopay, next_due_date=due_date, is_recurring=recurring)
            st.success("Bill saved")

    summary = monthly_plan_summary(session)
    bills_df = summary["bills_df"]

    st.subheader("Monthly Plan Snapshot")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Income", f"${summary['income']:.2f}")
    m2.metric("Checking", f"${summary['checking_balance']:.2f}")
    m3.metric("Total Bills", f"${summary['total_bills']:.2f}")
    m4.metric("Autopay", f"${summary['autopay_total']:.2f}")
    m5.metric("Remaining", f"${summary['remaining']:.2f}")

    if not bills_df.empty:
        st.subheader("Bills Calendar & Mix")
        c1, c2 = st.columns(2)
        with c1:
            by_day = bills_df.groupby("due_day", as_index=False)["amount"].sum()
            st.line_chart(by_day.set_index("due_day"))
        with c2:
            by_cat = bills_df.groupby("category", as_index=False)["amount"].sum()
            st.bar_chart(by_cat, x="category", y="amount", color="#ff8787")

        st.subheader("Mark bills paid")
        bill_objs = list_bills(session)
        for bill in bill_objs:
            with st.container(border=True):
                l, r = st.columns([4, 1])
                paid_badge = "✅ Paid" if bill.is_paid else "🕒 Open"
                recur_badge = "🔁 recurring" if bill.is_recurring else "one-time"
                l.write(f"**{bill.name}** · ${bill.amount:.2f} · due {bill.next_due_date or f'day {bill.due_day}'} · {recur_badge} · {paid_badge}")
                if not bill.is_paid and r.button("Mark Paid", key=f"paid_{bill.id}"):
                    mark_bill_paid(session, bill.id, date.today())
                    st.success(f"Marked {bill.name} paid")
        if st.button("Reset Paid Flags"):
            reset_bill_paid_flags(session)
            st.success("Reset paid status for all active bills")

        st.dataframe(bills_df.sort_values(["is_paid", "due_day", "bill"]), use_container_width=True)
    else:
        st.info("No bills yet. Add bills to unlock automation and projections.")

    st.subheader("Income & Bills Calendar")
    horizon = st.slider("Calendar horizon (days)", min_value=30, max_value=120, value=60, step=15)
    cal_df = build_income_bill_calendar(session, horizon_days=int(horizon))
    if cal_df.empty:
        st.info("No scheduled income or bills yet.")
    else:
        by_date = cal_df.groupby("date", as_index=False)["net"].sum().set_index("date")
        st.line_chart(by_date)
        st.dataframe(cal_df.sort_values(["date", "event_type", "name"]), use_container_width=True)

    st.subheader("Debt Reduction Plan")
    extra = st.number_input("Extra monthly payment toward debt", min_value=0.0, step=10.0, value=max(0.0, summary["remaining"]))
    payoff_months = st.slider("Payoff projection months", min_value=6, max_value=84, value=24, step=6)
    if st.button("Generate Debt Plan"):
        plan = build_debt_payment_plan(session, monthly_extra_payment=extra)
        if plan.empty:
            st.info("No liabilities found. Add liabilities in Money Map.")
        else:
            st.dataframe(plan, use_container_width=True)
            target = plan.iloc[0]
            st.success(f"Plan: pay minimums and target extra payment to **{target['liability']}** (APR {target['apr']:.2f}%).")

            payoff = build_debt_payoff_schedule(session, monthly_extra_payment=extra, months=payoff_months)
            payoff_summary = summarize_debt_payoff(payoff)
            p1, p2, p3 = st.columns(3)
            p1.metric("Projection length", f"{payoff_summary['months']} month(s)")
            p2.metric("Projected interest", f"${payoff_summary['total_interest']:.2f}")
            p3.metric("Remaining balance", f"${payoff_summary['ending_total_balance']:.2f}")

            if not payoff.empty:
                trend = payoff.groupby("month", as_index=False)["ending_balance"].sum().set_index("month")
                st.line_chart(trend)
                st.dataframe(payoff, use_container_width=True)

    cta1, cta2 = st.columns(2)
    if cta1.button("Generate This Month's Bill Tasks"):
        created = generate_monthly_bill_tasks(session)
        st.success(f"Created {created} task(s) in Next Actions")
    cta2.caption(f"Next pay date: {summary['next_pay_date']}")
