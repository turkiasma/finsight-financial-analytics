"""Independently hand-calculated examples for the Phase 2 analytics engine."""

from io import StringIO

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from src import analytics
from src.data_loader import load_transactions


@pytest.fixture
def transactions() -> pd.DataFrame:
    """Jan: 150/60; Feb: 300/90; Mar: 0/30; Apr: 120/0 (income/expense)."""
    return load_transactions(StringIO(
        "date,description,category,type,amount\n"
        "2026-02-20,Project B,Service Revenue,Income,300.00\n"
        "2026-01-03,Project A,Service Revenue,Income,100.00\n"
        "2026-01-04,Templates,Product Sales,Income,50.00\n"
        "2026-01-10,Office,Rent,Expense,40.00\n"
        "2026-01-11,Tools,Software,Expense,20.00\n"
        "2026-02-10,Office,Rent,Expense,60.00\n"
        "2026-02-11,Tools,Software,Expense,30.00\n"
        "2026-03-10,Tools,Software,Expense,30.00\n"
        "2026-04-03,Project C,Service Revenue,Income,120.00\n"
    ))


@pytest.mark.parametrize("function, expected", [
    (analytics.calculate_total_income, 570.00),
    (analytics.calculate_total_expenses, 180.00),
    (analytics.calculate_net_cash_flow, 390.00),
])
def test_totals(transactions, function, expected):
    assert function(transactions) == pytest.approx(expected)
    assert isinstance(function(transactions), float)


def test_monthly_summary(transactions):
    expected = pd.DataFrame({
        "month": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"]),
        "income": [150.0, 300.0, 0.0, 120.0],
        "expenses": [60.0, 90.0, 30.0, 0.0],
        "net_cash_flow": [90.0, 210.0, -30.0, 120.0],
    })
    assert_frame_equal(analytics.calculate_monthly_summary(transactions), expected)


@pytest.mark.parametrize("function, column, categories, amounts", [
    (analytics.calculate_expenses_by_category, "total_expenses", ["Rent", "Software"], [100.0, 80.0]),
    (analytics.calculate_income_by_category, "total_income", ["Service Revenue", "Product Sales"], [520.0, 50.0]),
])
def test_category_totals(transactions, function, column, categories, amounts):
    result = function(transactions)
    assert list(result.columns) == ["category", column]
    assert result["category"].tolist() == categories
    assert result[column].tolist() == pytest.approx(amounts)


def test_monthly_changes(transactions):
    result = analytics.calculate_monthly_changes(transactions)
    assert list(result.columns) == [
        "month", "income", "expenses", "net_cash_flow",
        "income_change_pct", "expense_change_pct",
    ]
    assert_frame_equal(result.iloc[:, :4], analytics.calculate_monthly_summary(transactions))
    assert result.loc[1, "income_change_pct"] == pytest.approx(100.0)
    assert result.loc[1, "expense_change_pct"] == pytest.approx(50.0)
    assert result.loc[2, "income_change_pct"] == pytest.approx(-100.0)
    assert result.loc[2, "expense_change_pct"] == pytest.approx(-66.67)
    assert result.loc[3, "expense_change_pct"] == pytest.approx(-100.0)


def test_first_month_changes_undefined(transactions):
    result = analytics.calculate_monthly_changes(transactions)
    assert result.loc[0, ["income_change_pct", "expense_change_pct"]].isna().all()


def test_zero_denominators(transactions):
    # April follows zero March income. May follows zero April expenses.
    may = transactions.iloc[[0]].assign(date=pd.Timestamp("2026-05-10"))
    result = analytics.calculate_monthly_changes(pd.concat([transactions, may]))
    assert pd.isna(result.loc[3, "income_change_pct"])
    assert pd.isna(result.loc[4, "expense_change_pct"])
    assert result.loc[4, "income_change_pct"] == pytest.approx(150.0)


