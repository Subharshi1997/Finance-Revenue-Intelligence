"""Days Sales Outstanding (Step 8).

DSO = (Total Accounts Receivable / Total Credit Sales in the period) x Number of Days

Interpretation: DSO estimates how many days, on average, it takes to collect
cash after billing. A DSO of 45 against 30-day payment terms means the
business is effectively financing its merchants for an extra two weeks on
top of agreed terms - cash that could otherwise fund operations. Rising DSO
is an early warning sign for collections effectiveness or credit-risk
underwriting, independent of whether revenue itself is growing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRAILING_WINDOW_DAYS = 90


def _total_ar(engine, as_of_date: str) -> float:
    invoices = pd.read_sql(
        "SELECT invoice_id, total_invoice_amount FROM invoices WHERE invoice_status != 'Void' "
        f"AND invoice_date <= '{as_of_date}'",
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
    merged = invoices.merge(payments, on="invoice_id", how="left").merge(credit_notes, on="invoice_id", how="left")
    merged["total_paid"] = merged["total_paid"].fillna(0.0)
    merged["total_credited"] = merged["total_credited"].fillna(0.0)
    return float((merged["total_invoice_amount"] - merged["total_paid"] - merged["total_credited"]).sum())


def overall_dso(engine, as_of_date: str = "2026-08-13", window_days: int = TRAILING_WINDOW_DAYS) -> dict:
    period_start = (pd.Timestamp(as_of_date) - pd.Timedelta(days=window_days)).strftime("%Y-%m-%d")
    credit_sales = pd.read_sql(
        f"SELECT SUM(billed_fee) AS total FROM invoices WHERE invoice_date BETWEEN '{period_start}' AND '{as_of_date}'",
        engine,
    )["total"].iloc[0] or 0.0

    total_ar = _total_ar(engine, as_of_date)
    dso = round(total_ar / credit_sales * window_days, 1) if credit_sales else None
    return {"total_ar": round(total_ar, 2), "trailing_credit_sales": round(credit_sales, 2), "dso_days": dso}


def monthly_dso(engine, as_of_date: str = "2026-08-13") -> pd.DataFrame:
    invoices = pd.read_sql(
        "SELECT invoice_id, merchant_id, invoice_date, billed_fee, total_invoice_amount FROM invoices "
        "WHERE invoice_status != 'Void'",
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
    invoices["invoice_date"] = pd.to_datetime(invoices["invoice_date"])
    invoices["month"] = invoices["invoice_date"].dt.strftime("%Y-%m")
    invoices = invoices.merge(payments, on="invoice_id", how="left").merge(credit_notes, on="invoice_id", how="left")
    invoices["total_paid"] = invoices["total_paid"].fillna(0.0)
    invoices["total_credited"] = invoices["total_credited"].fillna(0.0)
    invoices["outstanding"] = invoices["total_invoice_amount"] - invoices["total_paid"] - invoices["total_credited"]

    monthly = invoices.groupby("month").agg(
        credit_sales=("billed_fee", "sum"),
        month_end_ar=("outstanding", "sum"),
    ).reset_index()
    days_in_month = pd.to_datetime(monthly["month"]).dt.days_in_month
    monthly["dso_days"] = (monthly["month_end_ar"] / monthly["credit_sales"].replace(0, np.nan) * days_in_month).round(1)
    monthly["credit_sales"] = monthly["credit_sales"].round(2)
    monthly["month_end_ar"] = monthly["month_end_ar"].round(2)
    return monthly


def dso_by(engine, group_col: str, as_of_date: str = "2026-08-13", window_days: int = TRAILING_WINDOW_DAYS) -> pd.DataFrame:
    """group_col: 'merchant_id' or 'merchant_segment'."""
    period_start = (pd.Timestamp(as_of_date) - pd.Timedelta(days=window_days)).strftime("%Y-%m-%d")

    invoices = pd.read_sql(
        "SELECT i.invoice_id, i.merchant_id, i.invoice_date, i.billed_fee, i.total_invoice_amount, "
        "m.merchant_segment FROM invoices i JOIN merchants m ON m.merchant_id = i.merchant_id "
        "WHERE i.invoice_status != 'Void'",
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
    invoices = invoices.merge(payments, on="invoice_id", how="left").merge(credit_notes, on="invoice_id", how="left")
    invoices["total_paid"] = invoices["total_paid"].fillna(0.0)
    invoices["total_credited"] = invoices["total_credited"].fillna(0.0)
    invoices["outstanding"] = invoices["total_invoice_amount"] - invoices["total_paid"] - invoices["total_credited"]

    ar_by_group = invoices.groupby(group_col)["outstanding"].sum()
    sales_by_group = invoices.loc[
        invoices["invoice_date"].between(period_start, as_of_date), :
    ].groupby(group_col)["billed_fee"].sum()

    result = pd.DataFrame({"total_ar": ar_by_group, "trailing_credit_sales": sales_by_group}).fillna(0.0)
    result["dso_days"] = (result["total_ar"] / result["trailing_credit_sales"].replace(0, np.nan) * window_days).round(1)
    result[["total_ar", "trailing_credit_sales"]] = result[["total_ar", "trailing_credit_sales"]].round(2)
    return result.reset_index().sort_values("dso_days", ascending=False)
