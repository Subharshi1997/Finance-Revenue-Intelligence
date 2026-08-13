"""Collection analytics (Step 9): how well Finance is turning billed revenue
into cash, and which collection channels/segments actually work.

Metrics
-------
Collection rate          = Cash collected in the window / Revenue billed in the window x 100
Recovery rate             = Amount collected on invoices that had at least one collection
                              activity / Amount owed on those invoices at first activity x 100
Average collection time   = Mean days between an invoice's due date and the date it was
                              fully paid (paid invoices only)
Promise-to-pay rate       = Share of collection activities whose outcome is "Promise to Pay"
Promise-to-pay fulfillment = Share of promises kept: a Success payment for that invoice
                              landed on or before the promised_payment_date
Channel / segment success = Share of collection activities per contact_channel /
                              merchant_segment whose outcome is "Payment Received"
"""
from __future__ import annotations

import pandas as pd

TRAILING_WINDOW_DAYS = 90


def _invoices(engine) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT invoice_id, merchant_id, invoice_date, due_date, total_invoice_amount, "
        "invoice_status, payment_status FROM invoices WHERE invoice_status != 'Void'",
        engine,
    )


def _payments(engine) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT invoice_id, merchant_id, payment_date, payment_amount, payment_status "
        "FROM payments WHERE payment_status = 'Success'",
        engine,
    )


def collection_rate(engine, as_of_date: str = "2026-08-13", window_days: int = TRAILING_WINDOW_DAYS) -> dict:
    period_start = (pd.Timestamp(as_of_date) - pd.Timedelta(days=window_days)).strftime("%Y-%m-%d")
    billed = pd.read_sql(
        f"SELECT SUM(total_invoice_amount) AS total FROM invoices "
        f"WHERE invoice_status != 'Void' AND invoice_date BETWEEN '{period_start}' AND '{as_of_date}'",
        engine,
    )["total"].iloc[0] or 0.0
    collected = pd.read_sql(
        f"SELECT SUM(payment_amount) AS total FROM payments "
        f"WHERE payment_status = 'Success' AND payment_date BETWEEN '{period_start}' AND '{as_of_date}'",
        engine,
    )["total"].iloc[0] or 0.0
    rate = round(100 * collected / billed, 2) if billed else None
    return {
        "period_start": period_start, "period_end": as_of_date,
        "billed_revenue": round(billed, 2), "collected_revenue": round(collected, 2),
        "collection_rate_percent": rate,
    }


def recovery_rate(engine) -> dict:
    """Of invoices Finance actively chased (they appear in collection_activity),
    how much of the outstanding balance at the time of first contact was eventually
    collected?"""
    activity = pd.read_sql(
        "SELECT invoice_id, MIN(activity_date) AS first_activity_date FROM collection_activity "
        "WHERE invoice_id IS NOT NULL GROUP BY invoice_id",
        engine,
    )
    invoices = _invoices(engine)
    payments = _payments(engine)

    chased = activity.merge(invoices, on="invoice_id", how="inner")
    paid_total = payments.groupby("invoice_id")["payment_amount"].sum().rename("total_paid")
    chased = chased.merge(paid_total, on="invoice_id", how="left")
    chased["total_paid"] = chased["total_paid"].fillna(0.0)

    owed_at_contact = chased["total_invoice_amount"].sum()
    collected = chased["total_paid"].clip(upper=chased["total_invoice_amount"]).sum()
    rate = round(100 * collected / owed_at_contact, 2) if owed_at_contact else None
    return {
        "invoices_chased": len(chased),
        "amount_owed_at_contact": round(owed_at_contact, 2),
        "amount_recovered": round(collected, 2),
        "recovery_rate_percent": rate,
    }


def average_collection_time(engine) -> dict:
    invoices = _invoices(engine)
    invoices = invoices[invoices["payment_status"] == "Paid"].copy()
    payments = _payments(engine)

    last_payment = payments.groupby("invoice_id")["payment_date"].max().rename("last_payment_date")
    df = invoices.merge(last_payment, on="invoice_id", how="inner")
    df["due_date"] = pd.to_datetime(df["due_date"])
    df["last_payment_date"] = pd.to_datetime(df["last_payment_date"])
    df["collection_days"] = (df["last_payment_date"] - df["due_date"]).dt.days

    return {
        "paid_invoices_measured": len(df),
        "avg_collection_days": round(df["collection_days"].mean(), 1) if len(df) else None,
        "median_collection_days": round(df["collection_days"].median(), 1) if len(df) else None,
    }


def promise_to_pay(engine) -> dict:
    activity = pd.read_sql(
        "SELECT invoice_id, merchant_id, activity_type, outcome, promised_payment_date, promised_amount "
        "FROM collection_activity",
        engine,
    )
    total_activities = len(activity)
    promises = activity[activity["outcome"] == "Promise to Pay"].copy()
    ptp_rate = round(100 * len(promises) / total_activities, 2) if total_activities else None

    payments = _payments(engine)
    promises = promises.dropna(subset=["invoice_id", "promised_payment_date"])
    fulfilled = 0
    for _, row in promises.iterrows():
        matches = payments[
            (payments["invoice_id"] == row["invoice_id"])
            & (payments["payment_date"] <= row["promised_payment_date"])
        ]
        if len(matches):
            fulfilled += 1
    fulfillment_rate = round(100 * fulfilled / len(promises), 2) if len(promises) else None

    return {
        "total_collection_activities": total_activities,
        "promises_made": len(promises),
        "promise_to_pay_rate_percent": ptp_rate,
        "promises_fulfilled": fulfilled,
        "promise_fulfillment_rate_percent": fulfillment_rate,
    }


def channel_effectiveness(engine) -> pd.DataFrame:
    activity = pd.read_sql(
        "SELECT contact_channel, outcome FROM collection_activity WHERE contact_channel IS NOT NULL",
        engine,
    )
    summary = activity.groupby("contact_channel").agg(
        total_activities=("outcome", "count"),
        payments_received=("outcome", lambda s: (s == "Payment Received").sum()),
    ).reset_index()
    summary["success_rate_percent"] = (100 * summary["payments_received"] / summary["total_activities"]).round(2)
    return summary.sort_values("success_rate_percent", ascending=False).reset_index(drop=True)


def segment_effectiveness(engine) -> pd.DataFrame:
    activity = pd.read_sql(
        "SELECT ca.outcome, m.merchant_segment FROM collection_activity ca "
        "JOIN merchants m ON m.merchant_id = ca.merchant_id",
        engine,
    )
    summary = activity.groupby("merchant_segment").agg(
        total_activities=("outcome", "count"),
        payments_received=("outcome", lambda s: (s == "Payment Received").sum()),
    ).reset_index()
    summary["success_rate_percent"] = (100 * summary["payments_received"] / summary["total_activities"]).round(2)
    return summary.sort_values("success_rate_percent", ascending=False).reset_index(drop=True)