def test_missing_calendar_month(transactions):
    # Remove February. March must not be compared with January.
    filtered = transactions.loc[transactions["date"].dt.month.ne(2)]
    result = analytics.calculate_monthly_changes(filtered)
    assert result["month"].dt.month.tolist() == [1, 3, 4]
    assert result.loc[1, ["income_change_pct", "expense_change_pct"]].isna().all()
    assert result.loc[2, "expense_change_pct"] == pytest.approx(-100.0)


def test_year_boundary_is_consecutive(transactions):
    first = transactions.iloc[[0]].assign(date=pd.Timestamp("2025-12-15"), amount=100.0)
    second = first.assign(date=pd.Timestamp("2026-01-15"), amount=125.0)
    result = analytics.calculate_monthly_changes(pd.concat([second, first]))
    assert result.loc[1, "income_change_pct"] == pytest.approx(25.0)
    assert pd.isna(result.loc[1, "expense_change_pct"])


@pytest.mark.parametrize("kind, income, expenses, net", [
    ("Income", 570.0, 0.0, 570.0),
    ("Expense", 0.0, 180.0, -180.0),
])
def test_single_transaction_type(transactions, kind, income, expenses, net):
    filtered = transactions.loc[transactions["type"].eq(kind)]
    assert analytics.calculate_total_income(filtered) == income
    assert analytics.calculate_total_expenses(filtered) == expenses
    assert analytics.calculate_net_cash_flow(filtered) == net
    summary = analytics.calculate_monthly_summary(filtered)
    missing_column = "expenses" if kind == "Income" else "income"
    assert summary[missing_column].eq(0.0).all()
    missing_categories = (analytics.calculate_expenses_by_category(filtered)
                          if kind == "Income" else analytics.calculate_income_by_category(filtered))
    assert missing_categories.empty


def test_empty_input(transactions):
    empty = transactions.iloc[:0]
    assert analytics.calculate_total_income(empty) == 0.0
    assert analytics.calculate_total_expenses(empty) == 0.0
    assert analytics.calculate_net_cash_flow(empty) == 0.0
    for function, columns in [
        (analytics.calculate_monthly_summary, ["month", "income", "expenses", "net_cash_flow"]),
        (analytics.calculate_monthly_changes, ["month", "income", "expenses", "net_cash_flow", "income_change_pct", "expense_change_pct"]),
        (analytics.calculate_income_by_category, ["category", "total_income"]),
        (analytics.calculate_expenses_by_category, ["category", "total_expenses"]),
    ]:
        result = function(empty)
        assert result.empty
        assert list(result.columns) == columns
        for column in columns:
            if column == "month":
                assert pd.api.types.is_datetime64_any_dtype(result[column])
            elif column != "category":
                assert pd.api.types.is_float_dtype(result[column])


ALL_FUNCTIONS = [
    analytics.calculate_total_income, analytics.calculate_total_expenses,
    analytics.calculate_net_cash_flow, analytics.calculate_monthly_summary,
    analytics.calculate_expenses_by_category, analytics.calculate_income_by_category,
    analytics.calculate_monthly_changes,
]


@pytest.mark.parametrize("function", ALL_FUNCTIONS)
def test_input_is_not_modified(transactions, function):
    original = transactions.copy(deep=True)
    function(transactions)
    assert_frame_equal(transactions, original)


def test_decimal_amounts(transactions):
    small = transactions.iloc[[0, 1, 3]].copy()
    small["amount"] = [0.10, 0.20, 0.10]
    assert analytics.calculate_total_income(small) == pytest.approx(0.30)
    assert analytics.calculate_total_expenses(small) == pytest.approx(0.10)
    assert analytics.calculate_net_cash_flow(small) == pytest.approx(0.20)


def test_category_ties_are_alphabetical(transactions):
    tied = transactions.loc[transactions["type"].eq("Expense")].iloc[:2].copy()
    tied["amount"] = 10.0
    result = analytics.calculate_expenses_by_category(tied)
    assert result["category"].tolist() == ["Rent", "Software"]
