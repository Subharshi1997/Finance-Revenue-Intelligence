"""Runs a table's declarative spec (see table_specs.py) through the generic
check primitives in checks.py and returns a single findings dict.
"""
from __future__ import annotations

import pandas as pd

from src.data_validation import checks
from src.data_validation.table_specs import MAX_DATE, MIN_DATE


def run_table_checks(table_name: str, df: pd.DataFrame, spec: dict, all_tables: dict[str, pd.DataFrame]) -> dict:
    findings: dict = {"table": table_name, "rows": len(df)}

    findings["missing_values"] = checks.missing_values(df, spec["required"])
    findings["duplicate_ids"] = checks.duplicate_ids(df, spec["id_col"])

    if spec.get("duplicate_subset"):
        findings["duplicate_business_rows"] = checks.duplicate_rows(df, spec["duplicate_subset"])

    date_issues = {}
    for col in spec.get("date_cols", []):
        if col in df.columns:
            n = checks.invalid_dates(df, col, MIN_DATE, MAX_DATE)
            if n:
                date_issues[col] = n
    findings["invalid_dates"] = date_issues

    order_issues = {}
    for earlier, later in spec.get("date_order", []):
        if earlier in df.columns and later in df.columns:
            n = checks.date_order_violations(df, earlier, later)
            if n:
                order_issues[f"{later} < {earlier}"] = n
    findings["date_order_violations"] = order_issues

    findings["negative_amounts"] = checks.negative_amounts(df, spec.get("negative_cols", []))

    range_issues = {}
    for col, low, high in spec.get("range_checks", []):
        if col in df.columns:
            n = checks.out_of_range(df.dropna(subset=[col]), col, low, high)
            if n:
                range_issues[col] = n
    findings["invalid_rates"] = range_issues

    cat_issues = {}
    for col, allowed in spec.get("categorical", {}).items():
        if col in df.columns:
            n = checks.invalid_categorical(df, col, allowed)
            if n:
                cat_issues[col] = n
    findings["invalid_categorical_values"] = cat_issues

    ref_issues = {}
    for child_col, parent_table, parent_col in spec.get("references", []):
        if child_col in df.columns and parent_table in all_tables:
            n = checks.referential_integrity(df, child_col, all_tables[parent_table], parent_col)
            if n:
                ref_issues[f"{child_col} -> {parent_table}.{parent_col}"] = n
    findings["referential_integrity_violations"] = ref_issues

    return findings
