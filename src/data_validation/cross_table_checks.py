"""Cross-table finance checks: referential integrity gaps and billing/AR
exceptions that span more than one table. These findings are business
signals (missing invoices, duplicate payments, unmatched payments) that later
phases (reconciliation, revenue leakage) are meant to detect and analyze -
they are reported here, not silently cleaned away.
"""
from __future__ import annotations

import pandas as pd


def missing_invoices(transactions: pd.DataFrame, invoices: pd.DataFrame) -> pd.DataFrame:
    """Merchant-months with successful transactions but no invoice row."""
    txn = transactions[transactions["payment_status"] == "Success"].copy()
    txn["billing_period"] = pd.to_datetime(txn["transaction_date"], errors="coerce").dt.to_period("M")
    txn_months = txn.dropna(subset=["merchant_id", "billing_period"]).groupby(
        ["merchant_id", "billing_period"]
    ).size().reset_index(name="transaction_count")

    inv = invoices.copy()
    inv["billing_period"] = pd.to_datetime(inv["billing_period_start"], errors="coerce").dt.to_period("M")
    invoiced_months = set(zip(inv["merchant_id"], inv["billing_period"]))

    txn_months["has_invoice"] = txn_months.apply(
        lambda r: (r["merchant_id"], r["billing_period"]) in invoiced_months, axis=1
    )
    return txn_months[~txn_months["has_invoice"]].drop(columns="has_invoice")


def duplicate_payments(payments: pd.DataFrame) -> pd.DataFrame:
    """Same invoice billed the same amount by more than one successful payment row."""
    paid = payments[payments["payment_status"] == "Success"]
    dupes = paid[paid.duplicated(subset=["invoice_id", "payment_amount"], keep=False)]
    return dupes[dupes["invoice_id"].notna()].sort_values(["invoice_id", "payment_date"])


def unmatched_payments(payments: pd.DataFrame, invoices: pd.DataFrame) -> pd.DataFrame:
    """Payments referencing an invoice_id that does not exist in invoices."""
    valid_invoice_ids = set(invoices["invoice_id"].dropna())
    return payments[payments["invoice_id"].notna() & ~payments["invoice_id"].isin(valid_invoice_ids)]


def orphan_payments(payments: pd.DataFrame) -> pd.DataFrame:
    """Payments with no invoice_id at all - cash received that cannot be
    applied to any invoice without manual investigation."""
    return payments[payments["invoice_id"].isna()]


def invoices_without_payment(invoices: pd.DataFrame, payments: pd.DataFrame) -> pd.DataFrame:
    """Invoices with no successful payment row at all (open AR balance)."""
    paid_invoice_ids = set(payments.loc[payments["payment_status"] == "Success", "invoice_id"].dropna())
    return invoices[
        (~invoices["invoice_id"].isin(paid_invoice_ids)) & (invoices["invoice_status"] != "Void")
    ]


def amount_mismatches(invoices: pd.DataFrame, payments: pd.DataFrame, tolerance: float = 1.0) -> pd.DataFrame:
    """Invoices where total successful payments materially over/under-shoot the invoice total."""
    paid = payments[payments["payment_status"] == "Success"]
    paid_totals = paid.groupby("invoice_id")["payment_amount"].sum().rename("total_paid")
    merged = invoices.merge(paid_totals, on="invoice_id", how="left")
    merged["total_paid"] = merged["total_paid"].fillna(0.0)
    merged["variance"] = merged["total_paid"] - merged["total_invoice_amount"]
    return merged[merged["variance"].abs() > tolerance]
