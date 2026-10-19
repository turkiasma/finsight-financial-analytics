"""Mocked Qwen extraction and independently verified financial routing tests."""

from datetime import date
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import ollama
import pandas as pd
from pandas.testing import assert_frame_equal
from pydantic import ValidationError
import pytest
from streamlit.testing.v1 import AppTest

from src import ai_assistant, ai_dashboard
from src.ai_assistant import OllamaConfig, connection_status, extract_intent
from src.ai_dashboard import synchronize_history
from src.ai_queries import (
    AssistantError, FinancialIntent, execute_financial_query, explicit_months,
)
from src.budgets import load_budgets
from src.data_loader import CATEGORY_TYPES, load_transactions
from src.ai_wording import format_financial_answer


ROOT = Path(__file__).resolve().parents[1]
TX_CSV = (
    b"date,description,category,type,amount\n"
    b"2026-01-01,Private project description,Service Revenue,Income,100.00\n"
    b"2026-01-31,Templates,Product Sales,Income,50.00\n"
    b"2026-01-15,Office,Rent,Expense,40.00\n"
    b"2026-01-16,Campaign,Marketing,Expense,60.00\n"
    b"2026-01-20,Tools,Software,Expense,10.00\n"
    b"2026-02-01,Project,Service Revenue,Income,300.00\n"
    b"2026-02-10,Office,Rent,Expense,40.00\n"
    b"2026-02-15,Campaign,Marketing,Expense,30.00\n"
    b"2026-03-01,Team,Salaries,Expense,25.00\n"
)
BUDGET_CSV = (
    b"month,category,budget_amount\n"
    b"2026-01,Marketing,50.00\n2026-01,Rent,60.00\n"
    b"2026-01,Software,0.00\n2026-01,Supplies,0.00\n"
    b"2026-01,Utilities,20.00\n2026-02,Marketing,40.00\n"
)


def request(operation="total_income", months=None, category=None, metric=None):
    return FinancialIntent(operation=operation, months=[] if months is None else months,
                           category=category, metric=metric)


@pytest.fixture
def transactions():
    return load_transactions(BytesIO(TX_CSV))


@pytest.fixture
def budgets():
    return load_budgets(BytesIO(BUDGET_CSV))


@pytest.fixture
def run_query(transactions, budgets):
    def run(intent, question, **kwargs):
        options = dict(start=date(2026, 1, 1), end=date(2026, 3, 31),
                       categories=list(CATEGORY_TYPES), budgets=budgets)
        options.update(kwargs)
        return execute_financial_query(intent, question, transactions, **options)
    return run


@pytest.fixture
def client(monkeypatch):
    mocked = Mock()
    mocked.chat.return_value = SimpleNamespace(message=SimpleNamespace(
        content=request().model_dump_json(), thinking="PRIVATE REASONING NEVER DISPLAYED",
    ))
    monkeypatch.setattr(ai_assistant.ollama, "Client", Mock(return_value=mocked))
    return mocked


def test_structured_intent_extraction_and_qwen_configuration(client):
    result = extract_intent("What is the total income?", ["2026-01"], OllamaConfig())
    assert result.operation == "total_income"
    options = client.chat.call_args.kwargs
    assert options["model"] == "qwen3:8b"
    assert options["think"] is False
    assert options["stream"] is False
    assert options["options"]["temperature"] == 0
    assert options["format"]["additionalProperties"] is False
    assert "Private project description" not in json.dumps(options)
    assert "PRIVATE REASONING" not in str(result)
    constructor = ai_assistant.ollama.Client.call_args.kwargs
    assert constructor["timeout"].read == 60.0
    assert constructor["trust_env"] is False


