"""Validate a small financial query language and route it to existing analytics.

No model communication or generated code execution belongs in this module.
"""

from calendar import month_abbr, month_name
from datetime import date
from typing import Literal
import json
import re

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.analytics import (
    calculate_expenses_by_category, calculate_income_by_category,
    calculate_monthly_summary, calculate_net_cash_flow,
    calculate_total_expenses, calculate_total_income,
)
from src.budgets import EXPENSE_CATEGORIES, calculate_budget_comparison
from src.dashboard import filter_analysis_scope
from src.data_loader import CATEGORY_TYPES
from src.ai_wording import format_financial_answer


class AssistantError(ValueError):
    """An actionable, safe message that can be presented without a traceback."""


class FinancialIntent(BaseModel):
    """Untrusted model output must match this exact, bounded query language."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    operation: Literal[
        "overview", "total_income", "total_expenses", "net_cash_flow",
        "highest_income_month", "highest_expense_month", "compare_months",
        "income_by_category", "expenses_by_category", "highest_expense_category",
        "monthly_summary", "budget_comparison", "over_budget_categories", "unsupported",
    ]
    months: list[str] = Field(min_length=0, max_length=2, description=(
        "Only calendar months explicitly named in the question. Use [] for overall totals. "
        "Never insert available months or the first/last month to describe a date range."
    ))
    category: str | None = Field(json_schema_extra={"enum": [None, *CATEGORY_TYPES]})
    metric: Literal["income", "expenses", "net_cash_flow"] | None

    @model_validator(mode="after")
    def check_parameters(self) -> "FinancialIntent":
        for month in self.months:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", month):
                raise ValueError("Months must be YYYY-MM.")
            date.fromisoformat(month + "-01")
        if self.category is not None and self.category not in CATEGORY_TYPES:
            raise ValueError("Unknown financial category.")
        if self.operation == "compare_months":
            if len(self.months) != 2 or len(set(self.months)) != 2 or self.metric is None:
                raise ValueError("A comparison needs two different months and a metric.")
        elif self.metric is not None or len(self.months) > 1:
            raise ValueError("Only a two-month comparison accepts a metric or two months.")
        if self.operation in ("highest_income_month", "highest_expense_month", "unsupported") and self.months:
            raise ValueError("This operation does not accept months.")
        if self.operation in ("budget_comparison", "over_budget_categories") and len(self.months) != 1:
            raise ValueError("Budget questions need one explicit calendar month.")
        if self.operation == "unsupported" and self.category is not None:
            raise ValueError("Unsupported requests cannot have parameters.")
        expense_ops = {"total_expenses", "highest_expense_month", "expenses_by_category",
                       "highest_expense_category", "budget_comparison", "over_budget_categories"}
        income_ops = {"total_income", "highest_income_month", "income_by_category"}
        kind = ("Expense" if self.operation in expense_ops else
                "Income" if self.operation in income_ops else None)
        if self.category is not None and kind and CATEGORY_TYPES[self.category] != kind:
            raise ValueError("The category does not match this financial operation.")
        if self.operation == "compare_months" and self.category is not None:
            expected = {"income": "Income", "expenses": "Expense"}.get(self.metric)
            if expected and CATEGORY_TYPES[self.category] != expected:
                raise ValueError("The category does not match the comparison metric.")
        return self


SUPPORTED_QUESTIONS = (
    "Ask about income, expenses, net cash flow, monthly/category summaries, peak "
    "months/categories, a comparison of two named months, or monthly budgets. "
    "Budget questions need a named month. Forecasts, investment advice, arbitrary "
    "date ranges in questions, and conversational follow-ups are not supported."
)


def explicit_months(question: str, available: list[str]) -> list[str]:
    """Resolve explicit English month names/ISO months without inventing a year.

    A yearless month is allowed only when unambiguous in the loaded data or when
    the question specifies one shared year. Unknown or ambiguous months fail.
    """
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", question):
        raise AssistantError("Use sidebar filters for day-level date ranges; ask with calendar months here.")
    found = re.findall(r"\b[0-9]{4}-[0-9]{2}\b", question)
    years = set(re.findall(r"\b(?:19|20|21)[0-9]{2}\b", question))
    names = {name.lower(): index for index in range(1, 13)
             for name in (month_name[index], month_abbr[index])}
    pattern = r"\b(" + "|".join(sorted(names, key=len, reverse=True)) + r")\b(?:\s+([0-9]{4}))?"
    for match in re.finditer(pattern, question, re.IGNORECASE):
        number = names[match[1].lower()]
        if re.match(r"\s+[0-9]{1,2}\b", question[match.end():]):
            raise AssistantError("Use sidebar filters for day-level dates; ask with calendar months here.")
        candidates = [month for month in available if month.endswith(f"-{number:02d}")]
        year = match[2] or (next(iter(years)) if len(years) == 1 else None)
        if year is not None:
            found.append(f"{year}-{number:02d}")
        elif len(candidates) == 1:
            found.append(candidates[0])
        else:
            raise AssistantError(f"Please specify a year for {month_name[number]}; that month is unavailable or ambiguous.")
    if years and not found:
        raise AssistantError("Name a calendar month and year, or use the sidebar dates for a date range.")
    return list(dict.fromkeys(found))


def validate_question_scope(question: str, intent: FinancialIntent, available: list[str]) -> None:
    """Require literal evidence before a model can override the user's filters."""
    named_months = explicit_months(question, available)
    if set(named_months) != set(intent.months):
        raise AssistantError("The interpreted months do not match your question. Please name the month(s) and year explicitly.")
    for month in intent.months:
        if month not in available:
            raise AssistantError(f"No transaction records are available for {month}; no other month was substituted.")
    named_categories = [name for name in CATEGORY_TYPES
                        if re.search(r"\b" + re.escape(name) + r"\b", question, re.IGNORECASE)]
    if len(named_categories) > 1:
        raise AssistantError("Ask about one named category at a time, or request a category breakdown.")
    if named_categories != ([] if intent.category is None else [intent.category]):
        raise AssistantError("The interpreted category does not match your question. Please use its exact category name.")


