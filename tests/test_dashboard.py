"""Focused checks for Phase 3 data scopes, export, charts, and page behavior."""

from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
from streamlit.testing.v1 import AppTest

from src.analytics import (
    calculate_expenses_by_category, calculate_income_by_category,
    calculate_monthly_changes, calculate_monthly_summary,
    calculate_total_income, calculate_total_expenses,
)
from src.charts import (
    expense_category_chart, income_category_chart,
    monthly_cash_flow_chart, monthly_income_expense_chart,
)
from src.dashboard import (
    export_transactions, filter_analysis_scope, filter_explorer,
    financial_highlights, format_monthly_comparison, load_dashboard_dataset,
)


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
UPLOAD = (
    b"date,description,category,type,amount\n"
    b"2026-01-01,Project,Service Revenue,Income,100.00\n"
    b"2026-01-15,Office,Rent,Expense,40.00\n"
    b"2026-02-01,Templates,Product Sales,Income,150.00\n"
    b'2026-02-10,"Tools, monthly",Software,Expense,60.50\n'
)


@pytest.fixture
def transactions():
    return load_dashboard_dataset("Upload CSV", UPLOAD)


def test_sample_selection():
    sample = load_dashboard_dataset("Sample Dataset")
    assert len(sample) == 200
    assert {"Income", "Expense"} == set(sample["type"])


def test_missing_upload_does_not_fall_back_to_sample():
    assert load_dashboard_dataset("Upload CSV") is None


def test_upload_is_validated(transactions):
    assert len(transactions) == 4
    assert transactions["amount"].tolist() == [100.0, 40.0, 150.0, 60.5]


@pytest.mark.parametrize("content", [
    b"", b"description,amount\nBad,20\n",
    UPLOAD.replace(b"100.00", b"-1.00"),
    UPLOAD.replace(b"2026-01-01", b"2026-02-30"),
    UPLOAD.replace(b"Income", b"Transfer"),
    b'date,description,category,type,amount\n2026-01-01,"unclosed\n',
])
def test_invalid_upload_is_rejected(content):
    with pytest.raises(ValueError):
        load_dashboard_dataset("Upload CSV", content)


def test_inclusive_date_and_category_filters(transactions):
    original = transactions.copy(deep=True)
    scope = filter_analysis_scope(
        transactions, date(2026, 1, 15), date(2026, 2, 1), ["Rent", "Product Sales"],
    )
    assert scope["description"].tolist() == ["Office", "Templates"]
    assert_frame_equal(transactions, original)


def test_single_date(transactions):
    scope = filter_analysis_scope(transactions, date(2026, 1, 15), date(2026, 1, 15), ["Rent"])
    assert scope["amount"].tolist() == [40.0]


def test_reversed_dates(transactions):
    with pytest.raises(ValueError, match="Start date"):
        filter_analysis_scope(transactions, date(2026, 2, 1), date(2026, 1, 1), ["Rent"])


@pytest.mark.parametrize("categories, start, end", [
    ([], date(2026, 1, 1), date(2026, 2, 28)),
    (["Rent"], date(2026, 3, 1), date(2026, 3, 2)),
])
def test_empty_filtered_scope(transactions, categories, start, end):
    result = filter_analysis_scope(transactions, start, end, categories)
    assert result.empty
    assert list(result.columns) == list(transactions.columns)
    assert calculate_total_income(result) == 0.0
    assert calculate_total_expenses(result) == 0.0


def test_explorer_type_filter_leaves_kpi_scope_unchanged(transactions):
    scope = filter_analysis_scope(transactions, date(2026, 1, 1), date(2026, 2, 28),
                                  transactions["category"].tolist())
    original = scope.copy(deep=True)
    explorer = filter_explorer(scope, ["Expense"])
    assert explorer["description"].tolist() == ["Tools, monthly", "Office"]
    assert calculate_total_income(scope) == 250.0
    assert calculate_total_expenses(scope) == 100.5
    assert_frame_equal(scope, original)
    assert filter_explorer(scope, []).empty


def test_export_matches_filtered_explorer_and_round_trips(transactions):
    explorer = filter_explorer(transactions, ["Expense"])
    original = explorer.copy(deep=True)
    exported = export_transactions(explorer)
    assert exported.decode("utf-8") == (
        'date,description,category,type,amount\n'
        '2026-02-10,"Tools, monthly",Software,Expense,60.50\n'
        '2026-01-15,Office,Rent,Expense,40.00\n'
    )
    assert_frame_equal(load_dashboard_dataset("Upload CSV", exported), explorer)
    assert_frame_equal(explorer, original)


def test_empty_export_is_header_only(transactions):
    assert export_transactions(transactions.iloc[:0]) == b"date,description,category,type,amount\n"


