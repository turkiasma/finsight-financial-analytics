"""Reusable cash-based analytics for validated FinSight transactions.

Inputs are DataFrames returned by load_transactions(), or filtered copies with
the same schema and dtypes. Empty filtered inputs are supported. Validation is
the loader's responsibility. All money is EUR; public monetary outputs are
rounded to two decimals. No function modifies its input.
"""

import pandas as pd


def calculate_total_income(df: pd.DataFrame) -> float:
    """Sum cash received (Income), returning 0.0 when none is present."""
    return round(float(df.loc[df["type"].eq("Income"), "amount"].sum()), 2)


def calculate_total_expenses(df: pd.DataFrame) -> float:
    """Sum cash paid (Expense), returning 0.0 when none is present."""
    return round(float(df.loc[df["type"].eq("Expense"), "amount"].sum()), 2)


def calculate_net_cash_flow(df: pd.DataFrame) -> float:
    """Return cash received minus cash paid; this is not accounting net profit."""
    # Keep the underlying sums unrounded until the final result.
    income = df.loc[df["type"].eq("Income"), "amount"].sum()
    expenses = df.loc[df["type"].eq("Expense"), "amount"].sum()
    return round(float(income - expenses), 2)


def calculate_monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return month, income, expenses, net_cash_flow in chronological order.

    month contains month-start timestamps. Only months with recorded transactions
    appear; an absent transaction type within a recorded month totals 0.0.
    Empty inputs return the same columns with datetime/float dtypes and no rows.
    """
    if df.empty:
        return pd.DataFrame({
            "month": pd.Series(dtype="datetime64[ns]"),
            "income": pd.Series(dtype="float64"),
            "expenses": pd.Series(dtype="float64"),
            "net_cash_flow": pd.Series(dtype="float64"),
        })

    totals = (
        df.groupby([df["date"].dt.to_period("M"), "type"])["amount"]
        .sum().unstack(fill_value=0.0)
        .reindex(columns=["Income", "Expense"], fill_value=0.0)
        .sort_index()
    )
    summary = pd.DataFrame({
        "month": totals.index.to_timestamp(),
        "income": totals["Income"].to_numpy(dtype=float),
        "expenses": totals["Expense"].to_numpy(dtype=float),
    })
    summary["net_cash_flow"] = summary["income"] - summary["expenses"]
    summary[["income", "expenses", "net_cash_flow"]] = summary[
        ["income", "expenses", "net_cash_flow"]
    ].round(2)
    return summary


def _calculate_category_totals(
    df: pd.DataFrame, transaction_type: str, output_column: str,
) -> pd.DataFrame:
    """Aggregate one transaction type, breaking equal-total ties alphabetically."""
    totals = (
        df.loc[df["type"].eq(transaction_type)]
        .groupby("category", as_index=False)["amount"].sum()
        .rename(columns={"amount": output_column})
    )
    totals[output_column] = totals[output_column].astype(float).round(2)
    return totals.sort_values(
        [output_column, "category"], ascending=[False, True],
    ).reset_index(drop=True)


def calculate_expenses_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """Return category/total_expenses, ordered by spending highest first."""
    return _calculate_category_totals(df, "Expense", "total_expenses")


def calculate_income_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """Return category/total_income, ordered by cash received highest first."""
    return _calculate_category_totals(df, "Income", "total_income")


def calculate_monthly_changes(df: pd.DataFrame) -> pd.DataFrame:
    """Add income_change_pct and expense_change_pct to the monthly summary.

    Change is (current - previous) / previous * 100, rounded to two decimals.
    NaN means undefined: first month, previous value zero, or nonconsecutive
    calendar months. A fall from a positive amount to zero is -100%.
    df is the transaction DataFrame, not an already aggregated monthly summary.
    """
    summary = calculate_monthly_summary(df)
    months = summary["month"].dt.to_period("M").astype("int64")
    consecutive = months.diff().eq(1)
    for column, change_column in (
        ("income", "income_change_pct"),
        ("expenses", "expense_change_pct"),
    ):
        previous = summary[column].shift(1)
        denominator = previous.where(consecutive & previous.ne(0))
        summary[change_column] = (
            (summary[column] - previous) / denominator * 100
        ).round(2)
    return summary
