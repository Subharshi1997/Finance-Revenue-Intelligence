"""Revenue realization engine (Step 5): tracks the funnel from gross
transaction value through to cash actually collected, and the two headline
accuracy ratios finance cares about:

  Realization Rate = Collected Revenue / Billed Revenue x 100
  Billing Accuracy = Correctly Billed Amount / Expected Billing x 100

Collected revenue is attributed to the invoice's ORIGINAL billing period (not
the payment date), so a month's realization rate answers "of what we billed
in month X, how much has been collected so far" - a cohort view, not a cash
view. sql/analytics_queries.sql query 8 answers the complementary cash-view
question (revenue collected during a calendar month, regardless of which
month it was billed for).
"""
from __future__ import annotations

import pandas as pd

CORRECT_TOLERANCE = 0.01


def _load_frames(engine) -> dict[str, pd.DataFrame]:
    transactions = pd.read_sql(
        "SELECT merchant_id, transaction_date, transaction_amount, expected_platform_fee "
        "FROM transactions WHERE payment_status = 'Success'",
        engine,
    )
    invoices = pd.read_sql(
        "SELECT invoice_id, merchant_id, billing_period_start, expected_fee, billed_fee "
        "FROM invoices",
        engine,
    )
    payments = pd.read_sql(
        "SELECT invoice_id, payment_amount FROM payments WHERE payment_status = 'Success'",
        engine,
    )
    credit_notes = pd.read_sql(
        "SELECT invoice_id, credit_amount FROM credit_notes WHERE status IN ('Issued','Applied')",
        engine,
    )

    transactions["transaction_date"] = pd.to_datetime(transactions["transaction_date"])
    transactions["billing_period"] = transactions["transaction_date"].dt.strftime("%Y-%m")
    invoices["billing_period"] = pd.to_datetime(invoices["billing_period_start"]).dt.strftime("%Y-%m")

    return {
        "transactions": transactions,
        "invoices": invoices,
        "payments": payments,
        "credit_notes": credit_notes,
    }


def compute_revenue_realization(engine, group_by: str = "month") -> pd.DataFrame:
    """group_by: 'month' | 'merchant' | 'overall'"""
    frames = _load_frames(engine)
    transactions, invoices, payments, credit_notes = (
        frames["transactions"], frames["invoices"], frames["payments"], frames["credit_notes"],
    )

    key = {"month": "billing_period", "merchant": "merchant_id", "overall": None}[group_by]

    gmv = transactions.groupby(key)["transaction_amount"].sum() if key else pd.Series(
        {"total": transactions["transaction_amount"].sum()}
    )
    txn_expected = transactions.groupby(key)["expected_platform_fee"].sum() if key else pd.Series(
        {"total": transactions["expected_platform_fee"].sum()}
    )

    inv_expected = invoices.groupby(key)["expected_fee"].sum() if key else pd.Series(
        {"total": invoices["expected_fee"].sum()}
    )
    inv_billed = invoices.groupby(key)["billed_fee"].sum() if key else pd.Series(
        {"total": invoices["billed_fee"].sum()}
    )

    correctly_billed = invoices.loc[
        (invoices["billed_fee"] - invoices["expected_fee"]).abs() <= CORRECT_TOLERANCE
    ]
    correctly_billed_amount = (
        correctly_billed.groupby(key)["expected_fee"].sum() if key else pd.Series(
            {"total": correctly_billed["expected_fee"].sum()}
        )
    )

    invoice_period = invoices.set_index("invoice_id")[key] if key else None
    paid = payments.merge(invoices[["invoice_id", key]] if key else invoices[["invoice_id"]], on="invoice_id", how="left")
    collected = paid.groupby(key)["payment_amount"].sum() if key else pd.Series(
        {"total": paid["payment_amount"].sum()}
    )

    credited = credit_notes.merge(invoices[["invoice_id", key]] if key else invoices[["invoice_id"]], on="invoice_id", how="left")
    credited_amount = credited.groupby(key)["credit_amount"].sum() if key else pd.Series(
        {"total": credited["credit_amount"].sum()}
    )

    result = pd.DataFrame({
        "gross_transaction_value": gmv,
        "expected_revenue": txn_expected,
        "billed_revenue": inv_billed,
        "correctly_billed_amount": correctly_billed_amount,
        "collected_revenue": collected,
        "credited_amount": credited_amount,
    }).fillna(0.0)

    result["outstanding_revenue"] = (
        result["billed_revenue"] - result["collected_revenue"] - result["credited_amount"]
    ).round(2)
    result["realization_rate_percent"] = (
        100 * result["collected_revenue"] / result["billed_revenue"].replace(0, pd.NA)
    ).astype(float).round(2)
    result["billing_accuracy_percent"] = (
        100 * result["correctly_billed_amount"] / inv_expected.replace(0, pd.NA)
    ).astype(float).round(2)

    for col in ["gross_transaction_value", "expected_revenue", "billed_revenue", "collected_revenue", "credited_amount"]:
        result[col] = result[col].round(2)

    result = result.drop(columns="correctly_billed_amount").reset_index()
    result = result.rename(columns={"index": key or "total"})
    return result.sort_values(result.columns[0]).reset_index(drop=True)