@pytest.mark.parametrize("chart, aggregation", [
    (monthly_income_expense_chart, calculate_monthly_summary),
    (monthly_cash_flow_chart, calculate_monthly_summary),
    (expense_category_chart, calculate_expenses_by_category),
    (income_category_chart, calculate_income_by_category),
])
@pytest.mark.parametrize("empty", [False, True])
def test_chart_helpers(transactions, chart, aggregation, empty):
    data = aggregation(transactions.iloc[:0] if empty else transactions)
    original = data.copy(deep=True)
    figure = chart(data)
    assert figure.to_json()
    if empty:
        assert "No transactions" in figure.layout.annotations[0].text
    assert_frame_equal(data, original)


def test_chart_values_use_analytics_outputs(transactions):
    monthly = calculate_monthly_summary(transactions)
    bars = monthly_income_expense_chart(monthly)
    assert list(bars.data[0].y) == [100.0, 150.0]
    assert list(bars.data[1].y) == [40.0, 60.5]
    expenses = expense_category_chart(calculate_expenses_by_category(transactions))
    assert list(expenses.data[0].y) == ["Software", "Rent"]
    assert list(expenses.data[0].x) == [60.5, 40.0]


def test_cash_flow_chart_does_not_connect_missing_months(transactions):
    summary = calculate_monthly_summary(transactions)
    summary.loc[1, "month"] = pd.Timestamp("2026-03-01")
    figure = monthly_cash_flow_chart(summary)
    assert len(figure.data[0].x) == 3
    assert pd.isna(figure.data[0].y[1])
    assert figure.data[0].connectgaps is False


def test_comparison_and_highlights(transactions):
    changes = calculate_monthly_changes(transactions)
    original = changes.copy(deep=True)
    display = format_monthly_comparison(changes)
    assert display.loc[0, "Income Change (%)"] == "N/A"
    assert display.loc[1, "Income Change (%)"] == "+50.00%"
    assert display.loc[0, "Total Income"] == "€100.00"
    highlights = financial_highlights(changes, calculate_expenses_by_category(transactions))
    assert "Highest monthly income: February 2026 (€150.00)." in highlights
    assert "Largest expense category: Software (€60.50)." in highlights
    assert "Income increased by 50.00% from January 2026 to February 2026." in highlights
    assert_frame_equal(changes, original)


def test_empty_and_undefined_highlights(transactions):
    empty = transactions.iloc[:0]
    assert financial_highlights(calculate_monthly_changes(empty), calculate_expenses_by_category(empty)) == [
        "No financial highlights are available for the current selection."
    ]
    expense_only = transactions.loc[transactions["type"].eq("Expense")]
    messages = financial_highlights(calculate_monthly_changes(expense_only), calculate_expenses_by_category(expense_only))
    assert not any("Highest monthly income" in message for message in messages)
    assert "Latest income comparison is unavailable" in messages[-1]


def test_highlight_does_not_confuse_rounded_change_with_unchanged_income(transactions):
    modified = transactions.copy()
    modified.loc[modified["type"].eq("Income"), "amount"] = [10000.0, 10000.01]
    messages = financial_highlights(calculate_monthly_changes(modified), calculate_expenses_by_category(modified))
    assert "Income increased by less than 0.01%" in messages[-1]


def app():
    return AppTest.from_file(APP_PATH, default_timeout=15).run()


def test_page_sample_render_type_scope_and_reset():
    page = app()
    assert not page.exception
    original_metrics = [metric.value for metric in page.metric]
    assert original_metrics == ["€117,542.02", "€36,013.80", "€81,528.22"]
    assert len(page.dataframe[-1].value) == 200
    page.multiselect(key="transaction_types").set_value(["Expense"]).run()
    assert not page.exception
    assert [metric.value for metric in page.metric] == original_metrics
    assert set(page.dataframe[-1].value["type"]) == {"Expense"}
    page.multiselect(key="categories").set_value(["Rent"]).run()
    assert [metric.value for metric in page.metric] == ["€0.00", "€3,900.00", "€-3,900.00"]
    page.button[0].click().run()
    assert not page.exception
    assert [metric.value for metric in page.metric] == original_metrics
    assert page.multiselect(key="transaction_types").value == ["Income", "Expense"]
    assert len(page.dataframe[-1].value) == 200


def test_page_empty_categories_and_incomplete_dates():
    page = app()
    page.multiselect(key="categories").set_value([]).run()
    assert not page.exception
    assert [metric.value for metric in page.metric] == ["€0.00"] * 3
    assert page.dataframe[-1].value.empty
    assert any("No transactions match" in info.value for info in page.info)
    page.date_input(key="date_range").set_value((date(2026, 1, 1),)).run()
    assert not page.exception
    assert not page.metric
    assert any("Select both" in info.value for info in page.info)


