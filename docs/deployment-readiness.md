# Deployment preparation — Step 1

Assessment date: 19 October 2026. Inspected baseline:
`41b1d8952107239f7272c4eba33621c02dbbd1be`.

This report records the Step 1 baseline. The subsequently implemented provider
adapters, current configuration, privacy boundaries, and verification are
documented in [Step 2: Groq integration](groq-integration.md).

This step reviews portability, dependencies, security, and provider boundaries.
It does not configure hosting, integrate a hosted provider, create secrets, or
change the working Ollama/Qwen3 implementation.

## Repository and local assumptions

- `app.py` is the repository-root Streamlit entrypoint. `requirements.txt` and
  `.streamlit/config.toml` are also in the expected repository-root locations.
- Sample transactions and budgets are committed synthetic data. Their paths in
  `src/dashboard.py` and `src/budget_dashboard.py` are resolved from `__file__`
  using `pathlib`, independently of the current working directory. Validation
  scripts and tests likewise locate the repository from their own file paths.
- Application source has no `/home/asma/...` path dependency. Uploaded CSVs and
  generated downloads are handled in memory; no persistent writable data volume
  is required. Session history is not durable across server/session restarts.
- The theme file contains presentation settings and disables usage telemetry.
  It contains no secrets, machine-specific bind address, or Ollama configuration.
- The Ollama **Python package** must be installed because it is imported during
  application startup. The Ollama executable, daemon, and model weights are not
  required to render the dashboard. Missing connectivity disables only chat.
- Current AI configuration deliberately accepts only loopback endpoints and
  `qwen3:8b`. A cloud deployment's `localhost` refers to the cloud server, not the
  developer's computer. Changing an endpoint variable alone cannot enable a
  hosted provider. Do not expose the personal Ollama endpoint to solve this.
- Current UI labels and availability messages explicitly name Qwen3/Ollama.
  Provider-appropriate labels will be needed when a hosted adapter is introduced.
- Current configuration reads `OLLAMA_MODEL` and `OLLAMA_BASE_URL` from environment
  variables. It does not yet read hosted credentials or `st.secrets`.

The dashboard and financial engine are candidates for Community Cloud. The
cloud AI architecture remains intentionally incomplete until the later provider
step. Local readiness tests do not constitute a deployed Community Cloud test.

## Dependency review

AST inspection of the application, source modules, scripts, and tests identifies
these direct third-party dependencies, all already present in `requirements.txt`:

| Package | Current pin | Purpose |
| --- | --- | --- |
| streamlit | 1.66.0 | UI, state, native page tests |
| pandas | 3.0.6 | CSV processing and financial aggregations |
| plotly | 7.1.0 | Charts |
| ollama | 0.6.3 | Local intent extraction and model metadata |
| httpx | 0.28.1 | Ollama transport timeouts and transport errors |
| pydantic | 2.14.1 | Strict financial intent validation |
| pytest | 9.1.1 | Verification suite |

The requirements file also pins NumPy and other transitive dependencies from
the existing environment. No direct dependency is missing. All currently
installed requirements declare Python 3.12 compatibility in their metadata.
The clean installation and execution checks below also succeeded; this assessment
does not rely on metadata alone.

Keep the existing pins unless an actual clean-install/test failure justifies a
specific change. Test/dev dependencies may remain installed for this preparation
step; splitting dependency files is not necessary for the existing application.
No system Ollama installation or model download belongs in cloud dependencies.

Python 3.12 is the intended cloud target. Community Cloud selects Python through
Advanced settings; do not assume a local interpreter version, theme setting, or
an unrecognized runtime file chooses the cloud version automatically.

## Verification results

The original environment was left intact. A temporary CPython 3.12.15 runtime
was installed with `uv` under `/tmp/finsight-readiness-python`, without adding
executables to the user's PATH. It created a separate virtual environment at
`/tmp/finsight-readiness-312`. Installing the unchanged `requirements.txt` there
succeeded, including native Linux Python 3.12 wheels. No package pins were
changed and no global Python packages were installed.

| Check | Existing Python 3.14.7 | Fresh Python 3.12.15 |
| --- | --- | --- |
| Full `pytest -v` suite | 171 passed | 171 passed |
| Phase 1 validation | Passed, including 12 invalid-input checks | Passed, including 12 invalid-input checks |
| Phase 2 validation | All 5 reconciliation checks passed | All 5 reconciliation checks passed |
| `pip check` | No broken requirements | No broken requirements |
| Native page rendering with a real unreachable local Ollama endpoint | Passed; chat disabled, dashboard/filtering usable | Passed; chat disabled, dashboard/filtering usable |

Additional Python 3.12 checks:

- Sample transactions and budgets load after changing the process working
  directory to `/tmp`, confirming the repository-relative data lookup.
