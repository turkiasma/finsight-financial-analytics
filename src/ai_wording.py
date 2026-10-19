"""Business-facing Markdown templates for verified financial results only."""

from datetime import date
from html import escape
import re


def escape_label(value: str) -> str:
    """Render data labels as literal text, never links, formatting, or raw HTML."""
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~$])", r"\\\1", escape(str(value), quote=False))


def _money(value: float) -> str:
    return f"{'-' if value < 0 else ''}€{abs(value):,.2f}"


def _month(value: str) -> str:
    return date.fromisoformat(value + "-01").strftime("%B %Y")


def _join(values: list[str]) -> str:
    return values[0] if len(values) == 1 else ", ".join(values[:-1]) + " and " + values[-1]


def _budget_prefix(question: str, status: str) -> str:
    """Answer recognizable yes/no budget predicates without reversing their meaning."""
    if not re.match(r"\s*(did|do|does|have|has|is|are|was|were)\b", question, re.I):
        return ""
    if re.search(r"\b(exceed\w*|over|overspend|overspent)\b", question, re.I):
        affirmative = status == "Over budget"
    elif re.search(r"\bunder\b", question, re.I):
        affirmative = status == "Under budget"
    elif re.search(r"\bwithin\b", question, re.I):
        affirmative = status in ("Under budget", "On budget")
    elif re.search(r"\bon budget\b", question, re.I):
        affirmative = status == "On budget"
    else:
        return ""
    return "Yes, " if affirmative else "No, "


def _budget_answer(row: dict, month: str, question: str, single: bool) -> str:
    category = escape_label(row["category"])
    actual = _money(row["actual"])
    if row["budget"] is None:
        return (f"**No budget is set for {category} in {month}.** "
                f"Recorded spending was **{actual}**, so a budget variance cannot be determined.")
    budget = _money(row["budget"])
    status = row["status"]
    prefix = _budget_prefix(question, status) if single else ""
    conclusion = "exceeded the budget" if status == "Over budget" else f"was {status.lower()}"
    opening = f"**{prefix}{category} spending {conclusion} in {month}.**"
    if row["budget"] == 0:
        explanation = (
            f"Actual spending was **{actual}** against a zero budget, an overrun of **{_money(abs(row['variance']))}**; "
            "a percentage variance is undefined."
        ) if row["actual"] > 0 else (
            "Both actual spending and the budget were **€0.00**, so a percentage variance is undefined."
        )
    elif status == "On budget":
        explanation = f"Actual spending of **{actual}** exactly matched the budget of **{budget}**."
    else:
        percentage = "" if row["variance_pct"] is None else f" ({abs(row['variance_pct']):.2f}%)"
        difference = _money(abs(row["variance"]))
        ending = (f"leaving **{difference} unspent{percentage}**" if status == "Under budget"
                  else f"an overrun of **{difference}{percentage}**")
        explanation = f"Actual spending was **{actual}** against a budget of **{budget}**, {ending}."
    return opening + "\n\n" + explanation


def format_financial_answer(result: dict, months: list[str], question: str, metric: str | None = None) -> str:
    """Describe computed values without model-generated claims or percentages.

    Month comparisons subtract the two validated monetary outputs solely to
    express their absolute change. Budget percentages are used as supplied by
    the budget engine, without recalculation. Internal results remain unchanged.
    """
    operation = result["operation"]
    period = f"in {_month(months[0])}" if len(months) == 1 else "for the selected period"
    during = f"in {_month(months[0])}" if len(months) == 1 else "during the selected period"
    if "totals" in result:
        totals = result["totals"]
        if operation == "overview":
            beginning = (f"Total income {period} was **{_money(totals['income'])}** "
                         f"and expenses were **{_money(totals['expenses'])}**. ")
        elif operation == "total_income":
            return f"Total income {period} was **{_money(totals['income'])}**."
        elif operation == "total_expenses":
            return f"Total expenses {period} were **{_money(totals['expenses'])}**."
        else:
            beginning = ""
        value = totals["net_cash_flow"]
        meaning = ("cash received exceeded cash paid" if value > 0 else
                   "cash paid exceeded cash received" if value < 0 else "cash received equaled cash paid")
        if beginning:
            return (beginning + f"Net cash flow was **{_money(value)}**, meaning {meaning}; "
                    "this is cash flow, not accounting net profit.")
        timing = "during that month" if len(months) == 1 else "during the selected period"
        flow = f"Net cash flow {period} was **{_money(value)}**, meaning {meaning} {timing}."
        return beginning + flow + " This is cash flow, not accounting net profit."

    rows = result["rows"]
    if operation == "budget_comparison":
        return "\n\n".join(_budget_answer(row, _month(months[0]), question, len(rows) == 1) for row in rows)
    if operation == "over_budget_categories":
        over = [row for row in rows if row["status"] == "Over budget"]
        unknown = [f"**{escape_label(row['category'])}**" for row in rows if row["budget"] is None]
        text = (f"The categories over budget {period} were " + _join([
            f"**{escape_label(row['category'])}** (**{_money(abs(row['variance']))}** over)" for row in over
        ]) + ".") if over else f"No categories with a set budget exceeded their targets {period}."
        if unknown:
            text += " No budget is set for " + _join(unknown) + ", so their budget status cannot be determined."
        return text
    if operation == "compare_months":
        assert metric in ("income", "expenses", "net_cash_flow")
        label = metric.replace("_", " ").capitalize()
        first, second = rows
        first_month = (date.fromisoformat(first["month"] + "-01").strftime("%B")
                       if first["month"][:4] == second["month"][:4] else _month(first["month"]))
        second_month = _month(second["month"])
        change = round(second[metric] - first[metric], 2)
        if change == 0:
            return f"{label} **was unchanged at {_money(first[metric])} between {first_month} and {second_month}**."
        direction, noun = ("increased", "an increase") if change > 0 else ("decreased", "a reduction")
        return (f"{label} **{direction} from {_money(first[metric])} in {first_month} "
                f"to {_money(second[metric])} in {second_month}**, {noun} of **{_money(abs(change))}**.")
    if operation.startswith("highest_") and operation.endswith("_month"):
        metric = "income" if operation == "highest_income_month" else "expenses"
        names = _join([f"**{_month(row['month'])}**" for row in rows])
        verb = "had the highest recorded" if len(rows) == 1 else "were tied for the highest recorded"
        each = " each" if len(rows) > 1 else ""
        return f"{names} {verb} {metric} at **{_money(rows[0][metric])}**{each} during the selected period."
    if operation == "monthly_summary":
        return "\n\n".join(
            f"In **{_month(row['month'])}**, income was **{_money(row['income'])}**, "
            f"expenses were **{_money(row['expenses'])}**, and net cash flow was **{_money(row['net_cash_flow'])}**."
            for row in rows
        )
    names = _join([f"**{escape_label(row['category'])}**" for row in rows])
    if operation == "highest_expense_category":
        if len(rows) == 1:
            return f"{names} was the largest expense category, accounting for **{_money(rows[0]['total_expenses'])}** {during}."
        return f"{names} were tied as the largest expense categories, at **{_money(rows[0]['total_expenses'])}** each {during}."
    income = operation == "income_by_category"
    column = "total_income" if income else "total_expenses"
    items = _join([f"**{escape_label(row['category'])}** (**{_money(row[column])}**)" for row in rows])
    return f"Income {period} came from {items}." if income else f"Expenses {period} comprised {items}."
