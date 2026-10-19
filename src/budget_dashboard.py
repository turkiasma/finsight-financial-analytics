"""Presentation for the independent monthly budget section of FinSight."""

from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from src.budgets import (
    EXPENSE_CATEGORIES, calculate_budget_comparison, load_budgets,
    summarize_budget_comparison,
)
from src.charts import budget_actual_chart


SAMPLE_BUDGET_PATH = Path(__file__).resolve().parents[1] / "data" / "sample_budgets.csv"


def render_budget_section(transactions: pd.DataFrame, is_sample: bool, dataset_identity: str) -> None:
    """Render monthly controls using the full validated dataset, never analysis scope."""
    st.divider()
    st.subheader("Budget vs. Actual Expenses")
    st.caption("Independent of the sidebar date range, categories, and transaction types. This section uses all recorded expenses for one full calendar month; budgets are never prorated.")
    st.caption("Only months with transaction records are available. Ensure your file contains the complete month: FinSight cannot verify that records are complete.")
    months = sorted(transactions["date"].dt.strftime("%Y-%m").unique().tolist())
    if st.session_state.get("budget_dataset") != dataset_identity:
        st.session_state["budget_source"] = "Sample budget" if is_sample else "Upload budget CSV"
        st.session_state["budget_month"] = months[0]
        st.session_state["budget_categories"] = list(EXPENSE_CATEGORIES)
        st.session_state["budget_dataset"] = dataset_identity
    source = st.radio("Budget source", ["Sample budget", "Upload budget CSV"],
                      key="budget_source", horizontal=True)
    left, right = st.columns(2)
    with left:
        month = st.selectbox("Budget calendar month", months, key="budget_month")
    with right:
        categories = st.multiselect("Budget expense categories", EXPENSE_CATEGORIES, key="budget_categories")
    try:
        if source == "Sample budget":
            st.caption("Lumen Digital Studio · Fictional spending targets · EUR. These targets are not forecasts.")
            if not is_sample:
                st.info("You explicitly selected Lumen Digital Studio's fictional budgets for your uploaded transactions. Confirm these targets are relevant to your comparison.")
            budgets = load_budgets(SAMPLE_BUDGET_PATH)
        else:
            # A new transaction dataset must not inherit another file's budget.
            uploaded = st.file_uploader("Upload monthly budget CSV", type=["csv"],
                                        key=f"budget_upload_{dataset_identity}")
            st.caption("Required columns: month, category, budget_amount. Month: YYYY-MM. EUR budgets must be non-negative, with at most two decimal places. One entry per month/category.")
            if uploaded is None:
                st.info("Upload a matching budget CSV to compare planned and actual expenses. Sample budgets are available only through an explicit selection.")
                return
            budgets = load_budgets(BytesIO(uploaded.getvalue()))
    except (ValueError, OSError) as error:
        st.error(f"Could not load budgets: {error}")
        st.info("Correct the budget file and upload it again. The transaction dashboard remains available.")
        return

    comparison = calculate_budget_comparison(transactions, budgets, month, categories)
    if comparison.empty:
        st.info("No budget or expense records match this month and category selection.")
        return
    totals = summarize_budget_comparison(comparison)
    for column, label, key in zip(st.columns(3),
                                   ["Total Budget", "Actual Expenses", "Budget Variance"],
                                   ["budget", "actual", "variance"]):
        value = totals[key]
        column.metric(label, "N/A" if pd.isna(value) else f"€{value:,.2f}", border=True)
    st.caption("Variance = actual − budget. Positive: over budget; negative: under budget; zero: on budget. Percentages are N/A for zero or missing budgets.")
    if comparison["budget"].isna().any():
        st.info("Some categories have no budget set. Total Budget includes only explicit targets; Actual Expenses includes all selected spending. Overall Budget Variance is N/A until every displayed category has a budget.")
    display = comparison.copy()
    for name in ("budget", "actual", "variance"):
        display[name] = display[name].map(lambda value: "N/A" if pd.isna(value) else f"€{value:,.2f}")
    display["variance_pct"] = display["variance_pct"].map(
        lambda value: "N/A" if pd.isna(value) else f"{value:+.2f}%",
    )
    st.dataframe(display.rename(columns={
        "category": "Category", "budget": "Budget (€)", "actual": "Actual (€)",
        "variance": "Variance (€)", "variance_pct": "Variance (%)", "status": "Status",
    }), hide_index=True, width="stretch")
    st.plotly_chart(budget_actual_chart(comparison), width="stretch", key="budget_actual")
    st.caption("A missing budget has no Budget bar; it is not a zero target. Actual means recorded cash paid, not a forecast or a full accounting expense measure.")
