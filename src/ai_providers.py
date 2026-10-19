"""Intent-only inference adapters. Financial data and calculations stay in Python."""

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import os
from typing import Protocol

import httpx
from pydantic import ValidationError

from src import ai_assistant
from src.ai_assistant import OllamaConfig, SYSTEM_PROMPT, INTENT_EXAMPLES
from src.ai_queries import AssistantError, FinancialIntent, SUPPORTED_QUESTIONS


GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
RECOMMENDED_GROQ_MODEL = "qwen/qwen3.8-27b"
MAX_QUESTION_LENGTH = 1500
CLOUD_SESSION_REQUEST_LIMIT = 20


class IntentProvider(Protocol):
    """Shared boundary: providers interpret questions, never receive DataFrames."""

    @property
    def identity(self) -> tuple[str, ...]: ...

    def status(self) -> str: ...

    def extract_intent(self, question: str, available_months: list[str]) -> FinancialIntent: ...


@dataclass(frozen=True)
class OllamaProvider:
    config: OllamaConfig

    @property
    def identity(self) -> tuple[str, ...]:
        return ("ollama", self.config.base_url, self.config.model)

    def status(self) -> str:
        return ai_assistant.connection_status(self.config)

    def extract_intent(self, question: str, available_months: list[str]) -> FinancialIntent:
        return ai_assistant.extract_intent(question, available_months, self.config)


@dataclass(frozen=True)
class GroqProvider:
    # Never place this object in Streamlit cache/session state or log its fields.
    model: str = ""
    api_key: str = field(default="", repr=False, compare=False)
    timeout: float = 30.0

    @property
    def identity(self) -> tuple[str, ...]:
        # Keys (including key fingerprints) must not enter cache/history identities.
        return ("groq", self.model, str(bool(self.api_key)))

    def status(self) -> str:
        # Configuration check only: rendering must never issue a paid request.
        return "Groq configured" if self.model and self.api_key else "Groq unconfigured"

    def extract_intent(self, question: str, available_months: list[str]) -> FinancialIntent:
        if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_LENGTH:
            raise AssistantError("Enter a self-contained financial question of 1–1500 characters.")
        if self.status() != "Groq configured":
            raise AssistantError("Cloud AI is not configured. The dashboard remains fully usable.")
        schema = FinancialIntent.model_json_schema()
        messages = [{"role": "system", "content": SYSTEM_PROMPT.replace(" /no_think", "")}]
        for example_question, example_intent in INTENT_EXAMPLES:
            messages.extend([{"role": "user", "content": example_question},
                             {"role": "assistant", "content": json.dumps(example_intent)}])
        messages.append({"role": "user", "content": json.dumps({
            "question": question, "available_months": available_months, "schema": schema,
        })})
        try:
            # Official REST endpoint; no SDK retries, environment endpoint override,
            # proxy inheritance, redirect following, or fallback provider.
            with httpx.Client(timeout=httpx.Timeout(self.timeout, connect=3.0),
                              trust_env=False, follow_redirects=False) as client:
                response = client.post(GROQ_ENDPOINT, headers={"Authorization": f"Bearer {self.api_key}"}, json={
                    "model": self.model, "messages": messages,
                    # Groq documents JSON object mode for all hosted models.
                    # Pydantic below enforces our stricter schema and semantics.
                    "response_format": {"type": "json_object"},
                    "temperature": 0, "max_completion_tokens": 512, "stream": False,
                })
        except httpx.HTTPError:
            raise AssistantError("Cloud AI is unavailable or the request timed out. Please try again later; the dashboard still works.") from None
        if response.status_code == 429:
            raise AssistantError("Cloud AI's rate limit or quota has been reached. Please try again later; the dashboard still works.")
        if response.status_code in (401, 403):
            raise AssistantError("Cloud AI authentication is unavailable. Please contact the application owner; the dashboard still works.")
        if not 200 <= response.status_code < 300:
            # Never expose provider response bodies, request headers, or exceptions.
            raise AssistantError("Cloud AI could not process this request. Please try again later; no fallback was used.")
        try:
            if len(response.content) > 32000:
                raise ValueError("Oversized response")
            choice = response.json()["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Incomplete response")
            content = choice["message"]["content"]
            if not isinstance(content, str) or len(content) > 8000:
                raise ValueError("Invalid content")
            return FinancialIntent.model_validate_json(content)
        except (ValidationError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise AssistantError("Cloud AI returned an invalid financial request. No calculations were performed. " + SUPPORTED_QUESTIONS) from None


def build_provider(secrets: Mapping | None = None) -> IntentProvider:
    """Environment wins over flat Streamlit Secrets; provider defaults to Ollama.

    Read only the selected provider's settings. Never infer a provider from a key.
    Missing/malformed secrets must not crash the rest of the dashboard.
    """
    def setting(name: str, default: str = "") -> str:
        value = os.environ.get(name)
        if value is None and secrets is not None:
            try:
                value = secrets.get(name)
            except FileNotFoundError as error:
                # Streamlit uses this exception family for both absent files
                # and malformed TOML. Only an absent file permits defaults.
                if getattr(error, "error_id", "no-secrets-found") != "no-secrets-found":
                    raise AssistantError("AI settings are unavailable. Check the application configuration; the dashboard still works.") from None
                value = None
            except (OSError, ValueError):
                raise AssistantError("AI settings are unavailable. Check the application configuration; the dashboard still works.") from None
        if value is None:
            return default
        if not isinstance(value, str):
            raise AssistantError("AI settings must be text values. The dashboard still works.")
        return value.strip()

    provider = setting("AI_PROVIDER", "ollama")
    if provider == "ollama":
        return OllamaProvider(OllamaConfig(base_url=setting("OLLAMA_BASE_URL", "http://localhost:11434"),
                                         model=setting("OLLAMA_MODEL", "qwen3:8b")))
    if provider == "groq":
        return GroqProvider(model=setting("GROQ_MODEL"), api_key=setting("GROQ_API_KEY"))
    raise AssistantError("AI_PROVIDER must be ollama or groq. The dashboard still works; no fallback was used.")


def extract_intent(question: str, available_months: list[str], provider: IntentProvider) -> FinancialIntent:
    """Route inference only; the financial router is shared by both providers."""
    return provider.extract_intent(question, available_months)
