"""Plotly presentation helpers. Inputs are already aggregated analytics outputs."""

import pandas as pd
import plotly.graph_objects as go


INCOME_COLOR = "#007F78"
EXPENSE_COLOR = "#C05B19"
FLOW_COLOR = "#3157A4"


def _style(figure: go.Figure, title: str, empty: bool) -> go.Figure:
    """Apply a consistent readable style and an explicit empty state."""
    figure.update_layout(
        title={"text": title, "font": {"size": 18}}, template="plotly_white",
        font={"family": "Arial, sans-serif", "color": "#24344A", "size": 13},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 12, "r": 12, "t": 64, "b": 24}, height=360,
        legend={"orientation": "h", "y": 1.12, "x": 0},
    )
    figure.update_xaxes(showgrid=False, automargin=True)
    figure.update_yaxes(gridcolor="#E3E9EF", automargin=True, zerolinecolor="#C7D2DF")
    if empty:
        figure.add_annotation(
            text="No transactions in this selection", x=0.5, y=0.5,
            xref="paper", yref="paper", showarrow=False,
        )
    return figure


def monthly_income_expense_chart(summary: pd.DataFrame) -> go.Figure:
    """Plot chronological monthly income and expenses as grouped bars."""
    ordered = summary.sort_values("month")
    figure = go.Figure()
    for column, label, color in (
        ("income", "Income", INCOME_COLOR), ("expenses", "Expenses", EXPENSE_COLOR),
    ):
        figure.add_bar(
            x=ordered["month"], y=ordered[column], name=label, marker_color=color,
            hovertemplate="%{x|%B %Y}<br>" + label + ": €%{y:,.2f}<extra></extra>",
        )
    figure.update_layout(barmode="group", bargap=0.28)
    figure.update_xaxes(dtick="M1", tickformat="%b %Y", title=None)
    figure.update_yaxes(title="Amount (EUR)", tickprefix="€", tickformat=",.0f")
    return _style(figure, "Monthly income vs expenses", summary.empty)


def monthly_cash_flow_chart(summary: pd.DataFrame) -> go.Figure:
    """Plot recorded monthly cash flow, leaving gaps across absent months."""
    ordered = summary.sort_values("month")
    # Reindex for presentation only: NaN gaps prevent a line suggesting continuity
    # through months with no records. No financial amounts are calculated here.
    series = ordered.set_index("month")["net_cash_flow"]
    if not ordered.empty:
        series = series.reindex(pd.date_range(series.index.min(), series.index.max(), freq="MS"))
    figure = go.Figure(go.Scatter(
        x=series.index, y=series, mode="lines+markers", name="Net Cash Flow",
        line={"color": FLOW_COLOR, "width": 3}, marker={"size": 7}, connectgaps=False,
        hovertemplate="%{x|%B %Y}<br>Net Cash Flow: €%{y:,.2f}<extra></extra>",
    ))
    figure.update_xaxes(dtick="M1", tickformat="%b %Y", title=None)
    figure.update_yaxes(title="Net cash flow (EUR)", tickprefix="€", tickformat=",.0f")
    return _style(figure, "Monthly net cash flow", summary.empty)


def _category_chart(totals: pd.DataFrame, column: str, title: str, color: str) -> go.Figure:
    """Present category totals highest first without performing aggregation."""
    ordered = totals.sort_values([column, "category"], ascending=[False, True])
    figure = go.Figure(go.Bar(
        x=ordered[column], y=ordered["category"], orientation="h", marker_color=color,
        hovertemplate="%{y}<br>€%{x:,.2f}<extra></extra>",
    ))
    figure.update_xaxes(title="Amount (EUR)", tickprefix="€", tickformat=",.0f")
    figure.update_yaxes(autorange="reversed", title=None)
    return _style(figure, title, totals.empty)


def expense_category_chart(totals: pd.DataFrame) -> go.Figure:
    """Display category/total_expenses output as a horizontal bar chart."""
    return _category_chart(totals, "total_expenses", "Where the business spends", EXPENSE_COLOR)


def income_category_chart(totals: pd.DataFrame) -> go.Figure:
    """Display category/total_income output as a horizontal bar chart."""
    return _category_chart(totals, "total_income", "Sources of income", INCOME_COLOR)
