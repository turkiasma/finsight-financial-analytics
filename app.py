"""FinSight's Streamlit dashboard: streamlit run app.py."""

from datetime import date
from hashlib import sha256

import streamlit as st

from src.budget_dashboard import render_budget_section
from src.ai_dashboard import render_ai_assistant

from src.analytics import (
    calculate_expenses_by_category, calculate_income_by_category,
    calculate_monthly_changes, calculate_monthly_summary,
    calculate_net_cash_flow, calculate_total_expenses, calculate_total_income,
)
from src.charts import (
    expense_category_chart, income_category_chart,
    monthly_cash_flow_chart, monthly_income_expense_chart,
)
from src.dashboard import (
    export_transactions, filter_analysis_scope, filter_explorer,
    financial_highlights, format_monthly_comparison, load_dashboard_dataset,
)


def reset_filters(start: date, end: date, categories: list[str]) -> None:
    """Set widget state before widgets render, including on reset callbacks."""
    st.session_state["date_range"] = (start, end)
    st.session_state["categories"] = categories
    st.session_state["transaction_types"] = ["Income", "Expense"]


def main() -> None:
    """Render validated data, independent analysis/explorer scopes, and exports."""
    st.set_page_config(page_title="FinSight | Business Financial Analytics", page_icon="◈", layout="wide")
    st.markdown("""
        <style>
        .block-container {max-width: 1440px; padding-top: 2rem;}
        [data-testid="stMetric"] {background: #fff; border-top: 3px solid #007F78;
            border-radius: 10px; padding: 1.1rem;}
        </style>
    """, unsafe_allow_html=True)
    st.title("FinSight")
    st.subheader("Business Financial Analytics Dashboard")
    st.write("Transforming business transaction data into clear financial insights.")
    st.caption("Public demonstration: do not upload confidential financial or personal information. In cloud deployments, CSVs are processed on Streamlit servers. Cloud AI receives only your question and limited intent metadata; uploaded records and calculated amounts are not attached.")

    with st.sidebar:
        st.header("FinSight")
        st.caption("A clear view of your business cash flow.")
        selection = st.radio("Dataset", ["Sample Dataset", "Upload CSV"], key="dataset_selection")
        uploaded = None
        if selection == "Upload CSV":
            uploaded = st.file_uploader("Upload transactions", type=["csv"])
            st.caption("UTF-8 CSV · All amounts must be EUR.")
        with st.expander("CSV format & categories"):
            st.write("Required columns: date, description, category, type, amount.")
            st.write("Dates: YYYY-MM-DD. Amounts: positive numbers, up to two decimal places. Types: Income or Expense.")
            st.write("Income: Product Sales, Service Revenue, Subscription Revenue.")
            st.write("Expense: Rent, Salaries, Marketing, Software, Utilities, Supplies.")
            st.caption("Category and type must agree. All records must pass validation.")

    uploaded_bytes = uploaded.getvalue() if uploaded is not None else None
    try:
        transactions = load_dashboard_dataset(selection, uploaded_bytes)
    except (ValueError, OSError) as error:
        st.error(f"Could not load this dataset: {error}")
        st.info("Correct the CSV and upload it again, or choose Sample Dataset.")
        return
    if transactions is None:
        st.info("Upload a CSV using the sidebar to begin. All amounts are assumed to be EUR.")
        return

    is_sample = selection == "Sample Dataset"
    label = "Lumen Digital Studio · Synthetic business transactions" if is_sample else "Uploaded dataset · User-provided transactions"
    st.caption(f"{label}  |  Currency: EUR  |  {len(transactions):,} validated transactions")
    start, end = transactions["date"].min().date(), transactions["date"].max().date()
    categories = sorted(transactions["category"].unique().tolist())
    identity = "sample" if is_sample else sha256(uploaded_bytes).hexdigest()
    if st.session_state.get("active_dataset") != identity:
        reset_filters(start, end, categories)
        st.session_state["active_dataset"] = identity

    with st.sidebar:
        st.divider()
        st.subheader("Analysis scope")
        st.button("Reset filters", key="reset_filters", on_click=reset_filters,
                  args=(start, end, categories), width="stretch")
        dates = st.date_input("Date range", min_value=start, max_value=end,
                              key="date_range", format="YYYY-MM-DD")
        chosen_categories = st.multiselect("Categories", categories, key="categories")
        st.caption("Dates and categories apply to the main KPIs, charts, highlights, and tables. The budget section has independent controls. No categories means no matching transactions.")
        st.subheader("Explorer display")
        types = st.multiselect("Transaction types", ["Income", "Expense"], key="transaction_types")
        st.caption("Transaction types affect only the explorer and its CSV download.")

    # date_input can return a scalar date, None, or an incomplete range.
    # Only two explicitly selected dates define an analysis scope.
    if (
        not isinstance(dates, (tuple, list))
        or len(dates) != 2
        or not all(isinstance(endpoint, date) for endpoint in dates)
    ):
        st.info("Select both a start and an end date to view the analysis.")
        return
    if dates[0] > dates[1]:
        st.warning("Start date must be on or before end date.")
        return
    scope = filter_analysis_scope(transactions, dates[0], dates[1], chosen_categories)
    explorer = filter_explorer(scope, types)

    st.divider()
    st.caption(f"ANALYSIS SCOPE · {dates[0]:%d %b %Y} – {dates[1]:%d %b %Y} · {len(scope):,} transactions")
    st.caption("Date and category filters define this analysis. Transaction types change only the explorer and download.")
    for column, title, function in zip(
        st.columns(3), ("Total Income", "Total Expenses", "Net Cash Flow"),
        (calculate_total_income, calculate_total_expenses, calculate_net_cash_flow),
    ):
        column.metric(title, f"€{function(scope):,.2f}", border=True)
    st.caption("Cash received minus cash paid is net cash flow, not accounting net profit.")
    if scope.empty:
        st.info("No transactions match this date and category selection. Widen the filters or choose Reset filters.")

    monthly = calculate_monthly_summary(scope)
    expenses = calculate_expenses_by_category(scope)
    income = calculate_income_by_category(scope)
    changes = calculate_monthly_changes(scope)

    st.subheader("Monthly financial trends")
    st.caption("Recorded cash activity only. Missing months are not assumed to have zero activity; partial months are not adjusted.")
    if monthly.empty:
        st.info("No monthly activity is available for this selection.")
    else:
        left, right = st.columns(2)
        with left:
            st.plotly_chart(monthly_income_expense_chart(monthly), width="stretch", key="monthly_totals")
        with right:
            st.plotly_chart(monthly_cash_flow_chart(monthly), width="stretch", key="cash_flow")

    st.subheader("Category analysis")
    left, right = st.columns(2)
    with left:
        if expenses.empty:
            st.info("No expense transactions in the current analysis scope.")
        else:
            st.plotly_chart(expense_category_chart(expenses), width="stretch", key="expense_categories")
    with right:
        if income.empty:
            st.info("No income transactions in the current analysis scope.")
        else:
            st.plotly_chart(income_category_chart(income), width="stretch", key="income_categories")

    st.subheader("Monthly comparison")
    st.caption("N/A: first recorded month, zero previous amount, or a gap between calendar months.")
    st.dataframe(format_monthly_comparison(changes), hide_index=True, width="stretch")

    st.subheader("Financial Highlights")
    st.caption("Calculated from the current analysis scope. Ties show the earliest month or alphabetically first category.")
    for highlight in financial_highlights(changes, expenses):
        # Plain text prevents user-provided content being interpreted as markup.
        st.text(highlight)

    budgets = render_budget_section(transactions, is_sample, identity)

    st.divider()
    st.subheader("Transaction Explorer")
    st.caption(f"{len(explorer):,} matching transactions · Date + category + transaction-type filters · Newest first")
    if explorer.empty:
        st.info("No matching transactions. Check the transaction types or reset the filters.")
    st.dataframe(explorer, hide_index=True, width="stretch", column_config={
        "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
        "description": st.column_config.TextColumn("Description"),
        "category": st.column_config.TextColumn("Category"),
        "type": st.column_config.TextColumn("Type"),
        "amount": st.column_config.NumberColumn("Amount (EUR)", format="€%.2f"),
    })
    st.download_button("Download CSV", data=export_transactions(explorer),
                       file_name="finsight_filtered_transactions.csv", mime="text/csv",
                       disabled=explorer.empty, on_click="ignore", type="primary")
    st.caption("Export includes only matching explorer records, in newest-first order, with YYYY-MM-DD dates and two-decimal EUR amounts.")
    render_ai_assistant(transactions, budgets, identity, dates[0], dates[1], chosen_categories)
    st.divider()
    st.caption("FinSight · Cash-based analysis · EUR assumed · Optional financial assistant · No forecasts or investment recommendations.")


if __name__ == "__main__":
    main()
