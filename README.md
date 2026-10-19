# FinSight — Business Financial Analytics

FinSight is a portfolio project for helping small businesses turn transaction
CSV files into understandable financial information. **Phases 1–3.5 are
implemented:** a fictional dataset, data loading/validation, and a reusable
financial analytics engine, together with an interactive Streamlit dashboard
and monthly budget comparisons.
The optional AI assistant is planned for Phase 5 and is not implemented.

## Run the dashboard

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
required. This is a local application; it has not been deployed.

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
All were already listed in `requirements.txt`; no dependencies were added.

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
bringing the suite to **103 passing tests**,
including zero/missing budgets, monthly filtering, exclusion of income, input
preservation, independent filters, explicit budget selection for uploaded data,
invalid-budget recovery, and chart values. Existing dashboard assertions identify
the original KPI cards by label so the additional budget cards do not change
what those regression tests verify.

Both phase validation scripts pass, and the local Streamlit server has been
checked for successful page and health responses. AppTest verifies rendering and
interactions without a browser; visual layout, mobile behavior, file picker, and
browser download clicks still need a manual browser check.

For a quick manual demonstration: open the sample, choose Expense in transaction
types and confirm KPIs remain unchanged, choose Rent in categories, reset filters,
upload a valid CSV, then download and reopen the filtered export. Try an invalid
CSV to see the validation message and confirm prior results disappear.

## Planned phases and inspiration

Phase 4 will broaden testing and documentation. Phase 5 will add optional local
Qwen/Ollama questions grounded in verified calculations. No Ollama, Qwen, AI chat,
RAG, or model integration is implemented. Phase 3 does not add predictions or
investment recommendations.

Architectural inspiration:
[TasniaNitu/finance-ai-assistant](https://github.com/TasniaNitu/finance-ai-assistant)
([MIT license](https://github.com/TasniaNitu/finance-ai-assistant/blob/main/LICENSE)).
Its CSV processing, dashboard, and optional local assistant informed the general
roadmap. FinSight's Phase 1 code and synthetic business dataset were written
independently; no reference source code or dataset was copied.
