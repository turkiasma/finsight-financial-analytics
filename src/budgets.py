"""Validate monthly EUR spending targets and compare them with recorded expenses."""

from collections.abc import Sequence
from pathlib import Path
from typing import IO
import re
import warnings

import pandas as pd

from src.analytics import calculate_expenses_by_category
from src.data_loader import CATEGORY_TYPES


BUDGET_COLUMNS = ("month", "category", "budget_amount")
EXPENSE_CATEGORIES = tuple(name for name, kind in CATEGORY_TYPES.items() if kind == "Expense")


def _reject_invalid(mask: pd.Series, message: str) -> None:
    """Identify invalid data records, counting the header as CSV row 1."""
    rows = [str(index + 2) for index, invalid in enumerate(mask) if invalid]
    if rows:
        raise ValueError(f"{message} CSV rows (up to 10): {', '.join(rows[:10])}.")


def validate_budgets(budgets: pd.DataFrame) -> pd.DataFrame:
    """Return a clean copy with month-start dates and float64 budget amounts.

    Require the exact schema, real YYYY-MM months, supported expense categories,
    finite non-negative amounts with at most two decimals, and unique month/
    category pairs. Reject invalid records without dropping or inventing values.
    """
    missing = [column for column in BUDGET_COLUMNS if column not in budgets.columns]
    if missing:
        raise ValueError(f"Missing required budget columns: {', '.join(missing)}.")
    if budgets.columns.has_duplicates or set(budgets.columns) != set(BUDGET_COLUMNS):
        raise ValueError("Budget CSV must contain exactly month, category, budget_amount without duplicate columns.")
    if budgets.empty:
        raise ValueError("Budget CSV must contain at least one budget entry.")
    clean = budgets.loc[:, list(BUDGET_COLUMNS)].copy()
    for column in BUDGET_COLUMNS:
        clean[column] = clean[column].astype("string").str.strip()
        _reject_invalid(clean[column].isna() | clean[column].eq(""), f"Missing required budget value in '{column}'.")
    months = pd.to_datetime(clean["month"], format="%Y-%m", errors="coerce")
    _reject_invalid(
        ~clean["month"].str.fullmatch(r"[0-9]{4}-[0-9]{2}") | months.isna(),
        "Invalid budget month; expected YYYY-MM.",
    )
    _reject_invalid(~clean["category"].isin(EXPENSE_CATEGORIES), "Invalid budget category; use a supported expense category.")
    amounts = pd.to_numeric(clean["budget_amount"], errors="coerce")
    _reject_invalid(
        ~clean["budget_amount"].str.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?")
        | amounts.isna() | amounts.lt(0) | amounts.eq(float("inf")),
        "Invalid budget amount; expected a finite non-negative number with at most two decimal places.",
    )
    _reject_invalid(clean.duplicated(["month", "category"], keep=False), "Duplicate budget month/category combination.")
    clean["month"] = months
    clean["budget_amount"] = amounts.astype("float64")
    return clean.sort_values(["month", "category"]).reset_index(drop=True)


def load_budgets(source: str | Path | IO[str] | IO[bytes]) -> pd.DataFrame:
    """Read a UTF-8 CSV path or file-like object and validate its entire contents."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", pd.errors.ParserWarning)
            budgets = pd.read_csv(
                source, dtype="string", encoding="utf-8-sig", keep_default_na=False,
                skip_blank_lines=False, index_col=False,
            )
    except (pd.errors.EmptyDataError, pd.errors.ParserError,
            pd.errors.ParserWarning, UnicodeDecodeError) as error:
        raise ValueError(f"Unable to read budget CSV: {error}") from error
    return validate_budgets(budgets)


def calculate_budget_comparison(
    transactions: pd.DataFrame, budgets: pd.DataFrame, month: str,
    categories: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Compare an entire calendar month, ignoring any dashboard filter state.

    Inputs must already be validated; pass the full transaction dataset. month
    must be YYYY-MM. None categories means all supported expense categories;
    [] means no categories. Include budget-only and actual-only categories.
    Missing budgets/variances are NaN, not zero. Zero budgets also have NaN
    percentages. Financial inputs and outputs use EUR and are never mutated.
    """
    if not isinstance(month, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", month):
        raise ValueError("Comparison month must be YYYY-MM.")
    try:
        selected_month = pd.Period(month, freq="M")
    except ValueError as error:
        raise ValueError("Comparison month must be a real calendar month in YYYY-MM format.") from error
    selected_categories = list(EXPENSE_CATEGORIES if categories is None else categories)
    if not set(selected_categories).issubset(EXPENSE_CATEGORIES):
        raise ValueError("Select only supported expense categories for budget comparisons.")
    monthly_transactions = transactions.loc[
        transactions["date"].dt.to_period("M").eq(selected_month)
        & transactions["category"].isin(selected_categories)
    ]
    actuals = calculate_expenses_by_category(monthly_transactions).rename(columns={"total_expenses": "actual"})
    targets = budgets.loc[
        budgets["month"].dt.to_period("M").eq(selected_month)
        & budgets["category"].isin(selected_categories), ["category", "budget_amount"],
    ].rename(columns={"budget_amount": "budget"})
    result = targets.merge(actuals, on="category", how="outer", validate="one_to_one")
    result["actual"] = result["actual"].fillna(0.0)
    result["variance"] = (result["actual"] - result["budget"]).round(2)
    result["variance_pct"] = (result["variance"] / result["budget"].where(result["budget"].gt(0)) * 100).round(2)
    result["status"] = "On budget"
    result.loc[result["variance"].gt(0), "status"] = "Over budget"
    result.loc[result["variance"].lt(0), "status"] = "Under budget"
    result.loc[result["budget"].isna(), "status"] = "No budget set"
    return result[["category", "budget", "actual", "variance", "variance_pct", "status"]].sort_values("category").reset_index(drop=True)


def summarize_budget_comparison(comparison: pd.DataFrame) -> dict[str, float]:
    """Total explicit budgets and all actuals; suppress variance if coverage is incomplete.

    A completely unbudgeted comparison has NaN total budget. An empty category
    selection has zero totals. Never treat missing budgets as zero allocations.
    """
    if comparison.empty:
        return {"budget": 0.0, "actual": 0.0, "variance": 0.0}
    return {
        "budget": round(float(comparison["budget"].sum(min_count=1)), 2),
        "actual": round(float(comparison["actual"].sum()), 2),
        "variance": (float("nan") if comparison["budget"].isna().any()
                     else round(float(comparison["variance"].sum()), 2)),
    }
