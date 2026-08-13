"""Reusable, table-agnostic data-quality check primitives.

Each function returns a small dict describing what it found. Functions never
mutate the input DataFrame; callers decide what to do with the findings.
"""
from __future__ import annotations

import pandas as pd


def missing_values(df: pd.DataFrame, columns: list[str]) -> dict:
    counts = {c: int(df[c].isna().sum()) for c in columns if c in df.columns}
    return {c: n for c, n in counts.items() if n > 0}


def duplicate_ids(df: pd.DataFrame, id_col: str) -> int:
    return int(df[id_col].duplicated(keep=False).sum())


def duplicate_rows(df: pd.DataFrame, subset: list[str]) -> int:
    return int(df.duplicated(subset=subset, keep=False).sum())


def invalid_dates(df: pd.DataFrame, date_col: str, min_date: str, max_date: str) -> int:
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    unparsable = parsed.isna() & df[date_col].notna()
    out_of_range = parsed.notna() & ((parsed < min_date) | (parsed > max_date))
    return int((unparsable | out_of_range).sum())


def date_order_violations(df: pd.DataFrame, earlier_col: str, later_col: str) -> int:
    earlier = pd.to_datetime(df[earlier_col], errors="coerce")
    later = pd.to_datetime(df[later_col], errors="coerce")
    return int((later < earlier).sum())


def negative_amounts(df: pd.DataFrame, columns: list[str]) -> dict:
    counts = {}
    for c in columns:
        if c in df.columns:
            n = int((df[c] < 0).sum())
            if n > 0:
                counts[c] = n
    return counts


def out_of_range(df: pd.DataFrame, column: str, low: float, high: float) -> int:
    return int(((df[column] < low) | (df[column] > high)).sum())


def invalid_categorical(df: pd.DataFrame, column: str, allowed: set[str]) -> int:
    return int((~df[column].isin(allowed) & df[column].notna()).sum())


def referential_integrity(child: pd.DataFrame, child_key: str, parent: pd.DataFrame, parent_key: str) -> int:
    valid_keys = set(parent[parent_key].dropna())
    child_keys = child[child_key].dropna()
    return int((~child_keys.isin(valid_keys)).sum())
