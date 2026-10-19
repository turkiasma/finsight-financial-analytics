"""Streamlit chat presentation and scope-isolated session history."""

from datetime import date
from hashlib import sha256
import json
from collections.abc import MutableMapping

import pandas as pd
import streamlit as st

from src.ai_assistant import OllamaConfig, connection_status
from src.ai_providers import (
    CLOUD_SESSION_REQUEST_LIMIT, MAX_QUESTION_LENGTH, OllamaProvider,
    build_provider, extract_intent,
)
from src.ai_queries import AssistantError, execute_financial_query


@st.cache_data(ttl=30, show_spinner=False)
def cached_connection_status(config: OllamaConfig) -> str:
    """Cache a metadata-only connection check; never cache user questions."""
    return connection_status(config)


def synchronize_history(state: MutableMapping, context_key: str) -> None:
    """Discard past answers when datasets, filters, budgets, or endpoint change."""
    if state.get("ai_context_key") != context_key:
        state["ai_messages"] = []
        state["ai_context_key"] = context_key


def _render_message(message: dict) -> None:
    """Show the answer and a discreet calculation indicator, keeping results internal."""
    with st.chat_message(message["role"]):
        if message["role"] == "assistant" and isinstance(message.get("result"), dict) and message["result"]:
            st.markdown(message["content"], unsafe_allow_html=False)
            st.caption("✓ Verified using financial data")
        else:
            st.text(message["content"])


def render_ai_assistant(
    transactions: pd.DataFrame, budgets: pd.DataFrame | None, dataset_identity: str,
    start: date, end: date, categories: list[str],
) -> None:
    """Render optional intent-only chat, preserving the dashboard on all failures."""
    st.divider()
    try:
        provider = build_provider(st.secrets)
    except AssistantError as error:
        synchronize_history(st.session_state, "unconfigured")
        st.subheader("FinSight AI")
        st.info(str(error))
        return
    local = isinstance(provider, OllamaProvider)
    st.subheader("FinSight AI — Qwen3 8B (Local)" if local else "FinSight AI — Cloud")
    st.write("Ask questions about your business financial data.")
    if not local:
        st.caption("Cloud AI receives your question, available calendar months, and the financial intent schema only. Records, descriptions, budgets, and calculated amounts are not attached. Avoid including confidential or personal information in questions.")
    st.caption("Ordinary questions use the sidebar dates and categories. A named month uses its full recorded calendar month; a named category replaces the category filter. Transaction-type display filters never affect answers.")
    st.caption("Budget questions require an explicit month and use the validated budget source above. Unless a category is named, sidebar expense categories apply. Budget-panel month/category controls do not filter chat. No budgets are prorated; complete month records must be supplied.")
    st.caption("Examples: What is the total income? · What were expenses in March 2026? · Compare income between April and May 2026. · Did we exceed our Marketing budget in February 2026?")
    st.caption("Ask self-contained questions; previous messages are displayed but are not sent to the model. Month names without years must be unambiguous. Changing data, filters, or budgets clears this conversation. Answers are verified Python calculations, not financial advice.")
    budget_key = None if budgets is None else sha256(budgets.to_csv(index=False).encode()).hexdigest()
    context_key = sha256(json.dumps([
        dataset_identity, start.isoformat(), end.isoformat(), sorted(categories),
        budget_key, provider.identity,
    ]).encode()).hexdigest()
    synchronize_history(st.session_state, context_key)
    status = cached_connection_status(provider.config) if local else provider.status()
    ready = status == ("Qwen3 available" if local else "Groq configured")
    st.caption(f"Connection: {status}" + (" · Local Ollama · Status cached for up to 30 seconds" if local else " · Connectivity is checked when you ask a question"))
    if not ready and local:
        st.info("The assistant is unavailable. Check your local Ollama service and installed qwen3:8b model. The dashboard remains fully usable; no model will be downloaded.")
    elif not ready:
        st.info("Cloud AI is not configured. The application owner must configure the hosted model and credentials privately. CSV uploads, financial analysis, and budget comparisons remain fully usable.")
    requests_used = st.session_state.get("cloud_ai_requests", 0)
    limited = not local and requests_used >= CLOUD_SESSION_REQUEST_LIMIT
    if not local:
        st.caption(f"Cloud questions: {requests_used}/{CLOUD_SESSION_REQUEST_LIMIT} requests used in this session.")
    if limited:
        st.info("This session's cloud AI request limit has been reached. The dashboard remains fully usable.")
    if st.button("Clear conversation", key="clear_ai_chat"):
        st.session_state["ai_messages"] = []

    for message in st.session_state["ai_messages"]:
        _render_message(message)

    question = st.chat_input("Ask a financial question…", key="financial_question",
                             max_chars=MAX_QUESTION_LENGTH, disabled=not ready or limited)
    if question:
        st.session_state["ai_messages"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.text(question)
        try:
            if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_LENGTH:
                raise AssistantError("Enter a self-contained financial question of 1–1500 characters.")
            if not ready or limited:
                raise AssistantError("The assistant is unavailable for this request. The dashboard still works.")
            if not local:
                # Include failed attempts; clearing chat/data must not reset quota.
                st.session_state["cloud_ai_requests"] = requests_used + 1
            with st.spinner("The assistant is interpreting your question; Python will calculate the answer…"):
                months = sorted(transactions["date"].dt.strftime("%Y-%m").unique().tolist())
                intent = extract_intent(question, months, provider)
                answer = execute_financial_query(intent, question, transactions, start, end, categories, budgets)
            reply = {"role": "assistant", "content": answer["text"], "result": answer["result"]}
        except AssistantError as error:
            reply = {"role": "assistant", "content": "Request not answered: " + str(error)}
        st.session_state["ai_messages"].append(reply)
        # Bound session memory to twelve question/answer pairs.
        st.session_state["ai_messages"] = st.session_state["ai_messages"][-24:]
        _render_message(reply)
