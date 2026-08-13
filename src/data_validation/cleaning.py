"""Cleaning fixes only genuine ingestion garbage (system-level duplicate IDs,
unusable orphan rows, physically invalid amounts). Business-meaningful
exceptions - duplicate payments, missing invoices, partial payments, disputed
invoices - are left untouched: they are what the reconciliation and revenue
leakage engines in later phases are built to detect.
"""
from __future__ import annotations

import pandas as pd


def clean_transactions(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    before = len(df)
    stats = {}

    df = df.drop_duplicates(subset=["transaction_id"], keep="first")
    stats["duplicate_transaction_id_rows_dropped"] = before - len(df)

    n_missing_merchant = df["merchant_id"].isna().sum()
    df = df[df["merchant_id"].notna()]
    stats["missing_merchant_id_rows_dropped"] = int(n_missing_merchant)

    n_negative = (df["transaction_amount"] < 0).sum()
    df = df[df["transaction_amount"] >= 0]
    stats["negative_amount_rows_dropped"] = int(n_negative)

    n_missing_status = df["payment_status"].isna().sum()
    df = df.copy()
    df["payment_status"] = df["payment_status"].fillna("Unknown")
    stats["missing_payment_status_imputed"] = int(n_missing_status)

    stats["rows_before"] = before
    stats["rows_after"] = len(df)
    return df, stats


def clean_invoices(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    before = len(df)
    stats = {}

    df = df.drop_duplicates(subset=["invoice_id"], keep="first")
    stats["duplicate_invoice_id_rows_dropped"] = before - len(df)

    df = df.copy()
    missing_due = df["due_date"].isna()
    if missing_due.any():
        terms = pd.to_timedelta(30, unit="D")
        df.loc[missing_due, "due_date"] = (
            pd.to_datetime(df.loc[missing_due, "invoice_date"]) + terms
        ).dt.strftime("%Y-%m-%d")
    stats["missing_due_date_imputed"] = int(missing_due.sum())

    # Incomplete invoices: all monetary fields blank except tax_rate and
    # expected_fee. Recovered from expected_fee, the way Finance would fix an
    # incomplete ledger entry rather than leave total_invoice_amount null.
    incomplete = df["total_invoice_amount"].isna() & df["expected_fee"].notna()
    if incomplete.any():
        df.loc[incomplete, "subtotal"] = df.loc[incomplete, "expected_fee"]
        df.loc[incomplete, "discount"] = 0.0
        df.loc[incomplete, "taxable_amount"] = df.loc[incomplete, "expected_fee"]
        df.loc[incomplete, "tax_amount"] = (
            df.loc[incomplete, "expected_fee"] * df.loc[incomplete, "tax_rate"]
        ).round(2)
        df.loc[incomplete, "total_invoice_amount"] = (
            df.loc[incomplete, "taxable_amount"] + df.loc[incomplete, "tax_amount"]
        ).round(2)
        df.loc[incomplete, "billed_fee"] = df.loc[incomplete, "expected_fee"]
        df.loc[incomplete, "invoice_error_flag"] = True
    stats["incomplete_invoice_amounts_recovered_from_expected_fee"] = int(incomplete.sum())

    stats["rows_before"] = before
    stats["rows_after"] = len(df)
    return df, stats


def dedupe_by_primary_key(df: pd.DataFrame, id_col: str) -> tuple[pd.DataFrame, dict]:
    before = len(df)
    df = df.drop_duplicates(subset=[id_col], keep="first")
    return df, {"duplicate_id_rows_dropped": before - len(df), "rows_before": before, "rows_after": len(df)}