- `streamlit run app.py` starts successfully on a temporary loopback-only port;
  both the page and health endpoint return HTTP 200. The owned server is stopped
  after checking it. No public endpoint is opened.
- The native page test verifies the unfiltered EUR 117,542.02 income KPI and
  200-row explorer, then changes category filters and verifies the Rent total.
- The theme configuration loads during the native Streamlit page test/startup.
- Nineteen sensitive/local/model filename examples are confirmed ignored without
  creating those files. The public `.streamlit/config.toml` remains tracked.
- `git diff --check` passes. No application modules, datasets, requirements, or
  existing test logic are modified by this step.

Local reproduction while the temporary environment remains available:

```bash
/tmp/finsight-readiness-312/bin/python -m pip check
/tmp/finsight-readiness-312/bin/python -m pytest -v
/tmp/finsight-readiness-312/bin/python scripts/validate_phase1.py
/tmp/finsight-readiness-312/bin/python scripts/validate_phase2.py
```

For a new machine, create an isolated environment using an available Python
3.12 interpreter and install `requirements.txt` before these checks. Temporary
tools/environments/logs are not project artifacts and must not be committed.

These results verify Linux/Python 3.12 readiness on this machine. They do not
prove Community Cloud resource limits, a future hosted provider's compatibility,
or a successful deployment. No hosted-provider requests, credential creation,
or real-model inference were needed for these readiness checks. The local
Ollama/Qwen3 implementation remains unchanged.

## Security findings

- No tracked dotenv files, Streamlit secrets file, API credentials, virtual
  environment, model weights, or binary model artifacts were found. A scan of
  tracked text found no common token/private-key patterns. This is a repository
  review, not a guarantee against every possible secret representation.
- Existing exclusions cover `.env`, `.env.*`, `.streamlit/secrets.toml`, `.venv/`,
  Python caches, `.ollama/`, `models/`, and common model weight extensions.
- Step 1 extends ignores to alternate environment names (`.venv*/`, `venv/`,
  `env/`), private-key extensions, and common credential JSON filenames. Ignore
  rules do not make a secret in an otherwise tracked source file safe to commit.
- Temporary test tools, Python runtimes, environments, and logs are under `/tmp`,
  outside the repository. Secret values were not read or printed.
- The current local model requires no API key. Future hosted credentials belong
  in Streamlit Secrets and must never enter logs, prompts, history, cache keys,
  committed configuration, or exception messages.

Potential future configuration names only (not implemented and no values set):
`AI_PROVIDER`, `AI_MODEL`, `AI_API_BASE_URL`, `AI_API_KEY`.

## Proposed provider boundary — documentation only

Only these functions currently communicate with Ollama:

1. `src.ai_assistant.connection_status(config)` calls `ollama.Client.list()`.
2. `src.ai_assistant.extract_intent(question, available_months, config)` calls
   `ollama.Client.chat()` with the JSON schema, `think=False`, and temperature 0.

`src.ai_dashboard.cached_connection_status()` caches the first function for 30
seconds. `render_ai_assistant()` builds `OllamaConfig`, displays provider status,
and connects extraction to the shared financial router. The live validation
script calls the same local functions explicitly.

A minimal future adapter could expose two operations:

```python
# Proposed interface only; no provider adapter is implemented in this step.
status() -> str  # available, unavailable, or unconfigured
extract_intent(question: str, available_months: list[str]) -> FinancialIntent
```

Provider-specific configuration and transport belong in each adapter. A small
factory would choose the local Ollama adapter or a later hosted adapter using
explicit configuration. Missing hosted configuration would return an
unconfigured/disabled state, leaving the dashboard usable. Local defaults and
the `qwen3:8b` restriction stay intact within the Ollama adapter.

Both adapters must use the same `FinancialIntent` schema and Python validation.
`execute_financial_query()` retains query-scope checks and financial routing;
`src/analytics.py`, `src/budgets.py`, and `src/ai_wording.py` remain provider
independent. No second model call for financial wording is needed.

When a hosted provider is selected later, adapt authentication, JSON-schema
request/response conventions, health/error handling, and display labels. Cache
and conversation identities should include provider/model identity but not
credentials. Continue sending only the question and the necessary month/schema
metadata, not raw transaction descriptions or generated financial values.

## Decisions before Step 2

1. Select a hosted provider and model that can support constrained structured
   requests, suitable timeouts, and the existing strict schema.
2. Decide acceptable request costs/rate limits and public-demo usage limits.
3. Confirm the provider's data-retention policy is acceptable for submitted
   questions and the limited metadata sent for intent extraction.

No credentials are needed for this decision or for Step 1. Do not weaken the
local loopback restriction or replace the local model as a shortcut.

## Official deployment references

- [Python version selection](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Dependency handling](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
- [Repository paths and configuration](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)
- [Streamlit Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