@pytest.mark.parametrize("content", [
    "not JSON", "<think>reasoning</think>{}", "[]", "null", "{}",
    json.dumps({"operation": "execute_sql", "months": [], "category": None, "metric": None}),
    json.dumps({"operation": "total_income", "months": "2026-01", "category": None, "metric": None}),
    json.dumps({"operation": "total_income", "months": [202601], "category": None, "metric": None}),
    json.dumps({"operation": "total_income", "months": [], "category": 5, "metric": None}),
    json.dumps({"operation": "total_income", "months": [], "category": None, "metric": None, "code": "print('bad')"}),
])
def test_invalid_json_or_fields_are_rejected(client, content):
    client.chat.return_value.message.content = content
    with pytest.raises(AssistantError, match="invalid financial request"):
        extract_intent("What is the total income?", ["2026-01"], OllamaConfig())


@pytest.mark.parametrize("changes", [
    {"months": ["2026-13"]}, {"months": ["2026-1"]},
    {"category": "Unknown"}, {"category": "Rent"},
    {"months": ["2026-01", "2026-02"]}, {"metric": "income"},
])
def test_parameter_semantics(changes):
    payload = request().model_dump()
    payload.update(changes)
    with pytest.raises(ValidationError):
        FinancialIntent.model_validate(payload)


@pytest.mark.parametrize("operation, question, key, expected", [
    ("total_income", "What is total income?", "income", 450.0),
    ("total_expenses", "What are total expenses?", "expenses", 205.0),
    ("net_cash_flow", "What is net cash flow?", "net_cash_flow", 245.0),
])
def test_totals(run_query, operation, question, key, expected):
    result = run_query(request(operation), question)
    assert result["result"]["totals"][key] == expected
    assert f"€{expected:,.2f}" in result["text"]


def test_monthly_expenses_and_cash_flow(run_query):
    result = run_query(request("total_expenses", ["2026-01"]), "What were expenses in January 2026?")
    assert result["result"]["totals"]["expenses"] == 110.0
    negative = run_query(request("net_cash_flow", ["2026-03"]), "Net cash flow in March 2026?")
    assert negative["result"]["totals"]["net_cash_flow"] == -25.0
    assert "cash paid exceeded cash received" in negative["text"]
    assert "**-€25.00**" in negative["text"]
    assert "€-" not in negative["text"]
    assert "not accounting net profit" in negative["text"]


def test_highest_category(run_query):
    result = run_query(request("highest_expense_category"), "Which expense category has the highest spending?")
    assert result["result"]["rows"] == [{"category": "Marketing", "total_expenses": 90.0}]


@pytest.mark.parametrize("operation, month", [
    ("highest_income_month", "2026-02"), ("highest_expense_month", "2026-01"),
])
def test_peak_months(run_query, operation, month):
    result = run_query(request(operation), "Which month has the highest income or expenses?")
    assert result["result"]["rows"][0]["month"] == month


def test_income_sources_and_monthly_summary(run_query):
    sources = run_query(request("income_by_category"), "What are the main income sources?")
    assert sources["result"]["rows"] == [
        {"category": "Service Revenue", "total_income": 400.0},
        {"category": "Product Sales", "total_income": 50.0},
    ]
    summary = run_query(request("monthly_summary"), "Summarize monthly financial trends.")
    assert summary["result"]["rows"][0] == {"month": "2026-01", "income": 150.0, "expenses": 110.0, "net_cash_flow": 40.0}


def test_two_month_comparison(run_query):
    result = run_query(request("compare_months", ["2026-01", "2026-02"], metric="income"),
                       "Compare income in January and February 2026.")
    assert [row["income"] for row in result["result"]["rows"]] == [150.0, 300.0]
    assert result["text"] == (
        "Income **increased from €150.00 in January to €300.00 in February 2026**, "
        "an increase of **€150.00**."
    )


