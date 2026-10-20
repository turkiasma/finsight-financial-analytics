# FinSight — Business Financial Analytics

FinSight is a portfolio project for helping small businesses turn transaction
CSV files into understandable financial information. **Phases 1–3.5 and 5 are
implemented:** a fictional dataset, data loading/validation, and a reusable
financial analytics engine, together with an interactive Streamlit dashboard
and monthly budget comparisons. The optional AI financial assistant supports
local **qwen3:8b** through Ollama and explicitly configured hosted Groq inference.
Both use the same validated Python financial calculations.

<img width="1520" height="1096" alt="financial-dashboard" src="https://github.com/user-attachments/assets/70ec546c-e4cf-44c6-8c0c-0a8d1843e601" />
<img width="1220" height="1290" alt="budget-vs-actual" src="https://github.com/user-attachments/assets/0ce92a41-e725-468a-8de7-afb6ad1162f9" />
<img width="1220" height="774" alt="ai-financial-assistant" src="https://github.com/user-attachments/assets/c1e84795-ff37-40e2-89ea-215b68c52296" />


## Run the dashboard

Cloud deployment preparation is documented in
[Deployment readiness — Step 1](docs/deployment-readiness.md) and
[Groq integration — Step 2](docs/groq-integration.md). Local Ollama remains the
default. Groq has passed mocked tests and 10 live checks using privately
configured credentials. Public deployment remains a manual next step.

From the repository root, after installing the existing requirements:

```bash
source .venv/bin/activate
streamlit run app.py
```

Or without activating the environment:

```bash
.venv/bin/python -m streamlit run app.py
```

Open the Local URL printed in the terminal (normally `http://localhost:8501`).
Stop the server with Ctrl+C. No API keys, paid services, or model downloads are
required for the default local mode. The application has not been deployed.

### Dashboard features

- A light main workspace, navy sidebar, and consistent EUR formatting.
- Sample Dataset and Upload CSV modes, with validation before any calculation.
- Total Income, Total Expenses, and Net Cash Flow cards.
- Grouped monthly income/expense bars and a monthly net cash flow line chart.
- Expense and income category charts, ordered highest first.
- Monthly comparison table with percentage changes; undefined values show `N/A`.
- Financial Highlights based on the verified analytics outputs: peak income and
  expense months, largest expense category, and the latest income comparison.
- A transaction explorer with newest-first records and filtered CSV download.
- Inclusive date-range selection, category selection, explorer type selection,
  reset, and helpful empty/error states.
- Independent calendar-month Budget vs. Actual Expenses comparison, with
  sample/custom budgets, variance cards, category statuses, and a grouped chart.
- Local Ollama or configured Groq question interpretation with validated operations,
  Python-calculated answers, a verification indicator, and conversation controls.

The layout uses native Streamlit columns and full-width tables/charts. Narrow
screens may require table scrolling. Chart colors distinguish income (teal),
expenses (orange), and net cash flow (blue); legends and hover labels also identify
the series without relying on color alone.

### Sample data versus uploaded data

The default dataset is **Lumen Digital Studio**, containing fictional business
transactions. Upload CSV mode uses a neutral **Uploaded dataset** label; it does
not assume the uploaded records belong to that fictional company or are synthetic.
Upload a UTF-8 `.csv` with the exact five-column schema and supported categories
documented below. All amounts are assumed to be EUR. The existing strict loader
validates the whole file. An invalid file displays an error, hides results, and
never falls back to previous data. Correct the file and upload it again.

With no upload selected, the dashboard displays instructions instead of results.
Uploads are read in memory and are not written to the repository or a database.
Transaction and budget uploads remain available with either AI provider and when
AI is unconfigured. Uploaded transactions never automatically use sample budgets.
For the public demonstration, do not upload confidential financial or personal
information. Cloud CSV processing happens on Streamlit's servers. Groq receives
the question and limited intent metadata, without attached records, descriptions,
budgets, calculated amounts, or prior chat. Information typed into a question is
sent as part of that question. See the Step 2 privacy and quota notes.

### Filter and export behavior

**Analysis scope = date range + categories.** This scope drives the original KPI
cards, charts, monthly comparison, and Financial Highlights. The Budget vs.
Actual section has independent controls. Dates include both
endpoints, including a range containing only one date. The initial range covers
all available dates and all categories are selected.

