"""Offline provider, privacy, upload, and session regressions; no Groq requests."""

from datetime import date
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.errors import StreamlitSecretNotFoundError

from src import ai_assistant, ai_providers
from src.ai_assistant import OllamaConfig
from src.ai_providers import (
    CLOUD_SESSION_REQUEST_LIMIT, GROQ_ENDPOINT, RECOMMENDED_GROQ_MODEL,
    GroqProvider, OllamaProvider, build_provider,
)
from src.ai_queries import AssistantError, FinancialIntent, execute_financial_query
from src.budgets import load_budgets
from src.data_loader import load_transactions


ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = "test-placeholder-never-a-real-credential"
TX = (b"date,description,category,type,amount\n"
      b"2026-01-01,PRIVATE CLIENT RECORD,Service Revenue,Income,1234.56\n"
      b"2026-01-15,PRIVATE RENT RECORD,Rent,Expense,80.00\n"
      b"2026-02-01,PRIVATE OTHER RECORD,Service Revenue,Income,300.00\n")
BUDGET = b"month,category,budget_amount\n2026-01,Rent,75.00\n"


def intent(operation="total_income", months=None, category=None, metric=None):
    return FinancialIntent(operation=operation, months=months or [], category=category, metric=metric)


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch):
    for name in ("AI_PROVIDER", "OLLAMA_MODEL", "OLLAMA_BASE_URL", "GROQ_MODEL", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_MODEL", RECOMMENDED_GROQ_MODEL)
    monkeypatch.setenv("GROQ_API_KEY", TEST_KEY)


@pytest.fixture
def transport(monkeypatch):
    """Exercise real HTTP serialization with a mock transport, never the network."""
    handler = Mock(return_value=httpx.Response(200, json={"choices": [{
        "finish_reason": "stop", "message": {"content": intent().model_dump_json()},
    }]}))
    original = httpx.Client
    constructor = Mock(side_effect=lambda **options: original(transport=httpx.MockTransport(handler), **options))
    monkeypatch.setattr(ai_providers.httpx, "Client", constructor)
    return handler, constructor


def page():
    return AppTest.from_file(ROOT / "app.py", default_timeout=20).run()


def assert_private_ui(app):
    assert not app.exception
    assert not app.get("json")
    for message in app.get("chat_message"):
        assert not message.get("expander")
    for element in ("text", "markdown", "caption", "info", "error"):
        assert TEST_KEY not in " ".join(item.value for item in app.get(element))
    assert TEST_KEY not in str(app.session_state)


def test_selection_defaults_local_even_when_key_exists(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", TEST_KEY)
    assert isinstance(build_provider(), OllamaProvider)
    assert isinstance(build_provider({"GROQ_API_KEY": TEST_KEY}), OllamaProvider)
    assert build_provider().config == OllamaConfig()


def test_environment_and_secrets_configuration(monkeypatch):
    secrets = {"AI_PROVIDER": "groq", "GROQ_MODEL": RECOMMENDED_GROQ_MODEL, "GROQ_API_KEY": TEST_KEY}
    provider = build_provider(secrets)
    assert isinstance(provider, GroqProvider)
    assert provider.status() == "Groq configured"
    assert provider.model == RECOMMENDED_GROQ_MODEL
    assert provider.api_key == TEST_KEY
    assert TEST_KEY not in repr(provider)
    assert TEST_KEY not in str(provider.identity)
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    assert isinstance(build_provider(secrets), OllamaProvider)
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_MODEL", "explicitly-configured-model")
    monkeypatch.setenv("GROQ_API_KEY", "")
    provider = build_provider(secrets)
    assert provider.model == "explicitly-configured-model"
    assert provider.status() == "Groq unconfigured"  # Empty env overrides secrets.


def test_local_secrets_retain_model_and_loopback_restrictions():
    assert build_provider({"OLLAMA_BASE_URL": "http://127.0.0.1:11434"}).config.base_url == "http://127.0.0.1:11434"
    with pytest.raises(AssistantError, match="loopback"):
        build_provider({"OLLAMA_BASE_URL": "https://public.example"})
    with pytest.raises(AssistantError, match="only OLLAMA_MODEL"):
        build_provider({"OLLAMA_MODEL": "another-model"})


@pytest.mark.parametrize("settings", [{"AI_PROVIDER": "other"}, {"AI_PROVIDER": 4},
                                       {"AI_PROVIDER": "groq", "GROQ_API_KEY": [TEST_KEY]}])
def test_invalid_configuration_is_safe(settings):
    with pytest.raises(AssistantError) as error:
        build_provider(settings)
    assert TEST_KEY not in str(error.value)

def test_missing_and_malformed_secrets_are_safe():
    secrets = Mock()
    secrets.get.side_effect = FileNotFoundError("private path")
    assert isinstance(build_provider(secrets), OllamaProvider)
    secrets.get.side_effect = ValueError(TEST_KEY)
    with pytest.raises(AssistantError) as error:
        build_provider(secrets)
    assert TEST_KEY not in str(error.value)
    secrets.get.side_effect = StreamlitSecretNotFoundError(TEST_KEY, error_id="failed-parsing-secrets-file")
    with pytest.raises(AssistantError) as error:
        build_provider(secrets)
    assert TEST_KEY not in str(error.value)


def test_groq_request_contract_and_privacy(transport):
    handler, constructor = transport
    provider = GroqProvider(RECOMMENDED_GROQ_MODEL, TEST_KEY)
    assert provider.status() == "Groq configured"
    handler.assert_not_called()  # Rendering/status never makes an API call.
    assert provider.extract_intent("Total income?", ["2026-01", "2026-02"]) == intent()
    request = handler.call_args.args[0]
    assert str(request.url) == GROQ_ENDPOINT
    assert request.headers["authorization"] == f"Bearer {TEST_KEY}"
    body = json.loads(request.content)
    assert body["model"] == RECOMMENDED_GROQ_MODEL
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_completion_tokens"] == 512
    assert body["stream"] is False
    assert body["temperature"] == 0
    metadata = json.loads(body["messages"][-1]["content"])
    assert set(metadata) == {"question", "available_months", "schema"}
    assert metadata["available_months"] == ["2026-01", "2026-02"]
    assert metadata["schema"] == FinancialIntent.model_json_schema()
    assert "PRIVATE" not in str(body) and "1234.56" not in str(body) and TEST_KEY not in str(body)
    options = constructor.call_args.kwargs
    assert options["timeout"].read == 30 and options["timeout"].connect == 3
    assert options["trust_env"] is False and options["follow_redirects"] is False
    assert handler.call_count == 1  # No implicit retry.


@pytest.mark.parametrize("content", ["not JSON", "[]", "null", "{}", "<think>private</think>{}",
    json.dumps({"operation": "execute_sql", "months": [], "category": None, "metric": None}),
    json.dumps({"operation": "total_income", "months": "2026-01", "category": None, "metric": None}),
    json.dumps({"operation": "total_income", "months": [], "category": None, "metric": None, "code": "bad"}),
    json.dumps({"operation": "total_expenses", "months": [], "category": "Unknown", "metric": None}),
    "x" * 8001, None])
def test_invalid_cloud_intents_are_rejected(transport, content):
    handler, _ = transport
    handler.return_value = httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
    with pytest.raises(AssistantError, match="invalid financial request"):
        GroqProvider(RECOMMENDED_GROQ_MODEL, TEST_KEY).extract_intent("Total income?", ["2026-01"])


@pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": None},
    {"choices": [{"finish_reason": "length", "message": {"content": intent().model_dump_json()}}]}])
