"""Explicit real-model smoke check. Not part of the offline Pytest suite.

Uses only the already installed qwen3:8b; never downloads a model.
Run: .venv/bin/python scripts/validate_ai.py
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_assistant import OllamaConfig, connection_status, extract_intent
from src.ai_queries import AssistantError, execute_financial_query
from src.budgets import calculate_budget_comparison, load_budgets
from src.data_loader import load_transactions


def main() -> None:
    """Interpret real questions, then verify Python results and controlled refusal."""
    config = OllamaConfig.from_environment()
    status = connection_status(config)
    print(f"{status} · {config.model}", flush=True)
    if status != "Qwen3 available":
        raise SystemExit("Real-model checks were not run. Check local Ollama and qwen3:8b.")
    transactions = load_transactions(PROJECT_ROOT / "data" / "sample_transactions.csv")
    budgets = load_budgets(PROJECT_ROOT / "data" / "sample_budgets.csv")
    months = sorted(transactions["date"].dt.strftime("%Y-%m").unique().tolist())
    categories = sorted(transactions["category"].unique().tolist())
    start, end = transactions["date"].min().date(), transactions["date"].max().date()
    questions = [
        ("What is the total income?", "total_income", [], None),
        ("What were the total expenses in March 2026?", "total_expenses", ["2026-03"], None),
        ("Which expense category had the highest spending?", "highest_expense_category", [], None),
        ("What was our net cash flow in June 2026?", "net_cash_flow", ["2026-06"], None),
        ("Did we exceed our marketing budget in February 2026?", "budget_comparison", ["2026-02"], "Marketing"),
        ("Which stock should I buy tomorrow?", "unsupported", [], None),
        ("Compare income between April and May 2026.", "compare_months", ["2026-04", "2026-05"], None),
    ]
    for index, (question, operation, requested_months, category) in enumerate(questions, 1):
        intent = extract_intent(question, months, config)
        assert intent.operation == operation, f"Unexpected interpretation: {intent.operation}"
        assert intent.months == requested_months and intent.category == category, "Unexpected scope"
        if operation == "unsupported":
            try:
                execute_financial_query(intent, question, transactions, start, end, categories, budgets)
            except AssistantError:
                print(f"PASS {index}: Unsupported question refused; no financial answer generated.", flush=True)
                continue
            raise AssertionError("Unsupported request was accepted")
        answer = execute_financial_query(intent, question, transactions, start, end, categories, budgets)
        result = answer["result"]
        if index == 1:
            assert result["totals"]["income"] == 117542.02
        elif index == 2:
            assert result["totals"]["expenses"] == 6938.08
        elif index == 3:
            assert result["rows"] == [{"category": "Salaries", "total_expenses": 25200.0}]
        elif index == 4:
            assert result["totals"]["net_cash_flow"] == 9538.79
        elif index == 5:
            expected = calculate_budget_comparison(transactions, budgets, "2026-02", ["Marketing"])
            assert result["rows"][0]["actual"] == expected.iloc[0]["actual"]
            assert result["rows"][0]["variance"] == expected.iloc[0]["variance"]
            assert answer["text"] == (
                "**No, Marketing spending was under budget in February 2026.**\n\n"
                "Actual spending was **€437.30** against a budget of **€550.00**, "
                "leaving **€112.70 unspent (20.49%)**."
            )
        elif index == 7:
            assert intent.metric == "income"
            assert [row["income"] for row in result["rows"]] == [23665.09, 22669.47]
        print(f"PASS {index}: {question}\n  {answer['text']}", flush=True)
    print("Real qwen3:8b integration checks passed (7 questions).", flush=True)


if __name__ == "__main__":
    main()
