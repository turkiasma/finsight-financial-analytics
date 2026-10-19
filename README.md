# FinSight — Business Financial Analytics

FinSight is a portfolio project for helping small businesses turn transaction
CSV files into understandable financial information. **Phases 1 and 2 are
implemented:** a fictional dataset, data loading/validation, and a reusable
financial analytics engine. The Streamlit dashboard and AI assistant are future
work.

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

Python and Pandas provide the Phase 1 and 2 functionality; Pytest verifies the
analytics. The existing `requirements.txt` also lists dependencies intended for
later phases, including Streamlit and Plotly. No new dependencies were added.

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
The empty `app.py` is not yet a runnable dashboard.

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

## Planned phases and inspiration

Later phases will add an interactive Streamlit and Plotly dashboard, a broader
Pytest suite, and optional local Qwen/Ollama questions grounded in verified
calculations. The dashboard, charts, and AI assistant are not implemented yet.

Architectural inspiration:
[TasniaNitu/finance-ai-assistant](https://github.com/TasniaNitu/finance-ai-assistant)
([MIT license](https://github.com/TasniaNitu/finance-ai-assistant/blob/main/LICENSE)).
Its CSV processing, dashboard, and optional local assistant informed the general
roadmap. FinSight's Phase 1 code and synthetic business dataset were written
independently; no reference source code or dataset was copied.