def test_incomplete_provider_responses_are_rejected(transport, payload):
    transport[0].return_value = httpx.Response(200, json=payload)
    with pytest.raises(AssistantError, match="invalid financial request"):
        GroqProvider(RECOMMENDED_GROQ_MODEL, TEST_KEY).extract_intent("Total income?", [])


@pytest.mark.parametrize("code,expected", [(429, "rate limit or quota"), (401, "authentication"),
                                         (403, "authentication"), (400, "could not process"),
                                         (500, "could not process"), (302, "could not process")])
def test_cloud_http_errors_never_expose_credentials(transport, code, expected):
    handler, _ = transport
    handler.return_value = httpx.Response(code, text=f"Sensitive provider body {TEST_KEY}")
    with pytest.raises(AssistantError, match=expected) as error:
        GroqProvider(RECOMMENDED_GROQ_MODEL, TEST_KEY).extract_intent("Total income?", [])
    assert TEST_KEY not in str(error.value)
    assert handler.call_count == 1


@pytest.mark.parametrize("failure", [httpx.ReadTimeout(TEST_KEY), httpx.ConnectError(TEST_KEY)])
def test_cloud_transport_errors_are_safe(transport, failure):
    transport[0].side_effect = failure
    with pytest.raises(AssistantError, match="unavailable or.*timed out") as error:
        GroqProvider(RECOMMENDED_GROQ_MODEL, TEST_KEY).extract_intent("Total income?", [])
    assert TEST_KEY not in str(error.value)
    assert transport[0].call_count == 1


