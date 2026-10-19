# Deployment preparation — Step 2: Groq intent extraction

Implemented against the existing Phase 5 financial engine. This is preparation,
not a deployment. Step 2 used mocked inference without creating a key or making
live requests. Subsequent successful Step 3 live results are recorded below. The earlier
[Step 1 report](deployment-readiness.md) is preserved as a historical baseline.

## Configuration

One application supports both providers. `build_provider()` in
`src/ai_providers.py` reads flat Streamlit Secrets and environment variables.
An explicitly present environment variable wins, including an empty value.
`.env` files are not loaded. Missing secrets files permit local defaults;
malformed secrets produce a safe configuration error without showing contents.

| Setting | Default | Purpose |
| --- | --- | --- |
| `AI_PROVIDER` | `ollama` | Exactly `ollama` or `groq`; never inferred from a key |
| `OLLAMA_MODEL` | `qwen3:8b` | Only this installed local model is accepted |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Only loopback addresses are accepted |
| `GROQ_MODEL` | Empty | Explicit hosted model ID; required for cloud chat |
| `GROQ_API_KEY` | Empty | Private credential; required for cloud chat |

Local shell configuration (no key):

```bash
export AI_PROVIDER=ollama
export OLLAMA_MODEL=qwen3:8b
export OLLAMA_BASE_URL=http://localhost:11434
.venv/bin/python -m streamlit run app.py
```

Future Streamlit Community Cloud Secrets configuration, with a placeholder only:

```toml
AI_PROVIDER = "groq"
GROQ_MODEL = "qwen/qwen3.8-27b"
GROQ_API_KEY = "<private-key-configured-by-owner>"
```

Enter real credentials only in the hosting service's private Secrets settings or
a private process environment. Never put them into source or committed TOML.
The local `.streamlit/secrets.toml`, dotenv files, virtual environments, credentials,
and model files are ignored. No secrets file is added by this step.

Selecting Groq without a model or key shows an unconfigured status and disables
chat only. Selecting Ollama without its daemon/model preserves the existing
offline behavior. An unknown provider is a configuration error, never a fallback.
Groq's status indicates configuration only: it does not authenticate, list models,
or issue inference requests during rendering. Authentication and model access
must be checked later with an authorized live request.

## Hosted model and JSON mechanism

Documentation checked on 19 October 2026:

