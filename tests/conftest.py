"""Keep all automated page tests independent of a running Ollama daemon."""

import pytest


@pytest.fixture(autouse=True)
def offline_assistant_status(monkeypatch):
    monkeypatch.setattr("src.ai_dashboard.cached_connection_status", lambda config: "Ollama unavailable")