@pytest.mark.parametrize("intent, question, expected", [
    (request(), "What is total income?", "Total income for the selected period was **€450.00**."),
    (request("total_expenses", ["2026-01"]), "Expenses in January 2026?",
     "Total expenses in January 2026 were **€110.00**."),
    (request("net_cash_flow", ["2026-03"]), "Net cash flow in March 2026?",
     "Net cash flow in March 2026 was **-€25.00**, meaning cash paid exceeded cash received during that month. This is cash flow, not accounting net profit."),
])
def test_natural_total_wording(run_query, intent, question, expected):
    assert run_query(intent, question)["text"] == expected


@pytest.mark.parametrize("category, conclusion, detail", [
    ("Marketing", "Yes, Marketing spending exceeded the budget", "an overrun of **€10.00 (20.00%)**"),
    ("Rent", "No, Rent spending was under budget", "leaving **€20.00 unspent (33.33%)**"),
    ("Supplies", "No, Supplies spending was on budget", "Both actual spending and the budget were **€0.00**"),
    ("Software", "Yes, Software spending exceeded the budget", "an overrun of **€10.00**"),
    ("Utilities", "No, Utilities spending was under budget", "leaving **€20.00 unspent (100.00%)**"),
])
def test_budget_yes_no_and_readable_variances(run_query, category, conclusion, detail):
    result = run_query(request("budget_comparison", ["2026-01"], category),
                       f"Did we exceed our {category} budget in January 2026?")
    assert result["text"].startswith(f"**{conclusion} in January 2026.**")
    assert detail in result["text"]
    assert "€-" not in result["text"]
    assert "savings" not in result["text"] and "profit" not in result["text"]


def test_on_budget_positive_amount_and_under_question(run_query, budgets):
    exact = budgets.copy()
    exact.loc[exact["category"].eq("Rent"), "budget_amount"] = 40.0
    answer = run_query(request("budget_comparison", ["2026-01"], "Rent"),
                       "Did we exceed our Rent budget in January 2026?", budgets=exact)
    assert answer["text"] == (
        "**No, Rent spending was on budget in January 2026.**\n\n"
        "Actual spending of **€40.00** exactly matched the budget of **€40.00**."
    )
    under = run_query(request("budget_comparison", ["2026-01"], "Rent"),
                      "Were Rent expenses under budget in January 2026?")
    assert under["text"].startswith("**Yes, Rent spending was under budget")


def test_preferred_sample_budget_and_comparison_wording():
    tx = load_transactions(ROOT / "data" / "sample_transactions.csv")
    budgets = load_budgets(ROOT / "data" / "sample_budgets.csv")
    start, end = tx.date.min().date(), tx.date.max().date()
    categories = tx.category.unique().tolist()
    budget = execute_financial_query(
        request("budget_comparison", ["2026-02"], "Marketing"),
        "Did we exceed our Marketing budget in February 2026?", tx, start, end, categories, budgets,
    )
    assert budget["text"] == (
        "**No, Marketing spending was under budget in February 2026.**\n\n"
        "Actual spending was **€437.30** against a budget of **€550.00**, "
        "leaving **€112.70 unspent (20.49%)**."
    )
    comparison = execute_financial_query(
        request("compare_months", ["2026-04", "2026-05"], metric="income"),
        "Compare income between April and May 2026.", tx, start, end, categories,
    )
    assert comparison["text"] == (
        "Income **decreased from €23,665.09 in April to €22,669.47 in May 2026**, "
        "a reduction of **€995.62**."
    )
    assert "%" not in comparison["text"]


@pytest.mark.parametrize("first, second, values, expected", [
    ("2025-12", "2026-01", [100.0, 150.0], "€100.00 in December 2025 to €150.00 in January 2026"),
    ("2026-01", "2026-02", [100.0, 100.0], "unchanged at €100.00 between January and February 2026"),
])
def test_comparison_dates_and_unchanged_values(first, second, values, expected):
    result = {"operation": "compare_months", "rows": [
        {"month": first, "income": values[0]}, {"month": second, "income": values[1]},
    ]}
    original = json.dumps(result)
    answer = format_financial_answer(result, [first, second], "Compare income", "income")
    assert expected in answer
    assert "%" not in answer
    assert json.dumps(result) == original


