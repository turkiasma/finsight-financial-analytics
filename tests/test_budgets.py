"""Hand-verified monthly targets, variances, validation, and dashboard integration."""

from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
from streamlit.testing.v1 import AppTest

from src.budgets import (
    calculate_budget_comparison, load_budgets, summarize_budget_comparison, validate_budgets,
)
from src.charts import budget_actual_chart
from src.data_loader import load_transactions


ROOT = Path(__file__).resolve().parents[1]
BUDGET_CSV = (
    b"month,category,budget_amount\n"
    b"2026-01,Marketing,100.00\n"
    b"2026-01,Rent,60.00\n"
    b"2026-01,Software,0.00\n"
    b"2026-01,Supplies,0.00\n"
    b"2026-01,Utilities,25.00\n"
    b"2026-02,Marketing,200.00\n"
)
TRANSACTIONS = (
    b"date,description,category,type,amount\n"
    b"2026-01-01,Campaign A,Marketing,Expense,80.00\n"
    b"2026-01-31,Campaign B,Marketing,Expense,50.00\n"
    b"2026-01-10,Office,Rent,Expense,40.00\n"
    b"2026-01-15,Tools,Software,Expense,10.00\n"
    b"2026-01-25,Team,Salaries,Expense,30.00\n"
    b"2026-01-20,Project,Service Revenue,Income,999.00\n"
    b"2026-02-01,Campaign C,Marketing,Expense,70.00\n"
)


@pytest.fixture
def budgets():
    return load_budgets(BytesIO(BUDGET_CSV))


@pytest.fixture
def transactions():
    return load_transactions(BytesIO(TRANSACTIONS))


def test_valid_budget_load(budgets):
    assert len(budgets) == 6
    assert list(budgets.columns) == ["month", "category", "budget_amount"]
    assert pd.api.types.is_datetime64_any_dtype(budgets["month"])
    assert budgets["budget_amount"].dtype == "float64"
    assert budgets.loc[0, "month"] == pd.Timestamp("2026-01-01")
    assert budgets["budget_amount"].tolist() == [100.0, 60.0, 0.0, 0.0, 25.0, 200.0]


def test_sample_budget_structure():
    sample = ROOT / "data" / "sample_budgets.csv"
    loaded = load_budgets(sample)
    assert len(loaded) == 36
    assert loaded.groupby("month").size().tolist() == [6] * 6
    assert loaded["month"].dt.strftime("%Y-%m").unique().tolist() == [f"2026-{m:02d}" for m in range(1, 7)]
    assert not loaded.duplicated(["month", "category"]).any()
    raw = pd.read_csv(sample, dtype="string")
    assert raw["budget_amount"].str.fullmatch(r"[0-9]+\.[0-9]{2}").all()


@pytest.mark.parametrize("content", [
    b"", b"month,category,budget_amount\n", b"month,category\n2026-01,Rent\n",
    b"month,category,budget_amount,extra\n2026-01,Rent,2.00,x\n",
    b"month,category,budget_amount,budget_amount\n2026-01,Rent,2.00,2.00\n",
    b'month,category,budget_amount\n2026-01,"broken\n',
    b"month,category,budget_amount\n2026-01,Rent,2.00,unexpected\n",
    BUDGET_CSV + b"2026-01,Marketing,20.00\n",
    BUDGET_CSV.replace(b"100.00", b"-1.00"),
    BUDGET_CSV.replace(b"100.00", b"inf"),
    BUDGET_CSV.replace(b"100.00", b"NaN"),
    BUDGET_CSV.replace(b"100.00", b"12.345"),
    BUDGET_CSV.replace(b"100.00", b""),
    BUDGET_CSV.replace(b"Marketing", b"Unknown"),
    BUDGET_CSV.replace(b"Marketing", b"Service Revenue"),
    BUDGET_CSV.replace(b"2026-01", b"2026-13"),
    BUDGET_CSV.replace(b"2026-01", b"2026-1"),
    BUDGET_CSV.replace(b"2026-01", b"2026-01-01"),
])
def test_invalid_budget_csv(content):
    with pytest.raises(ValueError) as error:
        load_budgets(BytesIO(content))
    assert str(error.value)


def test_whitespace_duplicate_and_input_preservation():
    raw = pd.read_csv(BytesIO(BUDGET_CSV), dtype="string")
    original = raw.copy(deep=True)
    validate_budgets(raw)
    assert_frame_equal(raw, original)
    duplicate = pd.concat([raw, raw.iloc[[0]].assign(category=" Marketing ")])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_budgets(duplicate)