**Explorer scope = analysis scope + transaction types.** Selecting only Expense
in the explorer leaves the Income KPI and charts intact. Selecting only expense
categories in the analysis scope, however, naturally produces zero income.
Category options always come from the currently selected dataset. Clearing all
categories yields an empty analysis. Clearing all transaction types yields an
empty explorer while preserving the analysis.

**Reset filters** restores the full date range, all available categories, and
both types. Switching datasets or replacing an upload with different contents
also resets filters to the new dataset's defaults. Resetting filters keeps the
selected data source.

**Download CSV** exports exactly the matching explorer records using the original
lowercase column names, dates in `YYYY-MM-DD`, two-decimal amounts, UTF-8 encoding,
and no index. The exported file can be loaded again by FinSight. It is ordered
newest first; interactive table sorting changes the on-screen order but does not
change export order or the exported set of records. Download is disabled when
the explorer has no matching rows.

Monthly comparisons follow the Phase 2 calendar-gap and zero-denominator rules.
A partial date range can produce partial-month totals: no adjustment or projection
is made. Highlights describe the selected scope, with the earliest month used
for tied peak totals and alphabetical category order for tied expense totals.
If the latest months are not consecutive or previous income is zero, the latest
income comparison is explicitly unavailable. No highlights are AI-generated.

## Phase 1 dataset

`data/sample_transactions.csv` contains exactly **200 fictional cash transactions**
for **Lumen Digital Studio**, an invented small digital services business.
It covers January–June 2026, with 30, 32, 34, 31, 36, and 37 records respectively.
Every month includes income and expenses. All descriptions and amounts are
synthetic; there is no real personal or banking information.

The sample combines recurring office rent (EUR 650), team salary payments
(EUR 4,200), software subscriptions, and maintenance subscription receipts with
variable service projects, digital template sales, advertising, and supplies.
Variable amounts and dates were generated using Python's standard `random`
module with seed 42. The committed CSV is the authoritative sample.

All amounts are **EUR**. This is a single-currency dataset; there is no currency
column or exchange-rate conversion. A user supplying another CSV must ensure
its amounts are also EUR.

```csv
date,description,category,type,amount
2026-01-05,Website development service,Service Revenue,Income,2500.00
2026-01-07,Monthly office rent,Rent,Expense,650.00
```

| Column | Meaning and validation |
| --- | --- |
| `date` | Real calendar date, exactly `YYYY-MM-DD` |
| `description` | Nonempty description of the cash transaction |
| `category` | One of the categories below, consistent with `type` |
| `type` | Exactly `Income` or `Expense`, case-sensitive |
| `amount` | Finite, strictly positive plain number, at most two decimal places |

Income categories: `Product Sales`, `Service Revenue`, `Subscription Revenue`.

Expense categories: `Rent`, `Salaries`, `Marketing`, `Software`, `Utilities`,
`Supplies`.

Sample amounts always have two decimal places. The loader also accepts values
such as `100` and `100.5`. Currency symbols, thousands separators, decimal commas,
scientific notation, and more than two decimal places are rejected. Category
and type names are case-sensitive; surrounding field whitespace is trimmed.

## Setup and validation

Python and Pandas provide data processing and analytics; Streamlit provides the
dashboard, Plotly the interactive charts, and Pytest the focused automated tests.
Phase 5 adds the official `ollama` client, `httpx` for transport, and Pydantic for
strict request validation. Step 2 reuses `httpx` for Groq's documented REST API;
no additional dependency or package-pin changes are needed.

From the repository root on Linux/macOS:

```bash
# If an environment is not already present:
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# Run with ordinary Python, without the -O flag (the script uses assertions):
python scripts/validate_phase1.py
```

If the existing environment is ready, run directly:

```bash
.venv/bin/python scripts/validate_phase1.py
```

Expected output:

```text
PASS: 200 transactions loaded; all five required columns present.
PASS: Valid dates across January-June 2026; both types in every month.
PASS: Positive amounts with two decimal places; currency assumed EUR.
PASS: Only Income/Expense types; valid categories match each type.
PASS: 12 invalid-input checks raised clear errors.
Phase 1 validation passed.
```

The script checks the actual sample and then tries twelve deliberately invalid
inputs. It is a focused Phase 1 smoke check, not the full Phase 4 Pytest suite.
It does not modify the CSV. No API keys, external APIs, or paid services are needed.
The dashboard run commands are documented above.

## How the loader works

```python
from src.data_loader import load_transactions

transactions = load_transactions("data/sample_transactions.csv")
print(transactions.head())
```