def test_breakdowns_summary_and_highest_wording(run_query):
    highest = run_query(request("highest_expense_category"), "Which expense category had the highest spending?")
    assert highest["text"] == "**Marketing** was the largest expense category, accounting for **€90.00** during the selected period."
    sources = run_query(request("income_by_category"), "Main income sources?")
    assert sources["text"] == "Income for the selected period came from **Service Revenue** (**€400.00**) and **Product Sales** (**€50.00**)."
    expenses = run_query(request("expenses_by_category"), "Expense category breakdown?")
    assert "Expenses for the selected period comprised **Marketing** (**€90.00**)" in expenses["text"]
    summary = run_query(request("monthly_summary"), "Summarize monthly trends.")
    assert "In **January 2026**, income was **€150.00**, expenses were **€110.00**, and net cash flow was **€40.00**." in summary["text"]
    assert "**-€25.00**" in summary["text"]
    peak = run_query(request("highest_income_month"), "Which month had the highest income?")
    assert peak["text"] == "**February 2026** had the highest recorded income at **€300.00** during the selected period."


def test_overview_and_zero_cash_flow_wording(run_query):
    overview = run_query(request("overview"), "Summarize our financial overview.")
    assert overview["result"]["totals"] == {"income": 450.0, "expenses": 205.0, "net_cash_flow": 245.0}
    assert overview["text"] == (
        "Total income for the selected period was **€450.00** and expenses were **€205.00**. "
        "Net cash flow was **€245.00**, meaning cash received exceeded cash paid; this is cash flow, not accounting net profit."
    )
    zero = format_financial_answer({"operation": "net_cash_flow", "totals": {"net_cash_flow": 0.0}}, [], "Net cash flow?")
    assert "**€0.00**" in zero and "cash received equaled cash paid" in zero


def test_wording_escapes_data_labels():
    label = '[Open](https://example.com) <script>alert("x")</script> **Fake**'
    result = {"operation": "highest_expense_category", "rows": [{"category": label, "total_expenses": 10.0}]}
    answer = format_financial_answer(result, [], "Largest category?")
    assert r"\[Open\]\(https://example\.com\)" in answer
    assert "<script>" not in answer and "&lt;script&gt;" in answer
    assert r"\*\*Fake\*\*" in answer
    assert "**€10.00**" in answer


def test_budget_variance(run_query):
    result = run_query(request("budget_comparison", ["2026-01"], "Marketing"),
                       "Did we exceed our Marketing budget in January 2026?")
    assert result["result"]["rows"] == [{
        "category": "Marketing", "budget": 50.0, "actual": 60.0,
        "variance": 10.0, "variance_pct": 20.0, "status": "Over budget",
    }]


def test_over_budget_categories_and_under_budget(run_query):
    result = run_query(request("over_budget_categories", ["2026-01"]), "Which categories were over budget in January 2026?")
    assert "**Marketing** (**€10.00** over)" in result["text"]
    assert "**Software** (**€10.00** over)" in result["text"]
    assert "**Rent**" not in result["text"]
    under = run_query(request("budget_comparison", ["2026-01"], "Rent"), "Compare Rent budget in January 2026.")
    assert under["result"]["rows"][0]["variance"] == -20.0
    assert under["result"]["rows"][0]["status"] == "Under budget"


@pytest.mark.parametrize("category, status, actual", [("Software", "Over budget", 10.0), ("Supplies", "On budget", 0.0)])
def test_zero_budget(run_query, category, status, actual):
    result = run_query(request("budget_comparison", ["2026-01"], category), f"{category} budget in January 2026?")
    row = result["result"]["rows"][0]
    assert row["budget"] == 0.0
    assert row["actual"] == actual
    assert row["status"] == status
    assert row["variance_pct"] is None
    assert "a percentage variance is undefined" in result["text"]
    assert "%" not in result["text"]