def test_correct_monthly_actuals_and_variances(transactions, budgets):
    # January expenses: Marketing 80+50, Rent 40, Software 10, Salaries 30.
    # Income 999 and February Marketing 70 must not enter this comparison.
    result = calculate_budget_comparison(transactions, budgets, "2026-01").set_index("category")
    assert result["actual"].to_dict() == {
        "Marketing": 130.0, "Rent": 40.0, "Salaries": 30.0,
        "Software": 10.0, "Supplies": 0.0, "Utilities": 0.0,
    }
    assert result.loc["Marketing", "variance"] == 30.0
    assert result.loc["Marketing", "variance_pct"] == 30.0
    assert result.loc["Marketing", "status"] == "Over budget"
    assert result.loc["Rent", "variance"] == -20.0
    assert result.loc["Rent", "variance_pct"] == pytest.approx(-33.33)
    assert result.loc["Rent", "status"] == "Under budget"
    assert result.loc["Utilities", "variance"] == -25.0
    assert result.loc["Utilities", "variance_pct"] == -100.0
    assert "Service Revenue" not in result.index


def test_zero_budgets(transactions, budgets):
    result = calculate_budget_comparison(transactions, budgets, "2026-01").set_index("category")
    assert result.loc["Supplies", "variance"] == 0.0
    assert result.loc["Supplies", "status"] == "On budget"
    assert pd.isna(result.loc["Supplies", "variance_pct"])
    assert result.loc["Software", "variance"] == 10.0
    assert result.loc["Software", "status"] == "Over budget"
    assert pd.isna(result.loc["Software", "variance_pct"])


def test_missing_budget_is_not_zero(transactions, budgets):
    comparison = calculate_budget_comparison(transactions, budgets, "2026-01")
    salary = comparison.set_index("category").loc["Salaries"]
    assert salary["actual"] == 30.0
    assert salary["status"] == "No budget set"
    assert salary[["budget", "variance", "variance_pct"]].isna().all()
    totals = summarize_budget_comparison(comparison)
    assert totals["budget"] == 185.0
    assert totals["actual"] == 210.0
    assert pd.isna(totals["variance"])


def test_month_and_category_filter(transactions, budgets):
    result = calculate_budget_comparison(transactions, budgets, "2026-02", ["Marketing"])
    assert result["category"].tolist() == ["Marketing"]
    assert result["budget"].tolist() == [200.0]
    assert result["actual"].tolist() == [70.0]
    assert result["variance"].tolist() == [-130.0]
    assert result["variance_pct"].tolist() == [-65.0]
    assert summarize_budget_comparison(result) == {"budget": 200.0, "actual": 70.0, "variance": -130.0}


def test_empty_selection_and_no_budgets(transactions, budgets):
    empty = calculate_budget_comparison(transactions, budgets, "2026-01", [])
    assert empty.empty
    assert summarize_budget_comparison(empty) == {"budget": 0.0, "actual": 0.0, "variance": 0.0}
    unbudgeted = calculate_budget_comparison(transactions, budgets.iloc[:0], "2026-01")
    assert unbudgeted["status"].eq("No budget set").all()
    assert pd.isna(summarize_budget_comparison(unbudgeted)["budget"])
    assert budget_actual_chart(empty).layout.annotations


@pytest.mark.parametrize("month", ["2026-13", "2026-00", "2026-1", "2026-01-01"])
def test_invalid_comparison_month(transactions, budgets, month):
    with pytest.raises(ValueError, match="month"):
        calculate_budget_comparison(transactions, budgets, month)


def test_inputs_not_modified(transactions, budgets):
    original_transactions, original_budgets = transactions.copy(deep=True), budgets.copy(deep=True)
    comparison = calculate_budget_comparison(transactions, budgets, "2026-01")
    original_result = comparison.copy(deep=True)
    summarize_budget_comparison(comparison)
    figure = budget_actual_chart(comparison)
    assert list(figure.data[0].y[:2]) == [100.0, 60.0]
    assert pd.isna(figure.data[0].y[2])  # Salaries has no budget, not a zero bar.
    assert figure.to_json()
    assert_frame_equal(comparison, original_result)
    assert_frame_equal(transactions, original_transactions)
    assert_frame_equal(budgets, original_budgets)


def page():
    return AppTest.from_file(ROOT / "app.py", default_timeout=15).run()


def budget_metrics(app):
    return {metric.label: metric.value for metric in app.metric if metric.label in (
        "Total Budget", "Actual Expenses", "Budget Variance",
    )}