def _records(frame: pd.DataFrame) -> list[dict]:
    """Serialize verified output, preserving missing values as JSON null."""
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def execute_financial_query(
    intent: FinancialIntent, question: str, transactions: pd.DataFrame,
    start: date, end: date, categories: list[str], budgets: pd.DataFrame | None = None,
) -> dict:
    """Return deterministic answer text plus a verifiable structured result.

    Named months override dates with full calendar months; a named category
    overrides category selection. Otherwise sidebar filters apply. Budgets need
    an explicit full month and use the currently validated budget dataset.
    """
    # Validate again at this public boundary, even if a caller constructed or
    # mutated an object without using Pydantic's normal validation path.
    try:
        intent = FinancialIntent.model_validate(intent.model_dump())
    except (ValueError, AttributeError) as error:
        raise AssistantError("Invalid financial request. " + SUPPORTED_QUESTIONS) from error
    if intent.operation == "unsupported":
        raise AssistantError(SUPPORTED_QUESTIONS)
    available = sorted(transactions["date"].dt.strftime("%Y-%m").unique().tolist())
    validate_question_scope(question, intent, available)
    selected_categories = [intent.category] if intent.category else list(categories)
    budget_query = intent.operation in ("budget_comparison", "over_budget_categories")
    if intent.category and intent.category not in set(transactions["category"]) and not (
        budget_query and budgets is not None and intent.category in set(budgets["category"])
    ):
        raise AssistantError(f"No records are available for category {intent.category}.")
    if intent.months:
        scope = transactions.loc[
            transactions["date"].dt.strftime("%Y-%m").isin(intent.months)
            & transactions["category"].isin(selected_categories)
        ].copy()
        date_label = ", ".join(intent.months) + " (full recorded calendar months)"
    else:
        scope = filter_analysis_scope(transactions, start, end, selected_categories)
        date_label = f"{start.isoformat()} through {end.isoformat()} (inclusive)"
    scope_label = f"Scope: {date_label}; categories: {', '.join(selected_categories) or 'none'}. Currency: EUR."
    operation = intent.operation
    details: dict = {"operation": operation, "scope": scope_label}
    if budget_query:
        if budgets is None:
            raise AssistantError("Select and validate a matching budget CSV in Budget vs. Actual Expenses first.")
        expense_categories = [category for category in selected_categories if category in EXPENSE_CATEGORIES]
        comparison = calculate_budget_comparison(transactions, budgets, intent.months[0], expense_categories)
        if comparison.empty:
            raise AssistantError("No budget or expense records match the requested month and categories.")
        # Full comparison includes unbudgeted categories even for over-budget queries.
        details["rows"] = _records(comparison)
    elif scope.empty:
        raise AssistantError("No transaction records match this question's scope; no values were invented.")
    elif operation in ("overview", "total_income", "total_expenses", "net_cash_flow"):
        totals = {
            "income": calculate_total_income(scope), "expenses": calculate_total_expenses(scope),
            "net_cash_flow": calculate_net_cash_flow(scope),
        }
        key = {"total_income": "income", "total_expenses": "expenses", "net_cash_flow": "net_cash_flow"}.get(operation)
        results = totals if key is None else {key: totals[key]}
        details["totals"] = results
    elif operation in ("monthly_summary", "highest_income_month", "highest_expense_month", "compare_months"):
        summary = calculate_monthly_summary(scope)
        summary["month"] = summary["month"].dt.strftime("%Y-%m")
        if operation.startswith("highest_"):
            metric = "income" if operation == "highest_income_month" else "expenses"
            if summary[metric].max() == 0:
                raise AssistantError(f"No {metric} transactions are recorded in this scope.")
            rows = summary.loc[summary[metric].eq(summary[metric].max())]
        elif operation == "compare_months":
            if not set(intent.months).issubset(set(summary["month"])):
                raise AssistantError("A requested month has no transactions within the selected categories; no zero values were invented.")
            rows = summary.set_index("month").loc[intent.months].reset_index()
        else:
            rows = summary
        details["rows"] = _records(rows)
    else:
        income_query = operation == "income_by_category"
        rows = calculate_income_by_category(scope) if income_query else calculate_expenses_by_category(scope)
        column = "total_income" if income_query else "total_expenses"
        if rows.empty:
            raise AssistantError("No income records in this scope." if income_query else "No expense records in this scope.")
        if operation == "highest_expense_category":
            rows = rows.loc[rows[column].eq(rows[column].max())]
        details["rows"] = _records(rows)
    return {"text": format_financial_answer(details, intent.months, question, intent.metric), "result": details}