def test_missing_budget_and_missing_budget_source(run_query):
    result = run_query(request("budget_comparison", ["2026-03"], "Salaries"), "Salaries budget in March 2026?")
    row = result["result"]["rows"][0]
    assert row["actual"] == 25.0
    assert row["budget"] is None
    assert row["variance"] is None
    assert "No budget is set for Salaries in March 2026" in result["text"]
    with pytest.raises(AssistantError, match="matching budget CSV"):
        run_query(request("budget_comparison", ["2026-01"], "Rent"), "Rent budget in January 2026?", budgets=None)


def test_missing_month_and_category(run_query):
    with pytest.raises(AssistantError, match="No transaction records.*2026-09"):
        run_query(request("total_expenses", ["2026-09"]), "Expenses in September 2026?")
    with pytest.raises(AssistantError, match="No records.*Utilities"):
        run_query(request("total_expenses", category="Utilities"), "What are Utilities expenses?")


def test_sidebar_scope_and_explicit_overrides(run_query):
    january = dict(start=date(2026, 1, 1), end=date(2026, 1, 31), categories=["Rent"])
    result = run_query(request("total_expenses"), "Total expenses?", **january)
    assert result["result"]["totals"]["expenses"] == 40.0
    explicit_category = run_query(request("total_expenses", category="Marketing"), "Marketing expenses?", **january)
    assert explicit_category["result"]["totals"]["expenses"] == 60.0
    explicit_month = run_query(request("total_expenses", ["2026-02"]), "Expenses in February 2026?", **january)
    assert explicit_month["result"]["totals"]["expenses"] == 40.0
    partial = run_query(request("total_income"), "Total income?", start=date(2026, 1, 1), end=date(2026, 1, 15))
    assert partial["result"]["totals"]["income"] == 100.0


def test_budget_month_override_never_prorates(run_query):
    result = run_query(request("budget_comparison", ["2026-01"], "Marketing"), "Marketing budget January 2026?",
                       start=date(2026, 1, 1), end=date(2026, 1, 2))
    assert result["result"]["rows"][0]["actual"] == 60.0
    assert result["result"]["rows"][0]["budget"] == 50.0
    with pytest.raises(ValidationError):
        request("budget_comparison")


def test_unmentioned_parameters_cannot_override_filters(run_query):
    with pytest.raises(AssistantError, match="months do not match"):
        run_query(request("total_income", ["2026-02"]), "Total income?")
    with pytest.raises(AssistantError, match="category does not match"):
        run_query(request("total_expenses", category="Rent"), "Total expenses?")
    with pytest.raises(AssistantError, match="months do not match"):
        run_query(request("total_expenses"), "What are expenses in March 2026?")


def test_empty_scope_and_missing_month_category_intersection(run_query):
    with pytest.raises(AssistantError, match="No transaction records"):
        run_query(request("total_income"), "Total income?", categories=[])
    with pytest.raises(AssistantError, match="no transactions within the selected categories"):
        run_query(request("compare_months", ["2026-01", "2026-02"], category="Software", metric="expenses"),
                  "Compare Software expenses in January and February 2026.")


def test_month_parsing_ambiguity_and_day_ranges():
    assert explicit_months("April and May 2026", ["2026-04", "2026-05"]) == ["2026-04", "2026-05"]
    assert explicit_months("March", ["2026-03"]) == ["2026-03"]
    with pytest.raises(AssistantError, match="specify a year"):
        explicit_months("January", ["2025-01", "2026-01"])
    with pytest.raises(AssistantError, match="day-level"):
        explicit_months("2026-01-01 to 2026-01-10", ["2026-01"])