@pytest.mark.parametrize("selection", [
    None,
    date(2026, 1, 15),
    (),
    (date(2026, 1, 15),),
    (date(2026, 1, 15), None),
    (None, date(2026, 1, 15)),
])
def test_page_incomplete_date_return_states(selection):
    from streamlit import date_input

    page = app()
    # Exercise the actual app guard for every return shape, including the scalar
    # reported in manual testing, without relying on AppTest's tuple conversion.
    original_range = page.date_input(key="date_range").value

    def date_input_returning_selection(*args, **kwargs):
        # Keep the real widget registered so Streamlit does not clean up its
        # state as an absent widget at the end of this mocked run.
        date_input(*args, **kwargs)
        return selection

    with patch("streamlit.date_input", side_effect=date_input_returning_selection):
        page.run()
    assert not page.exception
    assert any("Select both a start and an end date" in info.value for info in page.info)
    assert not page.metric
    assert not page.dataframe
    # The guard does not fill in dates or overwrite the widget's selection.
    assert page.session_state["date_range"] == original_range


def test_page_complete_date_range_after_incomplete_selection():
    page = app()
    # February has known, independently verified Phase 2 sample totals.
    page.date_input(key="date_range").set_value((date(2026, 2, 1),)).run()
    assert not page.exception
    assert not page.metric
    selected_range = (date(2026, 2, 1), date(2026, 2, 28))
    page.date_input(key="date_range").set_value(selected_range).run()
    assert not page.exception
    assert [metric.value for metric in page.metric] == ["€17,473.76", "€5,771.91", "€11,701.85"]
    assert len(page.dataframe[-1].value) == 32
    assert page.date_input(key="date_range").value == selected_range
    page.button[0].click().run()
    assert not page.exception
    assert len(page.dataframe[-1].value) == 200


def test_page_upload_prompt():
    page = app()
    page.radio(key="dataset_selection").set_value("Upload CSV").run()
    assert not page.exception
    assert not page.metric
    assert any("Upload a CSV" in info.value for info in page.info)


def test_page_valid_upload_and_dataset_switch_resets_filters():
    page = app()
    page.multiselect(key="categories").set_value(["Rent"]).run()
    with patch("streamlit.file_uploader", return_value=BytesIO(UPLOAD)):
        page.radio(key="dataset_selection").set_value("Upload CSV").run()
        assert not page.exception
        assert [metric.value for metric in page.metric] == ["€250.00", "€100.50", "€149.50"]
        assert len(page.multiselect(key="categories").value) == 4
        assert any("Uploaded dataset" in caption.value for caption in page.caption)
        assert not any("Lumen Digital Studio" in caption.value for caption in page.caption)
        page.multiselect(key="transaction_types").set_value([]).run()
        assert page.dataframe[-1].value.empty
        assert [metric.value for metric in page.metric] == ["€250.00", "€100.50", "€149.50"]
    page.radio(key="dataset_selection").set_value("Sample Dataset").run()
    assert not page.exception
    assert len(page.dataframe[-1].value) == 200


def test_page_invalid_upload_clears_previous_results():
    page = app()
    with patch("streamlit.file_uploader", return_value=BytesIO(b"bad,file\n1,2\n")):
        page.radio(key="dataset_selection").set_value("Upload CSV").run()
    assert not page.exception
    assert page.error
    assert "Missing required columns" in page.error[0].value
    assert not page.metric
    assert not page.dataframe
    with patch("streamlit.file_uploader", return_value=BytesIO(UPLOAD)):
        page.run()
    assert not page.exception
    assert len(page.metric) == 3


def test_page_single_date_upload():
    single_date = b"date,description,category,type,amount\n2026-06-01,Office,Rent,Expense,50.00\n"
    page = app()
    with patch("streamlit.file_uploader", return_value=BytesIO(single_date)):
        page.radio(key="dataset_selection").set_value("Upload CSV").run()
        assert not page.exception
        assert page.date_input[0].value == (date(2026, 6, 1), date(2026, 6, 1))
        assert [metric.value for metric in page.metric] == ["€0.00", "€50.00", "€-50.00"]
        page.button[0].click().run()
        assert not page.exception
        assert len(page.dataframe[-1].value) == 1


def test_replacing_upload_resets_scope_to_new_dataset():
    page = app()
    with patch("streamlit.file_uploader", return_value=BytesIO(UPLOAD)):
        page.radio(key="dataset_selection").set_value("Upload CSV").run()
        page.multiselect(key="categories").set_value(["Rent"]).run()
        page.multiselect(key="transaction_types").set_value(["Expense"]).run()
    replacement = b"date,description,category,type,amount\n2025-12-01,Project,Service Revenue,Income,50.00\n"
    with patch("streamlit.file_uploader", return_value=BytesIO(replacement)):
        page.run()
    assert not page.exception
    assert page.multiselect(key="categories").value == ["Service Revenue"]
    assert page.multiselect(key="transaction_types").value == ["Income", "Expense"]
    assert page.date_input[0].value == (date(2025, 12, 1), date(2025, 12, 1))
    assert [metric.value for metric in page.metric] == ["€50.00", "€0.00", "€50.00"]