`src/data_loader.py` keeps data validation separate from later financial logic:

- `load_transactions(source)` reads a UTF-8 CSV path or file-like object using
  Pandas, then calls the validator. It reads fields as text first so invalid
  monetary values are not silently reinterpreted. Empty/malformed CSVs and
  encoding problems raise `ValueError`; missing paths raise `FileNotFoundError`.
- `validate_required_columns(transactions)` verifies the exact five-column
  schema. Missing, duplicate, or extra columns are rejected. Column order may
  vary in the input; output uses the documented order.
- `validate_transactions(transactions)` copies the input, trims whitespace,
  checks missing values, parses dates, validates category/type pairs, and
  converts valid amounts to numeric values. It returns a DataFrame with datetime
  dates, `float64` amounts, text fields, and a fresh index. Its input fields are
  expected to use CSV-style text values.
- `_reject_invalid(invalid, message)` is an internal helper that raises a readable
  `ValueError` identifying the first ten offending CSV row positions. The header
  counts as row 1. For quoted multiline descriptions, these are record positions
  rather than physical file line numbers.

For example, a negative amount in the first data record produces an error like:

```text
Invalid amount; expected a finite, strictly positive number with at most two decimal places (for example 1250.50). CSV rows: 2.
```

Validation stops at the first failing rule. Invalid values cause the entire load
to fail; the loader never silently drops transactions, fills missing amounts,
rounds excess precision, or guesses categories. It preserves input row order and
keeps duplicate records because identical transactions may be legitimate.
The sample is sorted by date. The reusable loader does not require 200 rows,
six months, or both transaction types; those are sample-specific checks.

## Phase 2 financial analytics

The functions in `src/analytics.py` accept the validated DataFrame from
`load_transactions()` or a filtered copy with the same columns and dtypes.
They do not reload files, repeat CSV validation, or change the input DataFrame.

| Function | Calculation and output |
| --- | --- |
| `calculate_total_income(df)` | Sum amounts for `Income`; returns a float |
| `calculate_total_expenses(df)` | Sum amounts for `Expense`; returns a float |
| `calculate_net_cash_flow(df)` | Income minus expenses; returns a float |
| `calculate_monthly_summary(df)` | Group by calendar month and transaction type; return `month`, `income`, `expenses`, `net_cash_flow` |
| `calculate_expenses_by_category(df)` | Sum only expenses per category; return `category`, `total_expenses` |
| `calculate_income_by_category(df)` | Sum only income per category; return `category`, `total_income` |
| `calculate_monthly_changes(df)` | Add `income_change_pct` and `expense_change_pct` to the monthly summary |

Income measures cash received, expenses measure cash paid, and net cash flow
measures the difference. Monthly figures apply the same formulas separately to
each calendar month. Category breakdowns show how cash is received or spent;
they sort by amount descending, with alphabetical category order for ties.

Month-over-month change is:

```text
((current month's amount - previous month's amount) / previous month's amount) * 100
```

For example, income rising from EUR 150 to EUR 300 is a 100% increase. Expenses
rising from EUR 60 to EUR 90 are a 50% increase. A fall from a positive amount
to zero is -100%. Percentage outputs are percentage points in the displayed
number: `50.0` means a 50% change, not `0.5`.

Monthly tables use chronological month-start timestamps, suitable for Plotly
later. An observed month with only income has zero recorded expenses, and vice
versa. Months without any records are omitted: missing records do not establish
zero business activity. Changes are `NaN` when there is no previous row, the
previous month's amount is zero, or the previous row is not the immediately
preceding calendar month. Thus January and March are never treated as adjacent
months. December–January comparisons work across years. A partially recorded
month is not automatically detected or adjusted.

All monetary results and percentage changes are rounded to two decimals at
output. Aggregation uses the underlying numeric amounts without rounding each
transaction again. No currency conversion takes place. An empty filtered
DataFrame returns `0.0` for totals and empty tables with the documented columns
for aggregations. It must retain the validated schema/dtypes, for example
`transactions.iloc[:0]`; a bare `pd.DataFrame()` is not a valid analytics input.

### Running Phase 2 and its tests

From the repository root:

```bash
.venv/bin/python scripts/validate_phase1.py
.venv/bin/python scripts/validate_phase2.py
.venv/bin/python -m pytest tests/test_analytics.py -v
```

