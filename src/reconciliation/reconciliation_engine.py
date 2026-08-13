"""Reconciliation engine (Step 12): matches the transaction -> invoice ->
payment -> settlement chain and assigns each invoice and each payment a
reconciliation status.

Invoice-level status (one row per invoice), checked in priority order since
an invoice can technically trip more than one condition at once - the most
operationally urgent one wins:
    MISSING_INVOICE   merchant transacted but no invoice was ever cut
                       (surfaced separately, see reconcile_missing_invoices)
    MISSING_PAYMENT    invoice issued, zero successful payments received
    DUPLICATE          more than one successful payment of the same amount
    AMOUNT_MISMATCH    total paid overshoots the invoice total
    TIMING_MISMATCH    a payment settled before it was made (data/process anomaly)
    PARTIAL            some payment received, total paid < invoice total
    MATCHED            total paid matches invoice total within tolerance

Payment-level status (one row per payment):
    ORPHAN             payment has no invoice_id to apply against
    UNMATCHED          payment references an invoice_id that does not exist
    DUPLICATE          one of two-or-more same-amount payments on an invoice
    MATCHED            applies cleanly to a real invoice
"""
from __future__ import annotations

import pandas as pd

AMOUNT_TOLERANCE = 1.0


def _load_frames(engine) -> dict[str, pd.DataFrame]:
    invoices = pd.read_sql(
        "SELECT invoice_id, merchant_id, invoice_date, total_invoice_amount, invoice_status FROM invoices",
        engine,
    )
    payments = pd.read_sql(
        "SELECT payment_id, invoice_id, merchant_id, payment_date, payment_amount, "
        "payment_status, settlement_date FROM payments",
        engine,
    )
    for col in ["payment_date", "settlement_date"]:
        payments[col] = pd.to_datetime(payments[col])
    invoices["invoice_date"] = pd.to_datetime(invoices["invoice_date"])
    return {"invoices": invoices, "payments": payments}


def reconcile_payments(engine) -> pd.DataFrame:
    frames = _load_frames(engine)
    payments, invoices = frames["payments"], frames["invoices"]

    successful = payments[payments["payment_status"] == "Success"].copy()
    valid_invoice_ids = set(invoices["invoice_id"])

    successful["is_duplicate"] = successful.duplicated(subset=["invoice_id", "payment_amount"], keep=False) & successful["invoice_id"].notna()
    successful["settled_before_paid"] = successful["settlement_date"] < successful["payment_date"]

    def classify(row):
        if pd.isna(row["invoice_id"]):
            return "ORPHAN"
        if row["invoice_id"] not in valid_invoice_ids:
            return "UNMATCHED"
        if row["is_duplicate"]:
            return "DUPLICATE"
        if row["settled_before_paid"]:
            return "TIMING_MISMATCH"
        return "MATCHED"

    successful["reconciliation_status"] = successful.apply(classify, axis=1)

    failed = payments[payments["payment_status"] != "Success"].copy()
    failed["reconciliation_status"] = "NOT_APPLICABLE_" + failed["payment_status"].str.upper()

    result = pd.concat([successful, failed], ignore_index=True)
    return result[[
        "payment_id", "invoice_id", "merchant_id", "payment_date", "payment_amount",
        "payment_status", "reconciliation_status",
    ]]


def reconcile_invoices(engine) -> pd.DataFrame:
    frames = _load_frames(engine)
    invoices, payments = frames["invoices"], frames["payments"]

    successful = payments[payments["payment_status"] == "Success"].copy()
    successful["is_duplicate"] = successful.duplicated(subset=["invoice_id", "payment_amount"], keep=False)
    successful["settled_before_paid"] = successful["settlement_date"] < successful["payment_date"]

    agg = successful.groupby("invoice_id").agg(
        total_paid=("payment_amount", "sum"),
        payment_count=("payment_id", "count"),
        has_duplicate=("is_duplicate", "any"),
        has_timing_mismatch=("settled_before_paid", "any"),
    )

    df = invoices.merge(agg, on="invoice_id", how="left")
    df["total_paid"] = df["total_paid"].fillna(0.0)
    df["payment_count"] = df["payment_count"].fillna(0).astype(int)
    df["has_duplicate"] = df["has_duplicate"].fillna(False)
    df["has_timing_mismatch"] = df["has_timing_mismatch"].fillna(False)
    df["variance"] = (df["total_paid"] - df["total_invoice_amount"]).round(2)

    def classify(row):
        if row["invoice_status"] == "Void":
            return "VOID"
        if row["payment_count"] == 0:
            return "MISSING_PAYMENT"
        if row["has_duplicate"]:
            return "DUPLICATE"
        if row["variance"] > AMOUNT_TOLERANCE:
            return "AMOUNT_MISMATCH"
        if row["has_timing_mismatch"]:
            return "TIMING_MISMATCH"
        if row["variance"] < -AMOUNT_TOLERANCE:
            return "PARTIAL"
        return "MATCHED"

    df["reconciliation_status"] = df.apply(classify, axis=1)
    return df[[
        "invoice_id", "merchant_id", "total_invoice_amount", "total_paid", "payment_count",
        "variance", "reconciliation_status",
    ]]


def reconcile_missing_invoices(engine) -> pd.DataFrame:
    """Merchant-months with successful transactions but no invoice at all -
    these never enter the invoice-level reconciliation above because there
    is no invoice_id to anchor them to."""
    txns = pd.read_sql(
        "SELECT merchant_id, transaction_date, transaction_amount FROM transactions WHERE payment_status = 'Success'",
        engine,
    )
    txns["transaction_date"] = pd.to_datetime(txns["transaction_date"])
    txns["billing_period"] = txns["transaction_date"].dt.strftime("%Y-%m")
    monthly = txns.groupby(["merchant_id", "billing_period"]).agg(
        transaction_count=("transaction_amount", "count"),
        gross_transaction_value=("transaction_amount", "sum"),
    ).reset_index()

    invoices = pd.read_sql("SELECT merchant_id, billing_period_start FROM invoices", engine)
    invoices["billing_period"] = pd.to_datetime(invoices["billing_period_start"]).dt.strftime("%Y-%m")
    invoiced = set(zip(invoices["merchant_id"], invoices["billing_period"]))

    monthly["has_invoice"] = [
        (m, p) in invoiced for m, p in zip(monthly["merchant_id"], monthly["billing_period"])
    ]
    missing = monthly[~monthly["has_invoice"]].drop(columns="has_invoice").copy()
    missing["reconciliation_status"] = "MISSING_INVOICE"
    return missing


def reconciliation_summary(invoice_recon: pd.DataFrame, missing_invoices: pd.DataFrame) -> pd.DataFrame:
    counts = invoice_recon["reconciliation_status"].value_counts()
    counts["MISSING_INVOICE"] = len(missing_invoices)
    total = counts.sum()
    matched = counts.get("MATCHED", 0)

    summary = counts.rename_axis("reconciliation_status").reset_index(name="count")
    summary["percent_of_total"] = (100 * summary["count"] / total).round(2)
    summary.attrs["reconciliation_rate_percent"] = round(100 * matched / total, 2)
    return summary.sort_values("count", ascending=False).reset_index(drop=True)
