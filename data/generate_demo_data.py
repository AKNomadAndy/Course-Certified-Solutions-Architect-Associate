from datetime import date, timedelta
import csv
from pathlib import Path

out = Path(__file__).resolve().parent / "demo_transactions.csv"
start = date.today() - timedelta(days=92)
merchants = ["Grocer", "Coffee Spot", "Utilities", "Transit", "Payroll", "Rent"]
rows = []
for i in range(66):
    d = start + timedelta(days=i)
    if i % 14 == 0:
        desc, amt, cat = "Payroll Deposit", 2200.00, "Income"
    elif i % 30 == 0:
        desc, amt, cat = "Rent Payment", -1200.00, "Housing"
    else:
        merchant = merchants[i % len(merchants)]
        desc = f"{merchant} Purchase"
        amt = -round(10 + (i % 7) * 3.15, 2)
        cat = "Living"
    rows.append([d.isoformat(), desc, amt, "Main Checking", cat, desc.split()[0], "USD"])

with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "description", "amount", "account", "category", "merchant", "currency"])
    w.writerows(rows)
print(out)