The Phase 2 script displays all seven calculations and performs five checks:
income minus expenses equals net cash flow; monthly income and expenses match
their overall totals; and category income and expenses match their overall
totals. It uses an absolute floating-point tolerance of EUR 0.000001 with no
relative tolerance, so a one-cent discrepancy fails a check.

The focused Pytest suite contains 23 cases using a separate, manually verified
nine-transaction dataset. It covers totals, monthly and category aggregation,
percentage changes, zero denominators, missing months, year boundaries, empty
inputs, single transaction types, decimal amounts, deterministic sorting, and
input preservation. Broader loader testing remains part of Phase 4.

### Actual sample results (EUR)

The existing 200-row synthetic CSV produces total income of **117,542.02**,
total expenses of **36,013.80**, and net cash flow of **81,528.22**. These are
demonstration values, not claims about a real business.

| Month | Income | Expenses | Net Cash Flow |
| --- | ---: | ---: | ---: |
| January 2026 | 22,041.20 | 5,591.04 | 16,450.16 |
| February 2026 | 17,473.76 | 5,771.91 | 11,701.85 |
| March 2026 | 15,913.33 | 6,938.08 | 8,975.25 |
| April 2026 | 23,665.09 | 5,676.05 | 17,989.04 |
| May 2026 | 22,669.47 | 5,796.34 | 16,873.13 |
| June 2026 | 15,779.17 | 6,240.38 | 9,538.79 |

| Expense category | Total Expenses |
| --- | ---: |
| Salaries | 25,200.00 |
| Rent | 3,900.00 |
| Marketing | 3,350.11 |
| Supplies | 1,465.14 |
| Software | 1,135.47 |
| Utilities | 963.08 |

## Phase 3.5: Monthly Budget vs. Actual Expenses

A **budget** is an independently planned spending target. **Actual** means cash
paid in recorded Expense transactions for the same calendar month and category.
Income transactions are excluded. Targets do not change the original financial
KPIs or the recorded transactions.

The section has its own month selector and expense-category selection. It uses
the full transaction dataset for that calendar month, independently of all
sidebar filters. For example, a sidebar range of January 10–15 does not prorate
the January budget or restrict January's actual spending in this section.
The main Reset filters button resets the sidebar, leaving these independent
budget controls alone.

### Budget CSV format and sample targets

`data/sample_budgets.csv` contains **36 fictional spending targets**: all six
supported expense categories for January–June 2026, in EUR. Targets were chosen
independently of actual expenses. Rent (650) and salaries (4,200) reflect fixed
monthly commitments; marketing (500–700), software (200–250), utilities (180–190),
and supplies (250–350) reflect simple spending allowances. These values are not
financial forecasts or recommendations.

```csv
month,category,budget_amount
2026-01,Marketing,500.00
2026-01,Software,200.00
2026-01,Rent,650.00
```

The loader requires exactly these columns, real months in `YYYY-MM` format,
supported expense categories, finite non-negative plain numeric amounts with
at most two decimals, and unique `(month, category)` pairs. Sample amounts use
exactly two decimals. Zero is valid. Missing values, negative amounts, invalid
categories/months, duplicate targets, and malformed files are rejected with
readable errors. No invalid rows are silently removed.

The sample expense categories are Rent, Salaries, Marketing, Software, Utilities,
and Supplies. Income categories cannot have expense budgets.

### Selecting budgets

The bundled transaction sample defaults to **Sample budget**. To use your own
targets, select **Upload budget CSV** in the budget section and upload a matching
UTF-8 CSV. Budget uploads remain in memory and are not saved to disk.

Uploaded transactions default to **Upload budget CSV**, with no automatic sample
budget applied. You can explicitly choose Sample budget if its fictional targets
are relevant; the interface makes that choice clear. Replacing the transaction
dataset resets the budget source/month/category controls and separates the file
uploader state so a previous dataset's uploaded budget is not silently reused.
Invalid budget files hide budget results while leaving the transaction dashboard
and CSV export available.

### Variance and missing-budget rules

```text
Variance (EUR) = Actual - Budget
Variance (%)   = ((Actual - Budget) / Budget) * 100
```

- Positive variance: **Over budget**.
- Negative variance: **Under budget**.
- Zero variance: **On budget**.
- No matching target: **No budget set**, with budget and both variances `N/A`.
- A zero budget has undefined percentage variance (`N/A`), never infinity.
  Zero actual against a zero budget is On budget; positive actual is Over budget.

