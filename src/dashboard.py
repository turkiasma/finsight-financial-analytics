"""Small, testable data-selection and presentation helpers for the dashboard."""

from datetime import date
from io import BytesIO
from pathlib import Path
from collections.abc import Sequence

import pandas as pd

from src.data_loader import REQUIRED_COLUMNS, load_transactions


SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "sample_transactions.csv"


def load_dashboard_dataset(selection: str, uploaded_csv: bytes | None = None) -> pd.DataFrame | None:
    """Load the chosen dataset; missing uploads return None, invalid ones raise.

    An invalid upload never falls back to the sample or a previously valid file.
    """
    if selection == "Sample Dataset":
        return load_transactions(SAMPLE_PATH)
    if selection == "Upload CSV":
        return None if uploaded_csv is None else load_transactions(BytesIO(uploaded_csv))
    raise ValueError("Choose Sample Dataset or Upload CSV.")


def filter_analysis_scope(
    transactions: pd.DataFrame, start: date, end: date, categories: Sequence[str],
) -> pd.DataFrame:
    """Apply inclusive dates and selected categories; no categories means no rows."""
    if start > end:
        raise ValueError("Start date must be on or before end date.")
    mask = transactions["date"].between(pd.Timestamp(start), pd.Timestamp(end))
    return transactions.loc[mask & transactions["category"].isin(categories)].copy()


def filter_explorer(scope: pd.DataFrame, transaction_types: Sequence[str]) -> pd.DataFrame:
    """Apply type selection only to explorer rows, ordered newest first."""
    return scope.loc[scope["type"].isin(transaction_types)].sort_values(
        "date", ascending=False, kind="stable",
    ).reset_index(drop=True)


def export_transactions(transactions: pd.DataFrame) -> bytes:
    """Export exactly these rows as UTF-8, preserving the loader-compatible schema."""
    exported = transactions.loc[:, list(REQUIRED_COLUMNS)].copy()
    exported["date"] = exported["date"].dt.strftime("%Y-%m-%d")
    return exported.to_csv(index=False, float_format="%.2f", lineterminator="\n").encode("utf-8")


def format_monthly_comparison(changes: pd.DataFrame) -> pd.DataFrame:
    """Format analytics outputs for display, explicitly showing undefined changes."""
    display = changes.copy()
    display["month"] = display["month"].dt.strftime("%b %Y")
    for column in ("income", "expenses", "net_cash_flow"):
        display[column] = display[column].map(lambda value: f"€{value:,.2f}")
    for column in ("income_change_pct", "expense_change_pct"):
        display[column] = display[column].map(
            lambda value: "N/A" if pd.isna(value) else f"{value:+.2f}%",
        )
    return display.rename(columns={
        "month": "Month", "income": "Total Income", "expenses": "Total Expenses",
        "net_cash_flow": "Net Cash Flow", "income_change_pct": "Income Change (%)",
        "expense_change_pct": "Expense Change (%)",
    })


def financial_highlights(changes: pd.DataFrame, expenses: pd.DataFrame) -> list[str]:
    """Describe verified analytics outputs without predictions or financial advice.

    Ties use the first chronological month or the category aggregation's order.
    Zero totals do not imply a source of income or an expense was present.
    """
    if changes.empty:
        return ["No financial highlights are available for the current selection."]
    highlights = []
    for column, label in (("income", "income"), ("expenses", "expenses")):
        row = changes.loc[changes[column].idxmax()]
        if row[column] > 0:
            highlights.append(
                f"Highest monthly {label}: {row['month']:%B %Y} (€{row[column]:,.2f})."
            )
    if not expenses.empty:
        row = expenses.iloc[0]
        highlights.append(f"Largest expense category: {row['category']} (€{row['total_expenses']:,.2f}).")
    if len(changes) < 2 or pd.isna(changes.iloc[-1]["income_change_pct"]):
        highlights.append("Latest income comparison is unavailable: two consecutive months and a positive previous income are required.")
    else:
        latest, previous = changes.iloc[-1], changes.iloc[-2]
        change = latest["income_change_pct"]
        # A rounded 0.00% can still describe a small nonzero movement.
        direction = ("increased" if latest["income"] > previous["income"] else
                     "decreased" if latest["income"] < previous["income"] else "was unchanged")
        movement = (f" by {abs(change):.2f}%" if change else
                    " by less than 0.01%" if direction != "was unchanged" else "")
        highlights.append(
            f"Income {direction}{movement} from {previous['month']:%B %Y} to {latest['month']:%B %Y}."
        )
    return highlights