@pytest.mark.parametrize("question", ["", "   ", "a" * 1501, None])
def test_question_limits_before_network(transport, question):
    with pytest.raises(AssistantError, match="1–1500"):
        GroqProvider(RECOMMENDED_GROQ_MODEL, TEST_KEY).extract_intent(question, [])
    transport[0].assert_not_called()


@pytest.mark.parametrize("model,key", [("", TEST_KEY), (RECOMMENDED_GROQ_MODEL, ""), ("", "")])
def test_missing_configuration_never_calls_network(transport, model, key):
    provider = GroqProvider(model, key)
    assert provider.status() == "Groq unconfigured"
    with pytest.raises(AssistantError, match="not configured"):
        provider.extract_intent("Total income?", [])
    transport[0].assert_not_called()


@pytest.mark.parametrize("selected,question", [
    (intent(), "Total income?"),
    (intent("budget_comparison", ["2026-01"], "Rent"), "Rent budget January 2026?"),
    (intent("compare_months", ["2026-01", "2026-02"], metric="income"), "Compare income January and February 2026"),
])
def test_adapters_share_financial_calculations(monkeypatch, transport, selected, question):
    mocked = Mock()
    mocked.chat.return_value = SimpleNamespace(message=SimpleNamespace(content=selected.model_dump_json()))
    monkeypatch.setattr(ai_assistant.ollama, "Client", Mock(return_value=mocked))
    transport[0].return_value = httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": selected.model_dump_json()}}]})
    transactions, budgets = load_transactions(BytesIO(TX)), load_budgets(BytesIO(BUDGET))
    answers = []
    for provider in (OllamaProvider(OllamaConfig()), GroqProvider(RECOMMENDED_GROQ_MODEL, TEST_KEY)):
        parsed = provider.extract_intent(question, ["2026-01", "2026-02"])
        answers.append(execute_financial_query(parsed, question, transactions, date(2026, 1, 1), date(2026, 2, 1),
                                              transactions.category.unique().tolist(), budgets))
    assert answers[0] == answers[1]
    if selected.operation == "total_income":
        assert answers[0]["result"]["totals"]["income"] == 1534.56
    if selected.operation == "budget_comparison":
        row = answers[0]["result"]["rows"][0]
        assert (row["budget"], row["actual"], row["variance"]) == (75, 80, 5)


def uploads(label, **kwargs):
    return BytesIO(TX if label == "Upload transactions" else BUDGET)