The comparison includes categories with budgets and no spending (zero recorded
actual) and categories with spending but no budget. It never replaces a missing
budget with zero. Categories with neither a target nor spending are omitted.
The grouped chart leaves a missing Budget bar absent rather than plotting zero.

Total Budget sums only explicit targets; Actual Expenses includes all selected
spending. If any displayed category lacks a target, overall Budget Variance is
`N/A` to avoid implying complete budget coverage. If there are no explicit
targets, Total Budget is also `N/A`. Financial outputs use two decimals.

January's fictional sample results:

| Category | Budget (EUR) | Actual (EUR) | Variance (EUR) | Status |
| --- | ---: | ---: | ---: | --- |
| Marketing | 500.00 | 401.59 | -98.41 | Under budget |
| Rent | 650.00 | 650.00 | 0.00 | On budget |
| Salaries | 4,200.00 | 4,200.00 | 0.00 | On budget |
| Software | 200.00 | 162.07 | -37.93 | Under budget |
| Supplies | 250.00 | 0.00 | -250.00 | Under budget |
| Utilities | 180.00 | 177.38 | -2.62 | Under budget |
| **Total** | **5,980.00** | **5,591.04** | **-388.96** | **Under budget** |

### Monthly comparison limitations

Only months containing transaction records are offered in the UI. The calendar
selector uses every available record for the selected month; it does not infer
the start/end of activity from the first/last transaction date or compare an
arbitrary partial date slice against a full budget. However, a CSV alone cannot
prove that all records for that month were provided. Users must supply complete
calendar-month records, not an unfinished month's extract. Zero actual means no
recorded expenses, not proof of zero business spending. Currency is assumed EUR;
no currency conversion, accounting profit calculation, or forecasting is added.

Budget logic lives in `src/budgets.py`: `load_budgets()` reads and validates files,
`validate_budgets()` checks a text DataFrame, `calculate_budget_comparison()` merges
monthly targets and actuals, and `summarize_budget_comparison()` computes card
totals without hiding missing coverage. `src/budget_dashboard.py` handles the new
section's widgets and presentation; `budget_actual_chart()` in `src/charts.py`
only visualizes those results. The existing transaction loader and analytics
remain unchanged.

To test manually, run `streamlit run app.py`, view January with sample budgets,
then change the sidebar dates and confirm the budget result stays unchanged.
Choose another budget month or a subset of expense categories. Upload a custom
budget with a zero target and omit a category that has spending; confirm `N/A`
percentages and the distinct statuses. Upload an invalid budget to confirm the
error stays within this section. Switch to uploaded transactions and verify no
sample budget is automatically applied.

## Phase 5: Local AI Financial Assistant

The **FinSight AI Assistant** understands self-contained questions using the
existing local `qwen3:8b` model. Ollama is optional: connection failures, a missing
model, or failed requests do not prevent dashboard analysis or CSV export.
In local mode only `qwen3:8b` is allowed. There are no fallback models or model
downloads. Hosted Groq is an explicit alternative documented below; the
application has no RAG pipelines, generated SQL, or autonomous tools.

### Setup and configuration

Ollama and `qwen3:8b` are already installed on the development computer. Confirm
the existing installation without downloading anything:

```bash
ollama list
ollama ps
```

If the local daemon is not running, start the existing installation in a separate
terminal with `ollama serve` (or use its existing Linux service). Do not start a
second daemon if the service is already running.

Install the Python dependencies, then run FinSight:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
export AI_PROVIDER=ollama
export OLLAMA_MODEL=qwen3:8b
export OLLAMA_BASE_URL=http://localhost:11434
streamlit run app.py
```

These environment variables are optional and default to the values shown.
Configuration is centralized in `OllamaConfig` in `src/ai_assistant.py`. An
`OLLAMA_MODEL` value other than `qwen3:8b` is rejected. The endpoint must be a
loopback address (`localhost`, `127.0.0.1`, or `::1`), rather than an external AI
service. Settings can also be supplied through flat Streamlit Secrets; an explicit
environment value takes precedence. `.env` files are not automatically read.

Requests have a 60-second read timeout and a 3-second connection timeout. Model
availability checks use a 2-second timeout and are cached for up to 30 seconds.
Checking availability lists model metadata; it does not run inference or pull a
model. A cached available status does not guarantee the next request will succeed;
request-time failures are handled separately.

### Architecture and numerical reliability

```text
Question → Qwen3 structured intent → strict Python validation
         → existing analytics/budget functions → deterministic answer + result
