from __future__ import annotations

from datetime import date

import streamlit as st

from services.planner import (
    add_bill,
    build_debt_payment_plan,
    generate_monthly_bill_tasks,
    get_or_create_income_profile,
    list_bills,
    mark_bill_paid,
    monthly_plan_summary,
    reset_bill_paid_flags,
    save_income_profile,
)


def render(session):
    st.header("Income & Bills Planner")
    st.caption("Simple cash plan: recurring income/bills, payment calendar, and debt payoff guidance.")

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
            try:
                import altair as alt

                chart = (
                    alt.Chart(by_cat)
                    .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
                    .encode(x="category:N", y="amount:Q", color=alt.value("#ff8787"), tooltip=["category", "amount"])
                    .properties(height=260)
                )
                st.altair_chart(chart, use_container_width=True)
            except Exception:
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

    st.subheader("Debt Reduction Plan")
    extra = st.number_input("Extra monthly payment toward debt", min_value=0.0, step=10.0, value=max(0.0, summary["remaining"]))
    if st.button("Generate Debt Plan"):
        plan = build_debt_payment_plan(session, monthly_extra_payment=extra)
        if plan.empty:
            st.info("No liabilities found. Add liabilities in Money Map.")
        else:
            st.dataframe(plan, use_container_width=True)
            target = plan.iloc[0]
            st.success(
                f"Plan: pay minimums on all debts and target extra payment to **{target['liability']}** (APR {target['apr']:.2f}%)."
            )

    cta1, cta2 = st.columns(2)
    if cta1.button("Generate This Month's Bill Tasks"):
        created = generate_monthly_bill_tasks(session)
        st.success(f"Created {created} task(s) in Next Actions")
    cta2.caption(f"Next pay date: {summary['next_pay_date']}")