- Groq's [supported models](https://console.groq.com/docs/models) list
  `qwen/qwen3.8-27b` as an API model. The
  [model page](https://console.groq.com/docs/model/qwen/qwen3.8-27b) labels it a
  preview and explicitly lists JSON object and JSON schema modes.
- The adapter uses `response_format={"type":"json_object"}`.
  Groq's [structured output documentation](https://console.groq.com/docs/structured-outputs)
  supports this mode across hosted models. It guarantees neither field types
  nor our business semantics; the unchanged strict `FinancialIntent` validation
  enforces those locally. The prompt includes the existing complete schema and
  fixed intent examples. No reasoning field is read or displayed.
- This intentionally uses the portable JSON object mechanism even though the
  recommended model also documents strict schema support. A future model change
  should be checked for availability, JSON support, quality, and account access.
- Do not reuse the local `qwen3:8b` tag on Groq. The older `qwen/qwen3-32b` is
  [deprecated](https://console.groq.com/docs/deprecations), despite its old model
  page still being accessible. The hosted ID remains explicitly configurable.

The adapter sends text-only requests to Groq's fixed official
`https://api.groq.com/openai/v1/chat/completions` endpoint using existing
`httpx==0.28.1`. See the [API reference](https://console.groq.com/docs/api-reference).
There is no custom endpoint, proxy inheritance, redirect following, tool use,
SQL/code execution, model download, or provider fallback. No SDK dependency is
needed; all existing package pins remain unchanged.

## Provider boundary and reliability

`IntentProvider` exposes `status()` and
`extract_intent(question, available_months) -> FinancialIntent`, plus a secret-free
configuration identity for conversation isolation. `OllamaProvider` delegates
to the unchanged local `src/ai_assistant.py` implementation. Its loopback/model
restrictions, schema request, `think=False`, timeouts, and real validation script
are preserved.

Both paths use exactly this sequence:

```text
Question → provider intent → strict FinancialIntent validation
         → scope validation → existing Python financial/budget calculations
         → deterministic business wording → verified answer
```

There is no second model call for answers. Financial formulas, supported operations,
filter overrides, and wording templates are unchanged. Structured results remain
internal to the session; JSON and technical panels are never rendered. Only
successfully computed answers receive “✓ Verified using financial data”.

Conversation state is per Streamlit session and resets when transactions,
validated budgets, dates, categories, provider, model, local endpoint, or cloud
configuration availability change. API keys and key fingerprints are excluded
from history identities, caches, results, and displayed messages. Changing a key
between two configured states does not alter the financial scope. Provider objects
exist only for the current render/request and are not cached or stored in session
state. The only shared application cache is the existing metadata-only local
Ollama availability check.

## Uploads and privacy

Both transaction and monthly budget CSV uploads remain enabled in local and
cloud modes, including when AI is unconfigured or unavailable. Existing strict
CSV validation, sample selection, KPIs, charts, filters, budget comparisons,
explorer, and export operate independently of inference connectivity.

Uploaded transactions default to uploading a matching budget, without silently
selecting fictional sample budgets. An explicit sample budget selection retains
its existing warning. A new transaction dataset cannot inherit another dataset's
budget upload. The AI router receives the same current validated transaction and
budget DataFrames as the dashboard.

DataFrames/uploads are processed in memory in the visitor's session flow. They
are not intentionally persisted to files, logs, databases, or shared caches.
The adapter has no DataFrame argument and receives only:

- The current natural-language question (not prior chat history).
- Available calendar months (`YYYY-MM`).
- The static intent schema, allowed categories, and fixed intent examples.

It never attaches transaction rows/descriptions, customer records, budget files,
reports, or calculated monetary values. Anything a visitor types into their
question is transmitted as part of that question: this is not automatic redaction.

In a hosted deployment, CSV records are still processed on Streamlit's cloud
servers. This public portfolio demonstration is unsuitable for confidential
financial or personal information. The page displays this warning before upload
and explains the limited hosted transmission. Review the provider's
[data policies](https://console.groq.com/docs/your-data) before enabling public
inference; absence of attached records is not a promise about question retention.

## Lightweight usage safeguards

- Both providers enforce a nonempty question of at most 1,500 characters.
- Groq uses a 30-second HTTP timeout and 3-second connection timeout, with a
  512-token output cap and no automatic retries. HTTP timeouts bound individual
  network operations, rather than guaranteeing a total wall-clock deadline.
- Each Streamlit session can attempt at most 20 cloud requests, including failures.
  Clearing history, changing filters/data, or changing providers does not replenish
  this allowance. Local Ollama inference retains its previous behavior.
- HTTP 429 produces a friendly rate/quota message. Authentication failures,
  server errors, timeouts, malformed/truncated responses, and invalid intents
  produce safe messages without provider bodies, headers, keys, or raw exceptions.
  Errors/refusals never receive a verification indicator.
- History remains bounded to the latest 12 question/answer pairs.

Session limits are **not global abuse prevention**. A visitor can create new
sessions; this does not fully protect a public API key from quota exhaustion.
Before public access, set provider-side project/spend limits and review acceptable
usage, retention, and preview-model stability. No authentication/database/global
rate-limiting infrastructure is introduced in Step 2.

## Verification and next steps

The automated suite exercises Groq only through `httpx.MockTransport`; it must
not be interpreted as live hosted-model quality or account-access verification.
It checks request payload privacy, schema rejection, errors, credentials, both
adapters' equivalent deterministic results, cloud upload paths, missing settings,
budget isolation, history, and independent sessions. Existing dashboard and
financial tests remain in place. Uploaded files are provided as in-memory objects
in Streamlit AppTest; browser file-picker/download interactions remain manual.

Run:

```bash
.venv/bin/python -m pytest -v
.venv/bin/python scripts/validate_phase1.py
.venv/bin/python scripts/validate_phase2.py
.venv/bin/python scripts/validate_ai.py  # Local installed qwen3:8b only
```

Python 3.12 remains the intended Community Cloud runtime. Step 1's isolated
Python 3.12 environment is reused to verify this change with unchanged
requirements. Executed Step 2 results:

| Check | Python 3.14.7 (`.venv`) | Python 3.12.15 (isolated `/tmp` environment) |
| --- | --- | --- |
| Full `pytest -v` | 223 passed | 223 passed |
| Phase 1 validation | Passed, including 12 invalid-input cases | Passed, including 12 invalid-input cases |
| Phase 2 validation | All 5 reconciliations passed | All 5 reconciliations passed |
| `pip check` | No broken requirements | No broken requirements |

The 223 cases include all 171 original tests plus 52 new provider/UI cases.
`pip install -r requirements.txt` was rechecked in the Step 1 Python 3.12
environment; all unchanged pins are satisfied. Step 1 already tested a clean
installation of those same requirements. No new Python 3.12 environment or
unrelated package upgrade was needed in Step 2.

The local `scripts/validate_ai.py` passed all seven real `qwen3:8b` questions.
Additionally, Python 3.12 Streamlit AppTest rendered the local provider and
successfully used real Qwen inference to return EUR 117,542.02 income with the
verification indicator and no JSON. Cloud AppTest cases used mock HTTP transport
only, including both uploads without credentials, matching budget calculations,
charts, filters/reset, export availability, session isolation, and safe failures.

`git diff --check` passes. Reviewed tracked/new source and documentation contain
no common secret-token/private-key patterns or tracked secret/model files;
sensitive/local filename ignore checks pass. This is a focused repository scan,
not an exhaustive guarantee about every possible secret format. No files were
staged or committed. Step 1 ignore rules and report were preserved.

Before deployment, the owner must privately configure the provider/model/key,
review quotas/data policy/model availability, authorize live Groq intent tests,
and select Python 3.12 with repository-root `app.py` in Community Cloud.
No deployment, credential creation, commit, or push is part of this step.

## Step 3 live verification — 20 October 2026

The configured `groq` provider and `qwen/qwen3.8-27b` model were verified through
normal application configuration without inspecting or exposing credential values.
Ten successful live checks covered income, monthly expenses, highest expense
category, monthly cash flow, budget variance, two-month comparisons, monthly
summary, unsupported-question refusal, and uploaded transaction/budget answers.
Structured intents, deterministic answers, and manually verified Python totals
matched. Uploaded CSVs were synthetic test fixtures supplied through AppTest;
browser file-picker/download clicks still require manual checking.

Every outgoing live test payload was audited before transmission: only the fixed
test question, available months, schema, and static intent examples were present.
No uploaded rows, descriptions, budget records, or calculated amounts were attached.
User sessions, dataset switching, conversation clearing, filters/reset, and the
per-session request cap were also checked in the configured Streamlit application.

A real HTTP 429 interrupted an additional summary check. The adapter did not
automatically retry or expose provider output; a controlled check after cooldown
passed. Simulated 429 and timeout UI checks confirmed that the dashboard remained
usable and failed answers had no verification indicator. Provider rate/quota
limits remain an operational constraint for public concurrent use.

The complete offline suite passed all 223 tests; Phase 1/2 validations and
dependency checks passed. All seven real local Ollama/Qwen3 integration checks
also passed. Credentials, test questions, and raw provider responses were not
logged by the live verification harness. No repository code or deployment settings
were changed during Step 3. No live testing needs to be repeated for final Git
verification unless a relevant implementation change is made.