```

Qwen3 receives the question, the available month identifiers, the allowed category
names, and the request schema. It does not receive individual transaction
descriptions or financial amounts. It selects an operation and parameters; it
does not supply monetary results. The client requests schema-constrained JSON,
`think=False`, temperature 0, and bounded output. Only `message.content` is parsed;
reasoning content is neither displayed nor stored.

Pydantic rejects missing/extra fields, unknown operations, incorrect types,
invalid months, incompatible categories, and unsuitable parameters. Python also
checks that a requested month exists in the loaded transactions and that any
filter override is explicitly supported by the question's month/category text.
Valid JSON alone is never treated as a trusted instruction. A fixed whitelist
routes requests to existing financial functions, with no `eval`, `exec`, shell
commands, or SQL execution.

Answers use deterministic business-facing Markdown templates, with short
conclusions and selective bold emphasis. Category labels are escaped and raw
HTML is disabled. EUR amounts come from existing calculations and display two
decimal places; negative cash flow uses `-€25.00`, while budget overruns and
unspent targets use positive amounts. Budget percentages retain the budget
engine's denominator and are not recalculated by the wording templates.
Successfully calculated answers
show a discreet **✓ Verified using financial data** caption, referring to Python's
deterministic calculations. Errors and unsupported requests have no verification
indicator. Structured results, including the interpreted operation, exact scope,
and computed values, remain internal for application logic and tests; no raw JSON
or calculation-detail panels are displayed in chat.
Missing budgets stay distinct from zero targets, undefined percentages remain
`N/A`, and net cash flow is never labelled accounting net profit.

### Supported questions and exact scope rules

Supported questions include overall income/expenses/cash flow, monthly summaries,
peak income/expense months, income/expense category breakdowns, the largest expense
category, main income sources, comparisons of two months, monthly budget/actual
variances, and categories exceeding a budget.

- **No named month or category:** use the sidebar analysis dates and categories.
  The explorer's transaction-type filter does not affect the answer.
- **Explicit month:** use all recorded transactions in that full calendar month,
  replacing the sidebar date range. Existing sidebar categories still apply.
  Two named months are allowed for comparisons of income, expenses, or cash flow.
- **Explicit category:** use that exact supported category, replacing the sidebar
  category selection. Existing sidebar dates still apply unless a month is named.
- **Yearless month names:** resolve only when unambiguous in loaded data or the
  question specifies a single shared year. Otherwise ask for an explicit year.
- **Budget questions:** always require one explicit month and compare its full
  recorded calendar month, without proration. Use the currently selected and
  validated budget file from the budget section. When no category is named, use
  the sidebar's selected expense categories. Budget-panel month/category controls
  do not filter chat. Uploaded transactions never acquire sample budgets unless
  the user explicitly selected that source in the budget section.
- **Missing records:** reject absent transaction months and absent explicitly
  requested categories rather than substitute another period/category. A month
  missing records within selected categories is not invented as a zero-valued
  month in a two-month comparison. Zero recorded expenses in an income-only
  month still means no expenses recorded, not proof of no business spending.
- **Conversation history:** retain at most twelve question/answer pairs for display.
  Changes to the dataset, sidebar date/category scope, validated budget contents,
  or endpoint clear the history. The Clear conversation button also resets it.
  Previous messages are not sent to Qwen; every question must stand on its own.

Examples:

```text
What is the total income?
What were the total expenses in March 2026?
Which expense category had the highest spending?
What was our net cash flow in June 2026?
Compare income between April and May 2026.
Did we exceed our Marketing budget in February 2026?
Which categories were over budget in March 2026?
```

Use exact category names for category-specific questions. Comparisons report
the verified amounts for the two named months and their absolute change,
calculated deterministically from those amounts solely for the answer wording.
No new percentage-change or forecasting formula is inferred. Use sidebar date filters for arbitrary
day-level date ranges. Forecasts, accounting profit/margins, investment advice,
stock predictions, multiple named categories in one request, and contextual
follow-ups such as “what about that month?” are unsupported.

### Verification and troubleshooting

The automated suite mocks Ollama and does not require a service, model, GPU, or
network connection. Run the existing checks and complete suite:

```bash
.venv/bin/python scripts/validate_phase1.py
.venv/bin/python scripts/validate_phase2.py
.venv/bin/python -m pytest -v
```

To explicitly test the real installed Qwen model:

```bash
.venv/bin/python scripts/validate_ai.py
```

The live script checks seven natural-language questions, their interpreted scopes,
Python results, and controlled refusal of an unsupported investment question.
It never downloads a model. Live checks passed against Ollama 0.33.3 and the
official Python client 0.6.3 with non-thinking structured outputs:

| Question | Verified sample result |
| --- | --- |
| Total income | EUR 117,542.02 |
| March 2026 expenses | EUR 6,938.08 |
| Largest expense category | Salaries, EUR 25,200.00 |
| June 2026 net cash flow | EUR 9,538.79 |
| February Marketing budget | EUR 550.00 budget, EUR 437.30 actual, EUR -112.70 variance (-20.49%), Under budget |
| Unsupported investment question | Refused without a financial answer |
| April/May income | EUR 23,665.09 / EUR 22,669.47 |

**Ollama unavailable:** check the existing daemon and `OLLAMA_BASE_URL`. The
dashboard continues working. Availability indicators may lag changes by up to
30 seconds; rerun after the cache expires.

**Qwen3 model unavailable:** inspect `ollama list` for the exact `qwen3:8b` tag.
The application does not silently switch models or install missing ones.

**Timeout:** cold loading or limited CPU/GPU memory may make inference slow.
The failed request generates no monetary answer; retry after the existing model
has warmed up. No automatic download, fallback, or unbounded retry occurs.

**Invalid request or scope mismatch:** rephrase with explicit month/year and an
exact supported category. Intent extraction can still misunderstand natural
language; check the question's scope against the documented filter rules. Invalid structured requests
are rejected rather than repaired into guessed financial values.

**Incompatible API options:** the tested versions support `think=False` and a JSON
schema. An API rejecting those options produces a controlled error asking you to
check versions; FinSight does not fall back to unconstrained text generation.
The `/no_think` instruction also appears in the extraction prompt.

The network boundary was also tested with an unreachable local endpoint: only
chat was disabled and the dashboard still rendered. Browser visual layout and
file-picker/download clicks remain manual checks. The model can misunderstand
intent despite schema validation; it cannot change financial formulas or inject
its own monetary values into the deterministic answer.

For public hosting, select `AI_PROVIDER=groq` explicitly and supply `GROQ_MODEL`
and `GROQ_API_KEY` privately through Streamlit Secrets. The documented Qwen option
is `qwen/qwen3.8-27b`; the exact model must be configured rather than inferred
from the presence of a key. It uses JSON object mode and the existing strict
Python schema validation. See [Step 2 configuration](docs/groq-integration.md).
Missing settings disable only chat. There is no automatic provider fallback.
Streamlit Community Cloud cannot reach Ollama on your personal computer through
localhost. Do not expose that endpoint publicly. No deployment has been performed.

Official API references: [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs),
[thinking controls](https://docs.ollama.com/capabilities/thinking), and the
[official Python client](https://github.com/ollama/ollama-python).

## Financial assumptions and limitations

Amounts record cash received or paid. `type` determines the direction of each
positive amount. Net cash flow means income minus expenses; it must
not be described as accounting net profit. This dataset does not model accruals,
receivables, depreciation, tax reporting, or a complete accounting ledger.

Float amounts are convenient for later Pandas analysis but use binary floating
point. They are not an exact decimal accounting representation; a production
ledger would need a deliberate integer-cent or decimal policy. Validation can
check structure and consistency, but cannot verify real payments, currency, or
the truth of a description. New categories require updating `CATEGORY_TYPES`.
The project uses synthetic business data and assumes EUR throughout. It does
not make financial predictions or investment recommendations.

## Phase 3 architecture and verification

The application separates responsibilities so the interface cannot quietly
introduce different financial formulas:

| File | Responsibility |
| --- | --- |
| `src/data_loader.py` | Read and validate CSV transactions; unchanged in Phase 3 |
| `src/analytics.py` | Calculate all totals, monthly summaries, and category aggregations; unchanged in Phase 3 |
| `src/dashboard.py` | Select datasets, filter scopes, serialize CSV exports, format comparisons, and describe analytics outputs |
| `src/charts.py` | Turn already aggregated results into Plotly figures, without financial aggregation |
| `app.py` | Build the page, manage widget state, and connect data, analytics, and charts |
| `.streamlit/config.toml` | Define the light workspace/navy sidebar theme and disable usage telemetry |
| `src/ai_assistant.py` | Central local-model configuration, availability checks, and structured Qwen extraction |
| `src/ai_providers.py` | Explicit provider configuration, Ollama adapter, and intent-only Groq REST adapter |
| `src/ai_queries.py` | Strict request schema, query-scope rules, existing financial function routing, and deterministic answers |
| `src/ai_dashboard.py` | Native chat widgets, cached connection indicator, and scope-isolated conversation state |

The cash flow chart inserts blank plotting positions for absent calendar months
so it does not join a line through missing activity. It does not invent zero
values or change the analytics.

Run all checks:

```bash
.venv/bin/python scripts/validate_phase1.py
.venv/bin/python scripts/validate_phase2.py
.venv/bin/python -m pytest -v
```

The original suite includes **67 tests**: 23 analytics cases and
44 dashboard cases. Phase 3 checks cover sample/upload selection, invalid uploads,
inclusive dates, single dates, categories, type-only explorer filtering, KPI scope,
empty results, loader-compatible CSV exports, chart values/empty figures, missing
chart months, and presentation/highlights. Native Streamlit `AppTest` also checks
rendering, reset, dataset replacement, invalid-file recovery, and incomplete date
selection (including scalar dates, empty selections, missing endpoints, and
completion/reset after an incomplete range). Uploaded file objects are supplied in memory for those page tests;
they do not automate the browser's file picker.

Phase 3.5 adds 36 budget validation, calculation, and page integration tests,
bringing the pre-AI suite to **103 tests**,
including zero/missing budgets, monthly filtering, exclusion of income, input
preservation, independent filters, explicit budget selection for uploaded data,
invalid-budget recovery, and chart values. Existing dashboard assertions identify
the original KPI cards by label so the additional budget cards do not change
what those regression tests verify.

Phase 5 adds 68 mocked-model, wording, and query-routing tests (171 tests total), covering
schema/type validation, Qwen request settings, model failures, manually verified
financial/budget answers, missing data, zero budgets, filters, safe routing,
conversation isolation, and offline/online chat presentation. Presentation checks
cover the verification caption, internal result preservation, absence of visible
JSON/detail panels, successful history rerendering, and unverified error/refusal
messages. Wording tests cover natural conclusions, budget yes/no answers, zero/missing
budgets, signed currency, calendar labels, exact month-comparison differences,
unchanged internal values, and safely escaped labels. Existing Reset
filters tests now target the button's stable key rather than its screen position.

Deployment Step 2 adds 52 offline provider/privacy/cloud UI cases, bringing the
suite to **223 passing tests on Python 3.14.7 and Python 3.12.15**. Both Phase 1/2
scripts and dependency checks pass on both versions. All seven real local Qwen
checks pass; a Python 3.12 Streamlit chat also succeeds with real local Qwen.
The automated suite uses mocked Groq inference and does not load local Streamlit
Secrets. Step 3 separately passed **10 live Groq checks** with
`qwen/qwen3.8-27b`, including synthetic uploaded transactions/budgets and an
unsupported-question refusal. Outgoing payloads were checked for absence of
attached records and financial amounts. A real HTTP 429 stopped its request
without automatic retries; the summary check passed after cooldown. Simulated
rate-limit and timeout UI checks also passed. No credentials or raw provider
responses were logged. Public hosting has not been configured or deployed.

Both phase validation scripts pass, and the local Streamlit server has been
checked for successful page and health responses. AppTest verifies rendering and
interactions without a browser; visual layout, mobile behavior, file picker, and
browser download clicks still need a manual browser check.

For a quick manual demonstration: open the sample, choose Expense in transaction
types and confirm KPIs remain unchanged, choose Rent in categories, reset filters,
upload a valid CSV, then download and reopen the filtered export. Try an invalid
CSV to see the validation message and confirm prior results disappear.

## Planned phases and inspiration

Phase 4 can broaden testing and documentation separately. Phase 5 now provides
local Qwen3 intent extraction grounded in existing calculations. There is no
RAG, autonomous agent, forecasting, or investment-recommendation functionality.

Architectural inspiration:
[TasniaNitu/finance-ai-assistant](https://github.com/TasniaNitu/finance-ai-assistant)
([MIT license](https://github.com/TasniaNitu/finance-ai-assistant/blob/main/LICENSE)).
Its CSV processing, dashboard, and optional local assistant informed the general
roadmap. FinSight's Phase 1 code and synthetic business dataset were written
independently; no reference source code or dataset was copied.
