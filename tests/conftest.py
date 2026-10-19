"""Keep automated tests independent of private settings and live AI services."""

import pytest


@pytest.fixture(autouse=True)
def offline_assistant_status(monkeypatch):
    # Never load the developer's local secrets during offline page tests.
    # Individual tests may supply their own mock AppTest secrets/settings.
    monkeypatch.setattr("streamlit.secrets", {})
    for name in ("AI_PROVIDER", "OLLAMA_MODEL", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("src.ai_dashboard.cached_connection_status", lambda config: "Ollama unavailable")