def test_unconfigured_cloud_preserves_both_uploads_and_dashboard(monkeypatch, cloud, transport):
    monkeypatch.setenv("GROQ_API_KEY", "")
    app = page()
    assert app.chat_input[0].disabled
    assert "FinSight AI — Cloud" in [item.value for item in app.subheader]
    assert app.metric[0].value == "€117,542.02"
    with patch("streamlit.file_uploader", side_effect=uploads):
        app.radio(key="dataset_selection").set_value("Upload CSV").run()
        assert_private_ui(app)
        assert app.chat_input[0].disabled
        assert app.metric[0].value == "€1,534.56"
        assert len(app.dataframe[-1].value) == 3
        assert len(app.get("plotly_chart")) == 5
        assert app.radio(key="budget_source").value == "Upload budget CSV"
        assert next(item.value for item in app.metric if item.label == "Total Budget") == "€75.00"
        assert next(item.value for item in app.metric if item.label == "Budget Variance") == "€5.00"
        assert not app.get("download_button")[0].proto.disabled
        app.multiselect(key="categories").set_value(["Rent"]).run()
        assert app.metric[1].value == "€80.00"
        app.button(key="reset_filters").click().run()
        assert app.metric[0].value == "€1,534.56"
    transport[0].assert_not_called()


def test_cloud_uploaded_answers_history_filters_and_budget_isolation(cloud, transport):
    handler, _ = transport
    app = page()
    with patch("streamlit.file_uploader", side_effect=uploads):
        app.radio(key="dataset_selection").set_value("Upload CSV").run()
        app.chat_input[0].set_value("Total income?").run()
        assert_private_ui(app)
        assert "€1,534.56" in app.session_state["ai_messages"][-1]["content"]
        assert app.get("chat_message")[-1].get("caption")[0].value == "✓ Verified using financial data"
        app.run()
        assert len(app.get("chat_message")) == 2
        selected = intent("budget_comparison", ["2026-01"], "Rent")
        handler.return_value = httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": selected.model_dump_json()}}]})
        app.chat_input[0].set_value("Rent budget January 2026?").run()
        row = app.session_state["ai_messages"][-1]["result"]["rows"][0]
        assert (row["budget"], row["actual"], row["variance"]) == (75, 80, 5)
        bodies = " ".join(call.args[0].content.decode() for call in handler.call_args_list)
        assert "1234.56" not in bodies
        assert "PRIVATE" not in bodies
        assert "budget_amount" not in bodies
        app.multiselect(key="categories").set_value(["Rent"]).run()
        assert app.session_state["ai_messages"] == []
        # Replacing only the budget also invalidates previous answers.
        app.session_state["ai_messages"] = [{"role": "user", "content": "previous budget"}]
        with patch("streamlit.file_uploader", side_effect=lambda label, **kwargs: BytesIO(TX) if label == "Upload transactions" else None):
            app.run()
        assert app.session_state["ai_messages"] == []
        assert app.radio(key="budget_source").value == "Upload budget CSV"
    assert_private_ui(app)
    app.radio(key="dataset_selection").set_value("Sample Dataset").run()
    assert app.session_state["ai_messages"] == []
    assert app.metric[0].value == "€117,542.02"


@pytest.mark.parametrize("response", ["unsupported", "rate", "invalid"])
def test_cloud_refusals_and_errors_have_no_verification(cloud, transport, response):
    handler, _ = transport
    if response == "rate":
        handler.return_value = httpx.Response(429, text=TEST_KEY)
    else:
        content = intent("unsupported").model_dump_json() if response == "unsupported" else TEST_KEY
        handler.return_value = httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
    app = page()
    app.chat_input[0].set_value("Which stock should I buy?").run()
    assert_private_ui(app)
    assert "result" not in app.session_state["ai_messages"][-1]
    assert not app.get("chat_message")[-1].get("caption")
    assert app.session_state["cloud_ai_requests"] == 1
    app.run()
    assert not app.get("chat_message")[-1].get("caption")


