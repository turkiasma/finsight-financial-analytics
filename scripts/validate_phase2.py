"""Display the sample's actual financial results and check reconciliation."""

from math import isclose
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics import (
    calculate_expenses_by_category,
    calculate_income_by_category,
    calculate_monthly_changes,
    calculate_monthly_summary,
    calculate_net_cash_flow,
    calculate_total_expenses,
    calculate_total_income,
)
from src.data_loader import load_transactions


def _display_table(title: str, table: pd.DataFrame) -> None:
    """Print a table with two-decimal numbers and explicit undefined values."""
    display = table.copy()
    if "month" in display:
        display["month"] = display["month"].dt.strftime("%Y-%m")
    print(f"\n{title}")
    print(display.to_string(index=False, float_format=lambda value: f"{value:,.2f}",
                            na_rep="NaN"))


def main() -> None:
    """Load existing data, display each calculation, and verify five identities."""
    transactions = load_transactions(PROJECT_ROOT / "data" / "sample_transactions.csv")
    income = calculate_total_income(transactions)
    expenses = calculate_total_expenses(transactions)
    cash_flow = calculate_net_cash_flow(transactions)
    monthly = calculate_monthly_summary(transactions)
    expense_categories = calculate_expenses_by_category(transactions)
    income_categories = calculate_income_by_category(transactions)
    changes = calculate_monthly_changes(transactions)

    print("FinSight — Lumen Digital Studio (synthetic cash transactions, EUR)")
    print(f"Transactions: {len(transactions)}")
    print(f"Total Income: EUR {income:,.2f}")
    print(f"Total Expenses: EUR {expenses:,.2f}")
    print(f"Net Cash Flow: EUR {cash_flow:,.2f}")
    _display_table("Monthly Summary (EUR)", monthly)
    _display_table("Expense Breakdown by Category (EUR)", expense_categories)
    _display_table("Income Breakdown by Category (EUR)", income_categories)
    _display_table("Monthly Percentage Changes (%)", changes)
    print("NaN = undefined: first month, zero previous value, or a calendar gap.")
    print("Monetary columns in the changes table remain EUR.")

    checks = [
        ("Income - Expenses = Net Cash Flow", income - expenses, cash_flow),
        ("Monthly income reconciles to Total Income", monthly["income"].sum(), income),
        ("Monthly expenses reconcile to Total Expenses", monthly["expenses"].sum(), expenses),
        ("Category expenses reconcile to Total Expenses", expense_categories["total_expenses"].sum(), expenses),
        ("Category income reconciles to Total Income", income_categories["total_income"].sum(), income),
    ]
    print()
    for name, actual, expected in checks:
        # One millionth of a euro tolerates binary float noise, not cent errors.
        if not isclose(float(actual), expected, rel_tol=0.0, abs_tol=0.000001):
            raise AssertionError(f"{name}: {actual} != {expected}")
        print(f"PASS: {name}")
    print("Phase 2 validation passed (5 reconciliation checks).")


if __name__ == "__main__":
    main()