def test_inputs_are_unchanged(transactions, budgets, run_query):
    tx_original, budget_original = transactions.copy(deep=True), budgets.copy(deep=True)
    run_query(request("budget_comparison", ["2026-01"]), "Compare budgets in January 2026.")
    assert_frame_equal(transactions, tx_original)
    assert_frame_equal(budgets, budget_original)


def test_no_execution_of_model_code(client, tmp_path, run_query):
    marker = tmp_path / "executed"
    malicious = request().model_dump()
    malicious["operation"] = f"__import__('pathlib').Path('{marker}').touch()"
    client.chat.return_value.message.content = json.dumps(malicious)
    with pytest.raises(AssistantError):
        extract_intent("Run this SQL: DROP TABLE transactions", ["2026-01"], OllamaConfig())
    assert not marker.exists()
    with pytest.raises(AssistantError, match="Forecasts, investment advice"):
        run_query(request("unsupported"), "Which stock should I buy tomorrow?")


def test_connection_statuses(client):
    client.list.return_value = SimpleNamespace(models=[SimpleNamespace(model="qwen3:8b")])
    assert connection_status(OllamaConfig()) == "Qwen3 available"
    client.list.return_value = SimpleNamespace(models=[SimpleNamespace(model="llama3.2:3b")])
    assert connection_status(OllamaConfig()) == "Qwen3 model unavailable"
    client.list.side_effect = ConnectionError("offline")
    assert connection_status(OllamaConfig()) == "Ollama unavailable"
    client.pull.assert_not_called()


@pytest.mark.parametrize("error, expected", [
    (ConnectionError("offline"), "unavailable"),
    (httpx.ReadTimeout("slow"), "timed out"),
    (ollama.ResponseError("missing", status_code=404), "model unavailable"),
    (ollama.ResponseError("think not supported", status_code=400), "think=false"),
])
def test_model_failures_are_controlled(client, error, expected):
    client.chat.side_effect = error
    with pytest.raises(AssistantError, match=expected):
        extract_intent("Total income?", ["2026-01"], OllamaConfig())