def test_cloud_session_limit_clear_and_separate_sessions(cloud, transport):
    app = page()
    app.session_state["cloud_ai_requests"] = CLOUD_SESSION_REQUEST_LIMIT - 1
    app.chat_input[0].set_value("Total income?").run()
    assert app.session_state["cloud_ai_requests"] == CLOUD_SESSION_REQUEST_LIMIT
    app.run()
    assert app.chat_input[0].disabled
    app.button(key="clear_ai_chat").click().run()
    assert app.session_state["ai_messages"] == []
    assert app.session_state["cloud_ai_requests"] == CLOUD_SESSION_REQUEST_LIMIT
    app.multiselect(key="categories").set_value(["Rent"]).run()
    assert app.chat_input[0].disabled
    other = page()
    assert not other.chat_input[0].disabled
    assert other.session_state["ai_messages"] == []
    transport[0].assert_called_once()


def test_changing_provider_model_and_configuration_clears_history(monkeypatch, cloud, transport):
    app = page()
    app.chat_input[0].set_value("Total income?").run()
    assert len(app.session_state["ai_messages"]) == 2
    monkeypatch.setenv("GROQ_MODEL", "different-explicit-model")
    app.run()
    assert app.session_state["ai_messages"] == []
    app.session_state["ai_messages"] = [{"role": "user", "content": "previous provider"}]
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    app.run()
    assert app.session_state["ai_messages"] == []
    assert app.chat_input[0].disabled  # Existing offline fixture, no fallback.
    assert "FinSight AI — Qwen3 8B (Local)" in [item.value for item in app.subheader]
    monkeypatch.setenv("AI_PROVIDER", "invalid")
    app.run()
    assert_private_ui(app)
    assert app.metric[0].value == "€117,542.02"


def test_streamlit_secrets_configure_cloud_without_exposing_key(transport):
    app = AppTest.from_file(ROOT / "app.py", default_timeout=20)
    app.secrets.update({"AI_PROVIDER": "groq", "GROQ_MODEL": RECOMMENDED_GROQ_MODEL, "GROQ_API_KEY": TEST_KEY})
    app.run()
    assert not app.chat_input[0].disabled
    app.chat_input[0].set_value("Total income?").run()
    assert_private_ui(app)
    assert "€117,542.02" in app.session_state["ai_messages"][-1]["content"]


def test_uploaded_data_and_answers_are_isolated_between_sessions(cloud, transport):
    uploaded = page()
    with patch("streamlit.file_uploader", side_effect=uploads):
        uploaded.radio(key="dataset_selection").set_value("Upload CSV").run()
        uploaded.chat_input[0].set_value("Total income?").run()
    sample = page()
    assert sample.session_state["ai_messages"] == []
    sample.chat_input[0].set_value("Total income?").run()
    assert "€1,534.56" in uploaded.session_state["ai_messages"][-1]["content"]
    assert "€117,542.02" in sample.session_state["ai_messages"][-1]["content"]
    assert uploaded.session_state["active_dataset"] != sample.session_state["active_dataset"]
    assert "PRIVATE CLIENT RECORD" in uploaded.dataframe[-1].value.description.tolist()
    assert "PRIVATE CLIENT RECORD" not in sample.dataframe[-1].value.description.tolist()


@pytest.mark.parametrize("bad_source", ["transactions", "budgets"])
def test_cloud_invalid_uploads_never_fall_back_to_sample(cloud, transport, bad_source):
    app = page()
    def invalid_upload(label, **kwargs):
        if label == "Upload transactions":
            return BytesIO(b"invalid,csv\n1,2\n" if bad_source == "transactions" else TX)
        return BytesIO(b"invalid,budget\n1,2\n")
    with patch("streamlit.file_uploader", side_effect=invalid_upload):
        app.radio(key="dataset_selection").set_value("Upload CSV").run()
    assert not app.exception
    assert app.error
    if bad_source == "transactions":
        assert not app.metric and not app.get("plotly_chart")
    else:
        assert app.metric[0].value == "€1,534.56"
        assert not any(item.label == "Total Budget" for item in app.metric)
        assert app.radio(key="budget_source").value == "Upload budget CSV"
    transport[0].assert_not_called()
