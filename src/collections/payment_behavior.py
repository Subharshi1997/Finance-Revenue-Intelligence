"""Customer payment behavior analysis (Step 11).

For every merchant, characterizes how they actually pay relative to invoice
due dates, then segments them into payer archetypes Finance can act on:

    Excellent  - average delay <= 0 days (pays on or before due date)
    Good       - average delay 0-15 days late
    Moderate   - average delay 15-30 days late
    High-risk  - average delay > 30 days late, or fewer than half of
                 invoices paid on time

Payment delay = last payment date on the invoice - invoice due date.
A negative delay means the merchant paid early.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _payer_segment(avg_delay: float, on_time_pct: float) -> str:
    if pd.isna(avg_delay):
        return "Insufficient Data"
    if avg_delay <= 0:
        return "Excellent"
    if avg_delay <= 15 and on_time_pct >= 50:
        return "Good"
    if avg_delay <= 30:
        return "Moderate"
    return "High-risk"


def payment_behavior_by_merchant(engine, as_of_date: str = "2026-08-13") -> pd.DataFrame:
    invoices = pd.read_sql(
        "SELECT invoice_id, merchant_id, due_date, total_invoice_amount, invoice_status, payment_status "
        "FROM invoices WHERE invoice_status != 'Void'",
        engine,
    )
    payments = pd.read_sql(
        "SELECT invoice_id, payment_date, payment_amount FROM payments WHERE payment_status = 'Success'",
        engine,
    )
    credit_notes = pd.read_sql(
        "SELECT invoice_id, SUM(credit_amount) AS total_credited FROM credit_notes "
        "WHERE status IN ('Issued','Applied') GROUP BY invoice_id",
        engine,
    )
    merchants = pd.read_sql("SELECT merchant_id, merchant_name, merchant_segment FROM merchants", engine)

    invoices["due_date"] = pd.to_datetime(invoices["due_date"])
    paid_totals = payments.groupby("invoice_id")["payment_amount"].sum().rename("total_paid")
    last_payment = payments.groupby("invoice_id")["payment_date"].max().rename("last_payment_date")

    df = invoices.merge(paid_totals, on="invoice_id", how="left") \
        .merge(last_payment, on="invoice_id", how="left") \
        .merge(credit_notes, on="invoice_id", how="left")
    df["total_paid"] = df["total_paid"].fillna(0.0)
    df["total_credited"] = df["total_credited"].fillna(0.0)
    df["outstanding"] = (df["total_invoice_amount"] - df["total_paid"] - df["total_credited"]).clip(lower=0)

    paid = df[df["payment_status"] == "Paid"].copy()
    paid["last_payment_date"] = pd.to_datetime(paid["last_payment_date"])
    paid["payment_delay_days"] = (paid["last_payment_date"] - paid["due_date"]).dt.days
    paid["on_time"] = paid["payment_delay_days"] <= 0

    delay_stats = paid.groupby("merchant_id").agg(
        avg_payment_delay_days=("payment_delay_days", "mean"),
        median_payment_delay_days=("payment_delay_days", "median"),
        max_payment_delay_days=("payment_delay_days", "max"),
        paid_invoice_count=("invoice_id", "count"),
        on_time_count=("on_time", "sum"),
    ).reset_index()
    delay_stats["on_time_percent"] = (100 * delay_stats["on_time_count"] / delay_stats["paid_invoice_count"]).round(2)
    delay_stats["late_percent"] = (100 - delay_stats["on_time_percent"]).round(2)

    overdue_counts = df[
        (df["payment_status"] != "Paid") & (df["due_date"] < pd.Timestamp(as_of_date))
    ].groupby("merchant_id").size().rename("overdue_invoice_count")

    overview = df.groupby("merchant_id").agg(
        total_invoice_count=("invoice_id", "count"),
        avg_invoice_value=("total_invoice_amount", "mean"),
        outstanding_balance=("outstanding", "sum"),
    ).reset_index()

    result = overview.merge(delay_stats, on="merchant_id", how="left") \
        .merge(overdue_counts, on="merchant_id", how="left") \
        .merge(merchants, on="merchant_id", how="left")
    result["overdue_invoice_count"] = result["overdue_invoice_count"].fillna(0).astype(int)
    result["collection_success_rate_percent"] = (
        100 * (result["total_invoice_count"] - result["overdue_invoice_count"]) / result["total_invoice_count"]
    ).round(2)

    result["payer_segment"] = [
        _payer_segment(row.avg_payment_delay_days, row.on_time_percent) for row in result.itertuples()
    ]

    result["avg_invoice_value"] = result["avg_invoice_value"].round(2)
    result["outstanding_balance"] = result["outstanding_balance"].round(2)
    for col in ["avg_payment_delay_days", "median_payment_delay_days"]:
        result[col] = result[col].round(1)

    cols = [
        "merchant_id", "merchant_name", "merchant_segment", "total_invoice_count", "avg_invoice_value",
        "outstanding_balance", "avg_payment_delay_days", "median_payment_delay_days", "max_payment_delay_days",
        "on_time_percent", "late_percent", "overdue_invoice_count", "collection_success_rate_percent",
        "payer_segment",
    ]
    return result[cols].sort_values("avg_payment_delay_days", ascending=False, na_position="last").reset_index(drop=True)


def payer_segment_summary(behavior: pd.DataFrame) -> pd.DataFrame:
    order = ["Excellent", "Good", "Moderate", "High-risk", "Insufficient Data"]
    summary = behavior.groupby("payer_segment").agg(
        merchant_count=("merchant_id", "count"),
        total_outstanding=("outstanding_balance", "sum"),
        avg_delay_days=("avg_payment_delay_days", "mean"),
    ).reindex(order).dropna(how="all").reset_index()
    summary["total_outstanding"] = summary["total_outstanding"].round(2)
    summary["avg_delay_days"] = summary["avg_delay_days"].round(1)
    return summary
