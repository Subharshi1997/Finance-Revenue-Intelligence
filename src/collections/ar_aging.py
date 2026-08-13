"""AR aging engine (Step 7): outstanding balance per invoice, days overdue,
aging bucket, and a risk category combining balance size with how overdue it is.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

AGING_BUCKETS = [
    (-np.inf, 0, "Current"),
    (0, 30, "1-30 days"),
    (30, 60, "31-60 days"),
    (60, 90, "61-90 days"),
    (90, np.inf, "90+ days"),
]


def _bucket(days_overdue: pd.Series) -> pd.Series:
    conditions = [(days_overdue > lo) & (days_overdue <= hi) if lo != -np.inf else days_overdue <= hi
                  for lo, hi, _ in AGING_BUCKETS]
    # first bucket ("Current") should catch days_overdue <= 0
    conditions[0] = days_overdue <= 0
    labels = [b[2] for b in AGING_BUCKETS]
    return pd.Series(np.select(conditions, labels, default="90+ days"), index=days_overdue.index)


def _risk_category(outstanding: pd.Series, days_overdue: pd.Series) -> pd.Series:
    """Combines balance size and days overdue into a single risk read - a
    small overdue balance and a large fresh one shouldn't sit in the same
    tier."""
    amount_score = pd.cut(outstanding, bins=[-np.inf, 500, 2000, 8000, np.inf], labels=[0, 1, 2, 3]).astype(int)
    age_score = pd.cut(days_overdue, bins=[-np.inf, 0, 30, 60, np.inf], labels=[0, 1, 2, 3]).astype(int)
    combined = amount_score + age_score
    return pd.cut(combined, bins=[-1, 1, 3, 5, 10], labels=["Low", "Medium", "High", "Critical"]).astype(str)


def build_ar_aging(engine, as_of_date: str = "2026-08-13") -> pd.DataFrame:
    invoices = pd.read_sql(
        "SELECT invoice_id, merchant_id, invoice_date, due_date, total_invoice_amount, invoice_status "
        "FROM invoices WHERE invoice_status != 'Void'",
        engine,
    )
    payments = pd.read_sql(
        "SELECT invoice_id, SUM(payment_amount) AS total_paid FROM payments "
        "WHERE payment_status = 'Success' GROUP BY invoice_id",
        engine,
    )
    credit_notes = pd.read_sql(
        "SELECT invoice_id, SUM(credit_amount) AS total_credited FROM credit_notes "
        "WHERE status IN ('Issued','Applied') GROUP BY invoice_id",
        engine,
    )
    merchants = pd.read_sql("SELECT merchant_id, merchant_name, merchant_segment FROM merchants", engine)

    df = invoices.merge(payments, on="invoice_id", how="left").merge(credit_notes, on="invoice_id", how="left")
    df["total_paid"] = df["total_paid"].fillna(0.0)
    df["total_credited"] = df["total_credited"].fillna(0.0)
    df["outstanding_amount"] = (df["total_invoice_amount"] - df["total_paid"] - df["total_credited"]).round(2)

    df["invoice_date"] = pd.to_datetime(df["invoice_date"])
    df["due_date"] = pd.to_datetime(df["due_date"])
    df["days_overdue"] = (pd.Timestamp(as_of_date) - df["due_date"]).dt.days

    df = df[df["outstanding_amount"] > 0.01].copy()
    df["aging_bucket"] = _bucket(df["days_overdue"])
    df["risk_category"] = _risk_category(df["outstanding_amount"], df["days_overdue"])

    df = df.merge(merchants, on="merchant_id", how="left")
    return df[[
        "merchant_id", "merchant_name", "merchant_segment", "invoice_id", "invoice_date", "due_date",
        "total_invoice_amount", "total_paid", "total_credited", "outstanding_amount", "days_overdue",
        "aging_bucket", "risk_category",
    ]].sort_values("outstanding_amount", ascending=False).reset_index(drop=True)


def aging_summary(ar_aging: pd.DataFrame) -> pd.DataFrame:
    order = ["Current", "1-30 days", "31-60 days", "61-90 days", "90+ days"]
    summary = ar_aging.groupby("aging_bucket").agg(
        invoice_count=("invoice_id", "count"),
        total_outstanding=("outstanding_amount", "sum"),
    ).reindex(order).reset_index()
    summary["total_outstanding"] = summary["total_outstanding"].round(2)
    summary["percent_of_total_ar"] = (100 * summary["total_outstanding"] / summary["total_outstanding"].sum()).round(2)
    return summary
