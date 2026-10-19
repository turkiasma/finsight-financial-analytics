"""Load and validate FinSight's single-currency (EUR) cash transactions."""

from pathlib import Path
from typing import IO
import warnings

import pandas as pd


REQUIRED_COLUMNS = ("date", "description", "category", "type", "amount")
CATEGORY_TYPES = {
    "Product Sales": "Income",
    "Service Revenue": "Income",
    "Subscription Revenue": "Income",
    "Rent": "Expense",
    "Salaries": "Expense",
    "Marketing": "Expense",
    "Software": "Expense",
    "Utilities": "Expense",
    "Supplies": "Expense",
}


def validate_required_columns(transactions: pd.DataFrame) -> None:
    """Require the five documented columns, without duplicates or extra fields."""
    missing = [name for name in REQUIRED_COLUMNS if name not in transactions.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}.")
    if transactions.columns.has_duplicates:
        raise ValueError("Duplicate column names are not allowed.")
    extra = [name for name in transactions.columns if name not in REQUIRED_COLUMNS]
    if extra:
        raise ValueError(f"Unexpected columns: {', '.join(map(str, extra))}.")


def _reject_invalid(invalid: pd.Series, message: str) -> None:
    """Raise an error identifying up to ten offending CSV data row positions."""
    rows = [str(position + 2) for position, bad in enumerate(invalid) if bad]
    if rows:
        suffix = " (first 10 shown)" if len(rows) > 10 else ""
        raise ValueError(f"{message} CSV rows: {', '.join(rows[:10])}{suffix}.")


def validate_transactions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Return a cleaned copy, or reject the entire dataset with a ValueError.

    Input fields use the documented CSV text format. Surrounding whitespace is
    trimmed. Dates must be YYYY-MM-DD; amounts must be plain positive decimal
    numbers with at most two decimal places. No rows are dropped or deduplicated.
    Row numbers in errors count the header as row 1 (one record per line).
    """
    validate_required_columns(transactions)
    if transactions.empty:
        raise ValueError("The CSV must contain at least one transaction.")

    clean = transactions.loc[:, list(REQUIRED_COLUMNS)].copy()
    for column in REQUIRED_COLUMNS:
        clean[column] = clean[column].astype("string").str.strip()
        _reject_invalid(
            clean[column].isna() | clean[column].eq(""),
            f"Missing required value in '{column}'.",
        )

    dates = pd.to_datetime(clean["date"], format="%Y-%m-%d", errors="coerce")
    _reject_invalid(
        ~clean["date"].str.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}") | dates.isna(),
        "Invalid date; expected a real calendar date in YYYY-MM-DD format.",
    )
    _reject_invalid(
        ~clean["type"].isin(("Income", "Expense")),
        "Invalid transaction type; expected Income or Expense (case-sensitive).",
    )
    _reject_invalid(
        ~clean["category"].isin(CATEGORY_TYPES),
        "Invalid category; use one of the documented business categories.",
    )
    _reject_invalid(
        clean["category"].map(CATEGORY_TYPES).ne(clean["type"]),
        "Category and transaction type are inconsistent.",
    )

    amounts = pd.to_numeric(clean["amount"], errors="coerce")
    _reject_invalid(
        ~clean["amount"].str.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?")
        | amounts.isna() | amounts.le(0) | amounts.eq(float("inf")),
        "Invalid amount; expected a finite, strictly positive number with at most "
        "two decimal places (for example 1250.50).",
    )
    clean["date"] = dates
    clean["amount"] = amounts.astype("float64")
    return clean.reset_index(drop=True)


def load_transactions(source: str | Path | IO[str] | IO[bytes]) -> pd.DataFrame:
    """Read a UTF-8 CSV path or file-like object and validate every transaction.

    Missing paths raise FileNotFoundError. Empty, malformed, incorrectly encoded,
    or invalid CSV data raises ValueError. File-like inputs are read from their
    current position. All amounts are assumed to be EUR; no conversion is done.
    """
    try:
        with warnings.catch_warnings():
            # index_col=False prevents surplus fields becoming a silent row index.
            # Treat any resulting truncation warning as a malformed CSV error.
            warnings.simplefilter("error", pd.errors.ParserWarning)
            transactions = pd.read_csv(
                source, dtype="string", encoding="utf-8-sig",
                keep_default_na=False, skip_blank_lines=False, index_col=False,
            )
    except (pd.errors.EmptyDataError, pd.errors.ParserError,
            pd.errors.ParserWarning, UnicodeDecodeError) as error:
        raise ValueError(f"Unable to read transactions CSV: {error}") from error
    return validate_transactions(transactions)