def test_sample_budget_page_and_independent_filters():
    app = page()
    expected = {"Total Budget": "€5,980.00", "Actual Expenses": "€5,591.04", "Budget Variance": "€-388.96"}
    assert not app.exception
    assert budget_metrics(app) == expected
    app.date_input(key="date_range").set_value((date(2026, 2, 1), date(2026, 2, 2))).run()
    app.multiselect(key="categories").set_value([]).run()
    app.multiselect(key="transaction_types").set_value(["Income"]).run()
    assert not app.exception
    assert budget_metrics(app) == expected
    app.multiselect(key="budget_categories").set_value(["Rent"]).run()
    assert budget_metrics(app) == {"Total Budget": "€650.00", "Actual Expenses": "€650.00", "Budget Variance": "€0.00"}
    app.selectbox(key="budget_month").set_value("2026-02").run()
    assert not app.exception
    assert budget_metrics(app)["Actual Expenses"] == "€650.00"


def test_uploaded_transactions_never_automatically_use_sample_budgets():
    app = page()

    def uploads(label, **kwargs):
        return BytesIO(TRANSACTIONS) if label == "Upload transactions" else None

    with patch("streamlit.file_uploader", side_effect=uploads):
        app.radio(key="dataset_selection").set_value("Upload CSV").run()
        assert not app.exception
        assert app.radio(key="budget_source").value == "Upload budget CSV"
        assert not budget_metrics(app)
        app.radio(key="budget_source").set_value("Sample budget").run()
        assert not app.exception
        assert budget_metrics(app)["Total Budget"] == "€5,980.00"
        assert any("explicitly selected" in info.value for info in app.info)


def test_budget_upload_missing_coverage_and_invalid_recovery():
    app = page()

    def uploads(label, **kwargs):
        return BytesIO(TRANSACTIONS if label == "Upload transactions" else BUDGET_CSV)

    with patch("streamlit.file_uploader", side_effect=uploads):
        app.radio(key="dataset_selection").set_value("Upload CSV").run()
        assert not app.exception
        assert budget_metrics(app) == {"Total Budget": "€185.00", "Actual Expenses": "€210.00", "Budget Variance": "N/A"}
        table = next(frame.value for frame in app.dataframe if "Status" in frame.value)
        assert "No budget set" in table["Status"].tolist()
        assert table.loc[table["Category"].eq("Salaries"), "Budget (€)"].item() == "N/A"

    with patch("streamlit.file_uploader", side_effect=lambda label, **kwargs: BytesIO(
        TRANSACTIONS if label == "Upload transactions" else b"bad,budget\n1,2\n"
    )):
        app.run()
        assert not app.exception
        assert any("Could not load budgets" in error.value for error in app.error)
        assert not budget_metrics(app)
        assert len(app.dataframe[-1].value) == 7  # Explorer still available.
    with patch("streamlit.file_uploader", side_effect=uploads):
        app.run()
        assert not app.exception
        assert budget_metrics(app)["Actual Expenses"] == "€210.00"


def test_budget_empty_categories():
    app = page()
    app.multiselect(key="budget_categories").set_value([]).run()
    assert not app.exception
    assert not budget_metrics(app)
    assert len(app.dataframe[-1].value) == 200


def test_new_transaction_dataset_requires_fresh_budget_selection():
    app = page()
    budget_upload_keys = []

    def initial_uploads(label, **kwargs):
        if label == "Upload transactions":
            return BytesIO(TRANSACTIONS)
        budget_upload_keys.append(kwargs["key"])
        return BytesIO(BUDGET_CSV)

    with patch("streamlit.file_uploader", side_effect=initial_uploads):
        app.radio(key="dataset_selection").set_value("Upload CSV").run()
        first_key = budget_upload_keys[-1]
        app.multiselect(key="budget_categories").set_value(["Rent"]).run()
        app.radio(key="budget_source").set_value("Sample budget").run()

    replacement = b"date,description,category,type,amount\n2026-02-01,Office,Rent,Expense,70.00\n"

    def replacement_uploads(label, **kwargs):
        if label == "Upload transactions":
            return BytesIO(replacement)
        budget_upload_keys.append(kwargs["key"])
        return None

    with patch("streamlit.file_uploader", side_effect=replacement_uploads):
        app.run()
    assert not app.exception
    assert app.radio(key="budget_source").value == "Upload budget CSV"
    assert app.selectbox(key="budget_month").value == "2026-02"
    assert len(app.multiselect(key="budget_categories").value) == 6
    assert budget_upload_keys[-1] != first_key
    assert not budget_metrics(app)
