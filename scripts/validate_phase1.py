"""Run focused Phase 1 checks: python scripts/validate_phase1.py."""

from io import StringIO
from pathlib import Path
import sys

import pandas as pd

# Resolve imports and the sample path independently of the working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import CATEGORY_TYPES, REQUIRED_COLUMNS, load_transactions


def main() -> None:
    """Check the sample and a small selection of invalid CSV records."""
    sample_path = PROJECT_ROOT / "data" / "sample_transactions.csv"
    transactions = load_transactions(sample_path)
    assert len(transactions) == 200
    assert tuple(transactions.columns) == REQUIRED_COLUMNS
    assert pd.api.types.is_datetime64_any_dtype(transactions["date"])
    assert transactions["date"].notna().all()
    assert transactions["amount"].gt(0).all()
    assert set(transactions["type"]) == {"Income", "Expense"}
    assert transactions["category"].isin(CATEGORY_TYPES).all()
    assert transactions["category"].map(CATEGORY_TYPES).eq(transactions["type"]).all()
    months = transactions["date"].dt.to_period("M")
    assert sorted(months.unique()) == list(pd.period_range("2026-01", "2026-06", freq="M"))
    assert transactions.groupby(months)["type"].nunique().eq(2).all()
    raw = pd.read_csv(sample_path, dtype="string", keep_default_na=False)
    assert raw["amount"].str.fullmatch(r"[0-9]+\.[0-9]{2}").all()
    assert raw["date"].str.fullmatch(r"2026-[0-9]{2}-[0-9]{2}").all()
    print("PASS: 200 transactions loaded; all five required columns present.")
    print("PASS: Valid dates across January-June 2026; both types in every month.")
    print("PASS: Positive amounts with two decimal places; currency assumed EUR.")
    print("PASS: Only Income/Expense types; valid categories match each type.")

    # These are focused loader smoke checks, not the full Phase 4 test suite.
    example = raw.iloc[[0]].copy()
    invalid_cases = [
        ("missing column", example.drop(columns="category")),
        ("invalid type", example.assign(type="Transfer")),
        ("invalid date", example.assign(date="2026-02-30")),
        ("negative amount", example.assign(amount="-10.00")),
        ("zero amount", example.assign(amount="0.00")),
        ("missing value", example.assign(description="   ")),
        ("invalid category", example.assign(category="Unknown")),
        ("inconsistent category/type", example.assign(category="Rent", type="Income")),
        ("nonnumeric amount", example.assign(amount="not-a-number")),
        ("infinite amount", example.assign(amount="inf")),
        ("excess decimal places", example.assign(amount="12.345")),
        ("wrong date format", example.assign(date="01/02/2026")),
    ]
    for name, invalid in invalid_cases:
        try:
            load_transactions(StringIO(invalid.to_csv(index=False)))
        except ValueError as error:
            assert str(error), f"Missing error explanation for {name}"
        else:
            raise AssertionError(f"Loader accepted {name}")
    print(f"PASS: {len(invalid_cases)} invalid-input checks raised clear errors.")
    print("Phase 1 validation passed.")


if __name__ == "__main__":
    main()