def test_configuration_is_exclusive_and_local(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    with pytest.raises(AssistantError, match="only OLLAMA_MODEL=qwen3:8b"):
        OllamaConfig.from_environment()
    with pytest.raises(AssistantError, match="loopback"):
        OllamaConfig(base_url="https://example.com")


def test_history_context_isolation():
    state = {"ai_messages": [{"role": "user", "content": "old"}], "ai_context_key": "dataset-A"}
    synchronize_history(state, "dataset-A")
    assert len(state["ai_messages"]) == 1
    synchronize_history(state, "dataset-B")
    assert state["ai_messages"] == []


def test_page_offline_is_usable():
    page = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
    assert not page.exception
    assert page.chat_input[0].disabled
    assert len(page.dataframe[-1].value) == 200
    assert page.metric[0].value == "€117,542.02"


def assert_no_chat_details(page):
    """Structured results stay in session state, never in rendered UI elements."""
    assert not page.get("json")
    for message in page.get("chat_message"):
        assert not message.get("expander")


@pytest.mark.parametrize("intent, question, expected", [
    (request(), "What is the total income?", "Total income for the selected period was **€117,542.02**."),
    (request("total_expenses", ["2026-03"]), "What were expenses in March 2026?", "Total expenses in March 2026 were **€6,938.08**."),
    (request("budget_comparison", ["2026-02"], "Marketing"),
     "Marketing budget in February 2026?", "Marketing spending was under budget in February 2026."),
])
def test_verified_answer_presentation_and_history(monkeypatch, intent, question, expected):
    monkeypatch.setattr(ai_dashboard, "cached_connection_status", lambda config: "Qwen3 available")
    monkeypatch.setattr(ai_dashboard, "extract_intent", Mock(return_value=intent))
    page = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
    page.chat_input[0].set_value(question).run()
    assert not page.exception
    messages = page.get("chat_message")
    assert len(messages) == 2
    assert not messages[0].get("caption")  # User messages are never verified.
    answer = messages[-1]
    assert expected in answer.get("markdown")[0].value
    assert answer.get("markdown")[0].proto.allow_html is False
    assert answer.get("caption")[0].value == "✓ Verified using financial data"
    assert [child.type for child in answer.children.values()] == ["markdown", "caption"]
    assert_no_chat_details(page)
    stored_answer = page.session_state["ai_messages"][-1]
    assert stored_answer["result"]["operation"] == intent.operation
    original_result = stored_answer["result"]

    # A later rerun renders stored answers through the same presentation path.
    page.run()
    assert not page.exception
    assert len(page.get("chat_message")) == 2
    assert page.get("chat_message")[-1].get("caption")[0].value == "✓ Verified using financial data"
    assert page.session_state["ai_messages"][-1]["result"] == original_result
    assert_no_chat_details(page)


def test_unsupported_question_has_no_verification_indicator(monkeypatch):
    monkeypatch.setattr(ai_dashboard, "cached_connection_status", lambda config: "Qwen3 available")
    monkeypatch.setattr(ai_dashboard, "extract_intent", Mock(return_value=request("unsupported")))
    page = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
    page.chat_input[0].set_value("Which stock should I buy?").run()
    assert not page.exception
    assert "result" not in page.session_state["ai_messages"][-1]
    assert not page.get("chat_message")[-1].get("caption")
    assert_no_chat_details(page)
    page.run()
    assert not page.get("chat_message")[-1].get("caption")


def test_page_chat_clear_filters_and_dataset_switch(monkeypatch):
    monkeypatch.setattr(ai_dashboard, "cached_connection_status", lambda config: "Qwen3 available")
    interpreter = Mock(return_value=request())
    monkeypatch.setattr(ai_dashboard, "extract_intent", interpreter)
    page = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
    page.chat_input[0].set_value("What is the total income?").run()
    assert not page.exception
    assert "€117,542.02" in page.session_state["ai_messages"][-1]["content"]
    assert len(page.session_state["ai_messages"]) == 2
    page.button(key="clear_ai_chat").click().run()
    assert page.session_state["ai_messages"] == []
    assert not page.get("chat_message")
    page.chat_input[0].set_value("What is the total income?").run()
    page.multiselect(key="categories").set_value(["Rent"]).run()
    assert page.session_state["ai_messages"] == []
    assert not page.get("chat_message")
    page.session_state["ai_messages"] = [{"role": "user", "content": "old date scope"}]
    page.date_input(key="date_range").set_value((date(2026, 1, 1), date(2026, 1, 31))).run()
    assert not page.exception
    assert page.session_state["ai_messages"] == []
    assert not page.get("chat_message")
    page.session_state["ai_messages"] = [{"role": "user", "content": "old dataset"}]
    with patch("streamlit.file_uploader", side_effect=lambda label, **kwargs: BytesIO(TX_CSV) if label == "Upload transactions" else None):
        page.radio(key="dataset_selection").set_value("Upload CSV").run()
    assert not page.exception
    assert page.session_state["ai_messages"] == []
    assert not page.get("chat_message")


def test_page_bad_model_output_is_controlled(monkeypatch):
    monkeypatch.setattr(ai_dashboard, "cached_connection_status", lambda config: "Qwen3 available")
    monkeypatch.setattr(ai_dashboard, "extract_intent", Mock(side_effect=AssistantError("Invalid request; try again.")))
    page = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
    page.chat_input[0].set_value("What is the total income?").run()
    assert not page.exception
    reply = page.session_state["ai_messages"][-1]
    assert reply["content"].startswith("Request not answered:")
    assert "result" not in reply
    assert not page.get("chat_message")[-1].get("caption")
    assert_no_chat_details(page)
    page.run()
    assert not page.exception
    assert not page.get("chat_message")[-1].get("caption")
    assert_no_chat_details(page)
