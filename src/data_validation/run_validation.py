"""Phase 4 entry point: validate every raw table, clean genuine ingestion
garbage, write the cleaned tables to data/processed/, and write a Markdown
data-quality report to docs/data_quality_report.md.

Run from the project root:
    python src/data_validation/run_validation.py
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from src.data_validation import cleaning, cross_table_checks, report
from src.data_validation.table_specs import TABLE_SPECS
from src.data_validation.validators import run_table_checks

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
DOCS_DIR = ROOT / "docs"

TABLE_NAMES = [
    "merchants",
    "contracts",
    "transactions",
    "invoices",
    "payments",
    "refunds",
    "credit_notes",
    "collection_activity",
    "disputes",
]


def load_raw_tables() -> dict[str, pd.DataFrame]:
    return {name: pd.read_csv(RAW_DIR / f"{name}.csv") for name in TABLE_NAMES}


def run_all_checks(tables: dict[str, pd.DataFrame]) -> list[dict]:
    return [run_table_checks(name, tables[name], TABLE_SPECS[name], tables) for name in TABLE_NAMES]


def clean_all_tables(tables: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], dict[str, dict]]:
    cleaned = dict(tables)
    stats = {}

    cleaned["transactions"], stats["transactions"] = cleaning.clean_transactions(tables["transactions"])
    cleaned["invoices"], stats["invoices"] = cleaning.clean_invoices(tables["invoices"])
    cleaned["payments"], stats["payments"] = cleaning.clean_payments(tables["payments"])
    cleaned["credit_notes"], stats["credit_notes"] = cleaning.clean_credit_notes(tables["credit_notes"])

    valid_transaction_ids = set(cleaned["transactions"]["transaction_id"])
    cleaned["refunds"], stats["refunds"] = cleaning.clean_refunds(tables["refunds"], valid_transaction_ids)

    for name in ["merchants", "contracts", "collection_activity", "disputes"]:
        id_col = TABLE_SPECS[name]["id_col"]
        cleaned[name], stats[name] = cleaning.dedupe_by_primary_key(tables[name], id_col)

    return cleaned, stats


def main() -> None:
    print("Loading raw tables...")
    raw_tables = load_raw_tables()
    for name, df in raw_tables.items():
        print(f"  {name}: {len(df):,} rows")

    print("\nRunning per-table quality checks...")
    findings = run_all_checks(raw_tables)

    print("Running cross-table finance checks...")
    missing_inv = cross_table_checks.missing_invoices(raw_tables["transactions"], raw_tables["invoices"])
    dup_pay = cross_table_checks.duplicate_payments(raw_tables["payments"])
    unmatched_pay = cross_table_checks.unmatched_payments(raw_tables["payments"], raw_tables["invoices"])
    orphan_pay = cross_table_checks.orphan_payments(raw_tables["payments"])
    unpaid_inv = cross_table_checks.invoices_without_payment(raw_tables["invoices"], raw_tables["payments"])
    mismatches = cross_table_checks.amount_mismatches(raw_tables["invoices"], raw_tables["payments"])

    print(f"  Missing invoices: {len(missing_inv):,}")
    print(f"  Duplicate payments: {len(dup_pay):,}")
    print(f"  Unmatched payments: {len(unmatched_pay):,}")
    print(f"  Orphan payments: {len(orphan_pay):,}")
    print(f"  Invoices with no payment: {len(unpaid_inv):,}")
    print(f"  Amount mismatches: {len(mismatches):,}")

    print("\nCleaning tables (ingestion garbage only)...")
    cleaned_tables, cleaning_stats = clean_all_tables(raw_tables)
    for name, stats in cleaning_stats.items():
        print(f"  {name}: {stats['rows_before']:,} -> {stats['rows_after']:,}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in cleaned_tables.items():
        df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False)
    print(f"\nCleaned tables written to {PROCESSED_DIR}")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / "data_quality_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Data Quality Report\n\n")
        f.write(f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(
            "This report covers the 9 raw finance tables before cleaning. "
            "See 'Cleaning actions applied' for what was corrected before loading "
            "into the SQL database, and 'Cross-table finance checks' for business "
            "exceptions that are intentionally preserved for downstream analysis.\n\n"
        )
        for finding in findings:
            f.write(report.render_table_section(finding))
        f.write(
            report.render_cross_table_section(
                missing_inv, dup_pay, unmatched_pay, orphan_pay, unpaid_inv, mismatches
            )
        )
        f.write("\n")
        f.write(report.render_cleaning_section(cleaning_stats))

    print(f"Data quality report written to {report_path}")


if __name__ == "__main__":
    main()
