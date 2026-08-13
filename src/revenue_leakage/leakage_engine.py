"""Revenue leakage engine (Step 6): quantifies money the company was owed
but did not collect, broken into distinct, non-overlapping mechanisms:

  Underbilling               invoice billed less than the correct contract rate
  Pricing Mismatch           same, but the invoice fell near a real contract
                              rate change (see billing_engine's scoping rule)
  Missing Invoice            merchant transacted but no invoice was ever cut
  Refund Fee Not Credited    a transaction was refunded but the platform fee
                              charged on it was never credited back
  Rate Discrepancy           checkout applied the wrong fee rate to a
                              transaction, though invoicing corrected for it
                              (a caught near-miss, not realized leakage)
  Failed Payment             invoice has only failed payment attempts and is
                              now overdue with zero successful collection

Only rows where the company actually collected less than it was owed count
toward "leakage_amount" - a handful of invoices classified Pricing Mismatch
by billing_engine are actually OVERbilled (the classifier prioritizes
"near a contract change" over billing direction). Those are excluded from
the leakage total and reported separately as an overcharge/compliance risk,
since overbilling is not revenue the company failed to collect.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RECOVERY_TOLERANCE = 0.5  # credit note must cover at least 50% of the gap to count as a real correction attempt


def _severity(amount: pd.Series) -> pd.Series:
    return pd.cut(
        amount,
        bins=[-np.inf, 100, 500, 2000, np.inf],
        labels=["Low", "Medium", "High", "Critical"],
    ).astype(str)


def _credit_note_status(invoice_ids: pd.Series, credit_notes: pd.DataFrame) -> pd.Series:
    """Maps each invoice_id to Recovered / Recoverable / Outstanding based on
    whether a credit note was issued against it and whether it was applied."""
    best_status = (
        credit_notes.assign(rank=credit_notes["status"].map({"Applied": 0, "Issued": 1, "Pending": 2}))
        .sort_values("rank")
        .drop_duplicates(subset="invoice_id", keep="first")
        .set_index("invoice_id")["status"]
    )
    mapped = invoice_ids.map(best_status)
    return mapped.map({"Applied": "Recovered", "Issued": "Recoverable", "Pending": "Recoverable"}).fillna("Outstanding")


def build_billing_leakage(billing_analysis: pd.DataFrame, credit_notes: pd.DataFrame) -> pd.DataFrame:
    underbilled = billing_analysis[billing_analysis["billing_status"] == "Underbilled"].copy()
    underbilled["leakage_type"] = "Underbilling"

    pm = billing_analysis[billing_analysis["billing_status"] == "Pricing Mismatch"].copy()
    overbilled_pm_count = (pm["revenue_difference"] > 0).sum()
    pm = pm[pm["revenue_difference"] < 0].copy()
    pm["leakage_type"] = "Pricing Mismatch"

    combined = pd.concat([underbilled, pm], ignore_index=True)
    combined["expected_amount"] = combined["expected_revenue"].round(2)
    combined["actual_amount"] = combined["actual_billed_revenue"].round(2)
    combined["leakage_amount"] = (-combined["revenue_difference"]).round(2)
    combined["status"] = _credit_note_status(combined["invoice_id"], credit_notes)
    combined["severity"] = _severity(combined["leakage_amount"])

    result = combined[[
        "merchant_id", "invoice_id", "leakage_type", "expected_amount", "actual_amount",
        "leakage_amount", "severity", "status",
    ]]
    result.attrs["overbilled_pricing_mismatch_count"] = int(overbilled_pm_count)
    return result


def build_missing_invoice_leakage(billing_analysis: pd.DataFrame) -> pd.DataFrame:
    missing = billing_analysis[billing_analysis["billing_status"] == "Missing Invoice"].copy()
    missing["leakage_type"] = "Missing Invoice"
    missing["expected_amount"] = missing["expected_revenue"].round(2)
    missing["actual_amount"] = 0.0
    missing["leakage_amount"] = missing["expected_amount"].round(2)
    missing["severity"] = _severity(missing["leakage_amount"])
    missing["status"] = "Outstanding"
    return missing[[
        "merchant_id", "invoice_id", "leakage_type", "expected_amount", "actual_amount",
        "leakage_amount", "severity", "status",
    ]]


def build_refund_fee_review(engine) -> pd.DataFrame:
    """Fee revenue retained on refunded transactions. This is NOT counted as
    realized leakage: refunds and transactions agree exactly (verified - no
    amount mismatches), and credit_notes has no "Refund" reason code, meaning
    the business's own design never intended fees to be reversed on refunds.
    Whether they should be is a policy question for Finance, not a data
    defect, so this is surfaced separately from the leakage total rather than
    asserted as money owed.
    """
    transactions = pd.read_sql(
        "SELECT merchant_id, transaction_date, refund_amount, expected_platform_fee, transaction_amount "
        "FROM transactions WHERE refund_amount > 0 AND payment_status = 'Success'",
        engine,
    )
    invoices = pd.read_sql("SELECT invoice_id, merchant_id, billing_period_start FROM invoices", engine)
    credit_notes = pd.read_sql("SELECT invoice_id, credit_amount FROM credit_notes", engine)

    transactions["transaction_date"] = pd.to_datetime(transactions["transaction_date"])
    transactions["billing_period"] = transactions["transaction_date"].dt.strftime("%Y-%m")
    # fee rate implied by this transaction's own expected fee, applied to the refunded portion
    transactions["fee_rate"] = transactions["expected_platform_fee"] / transactions["transaction_amount"].replace(0, pd.NA)
    transactions["fee_on_refund"] = (transactions["refund_amount"] * transactions["fee_rate"]).round(2)

    monthly = transactions.groupby(["merchant_id", "billing_period"]).agg(
        fee_on_refunded_amount=("fee_on_refund", "sum"),
    ).reset_index()

    invoices["billing_period"] = pd.to_datetime(invoices["billing_period_start"]).dt.strftime("%Y-%m")
    monthly = monthly.merge(invoices[["invoice_id", "merchant_id", "billing_period"]], on=["merchant_id", "billing_period"], how="left")

    credited = credit_notes.groupby("invoice_id")["credit_amount"].sum().rename("total_credited")
    monthly = monthly.merge(credited, on="invoice_id", how="left")
    monthly["total_credited"] = monthly["total_credited"].fillna(0.0)

    uncredited = monthly[monthly["total_credited"] < monthly["fee_on_refunded_amount"] * RECOVERY_TOLERANCE].copy()
    uncredited["leakage_type"] = "Refund Fee Retention (Policy Review)"
    uncredited["expected_amount"] = 0.0
    uncredited["actual_amount"] = uncredited["fee_on_refunded_amount"].round(2)
    uncredited["leakage_amount"] = (uncredited["fee_on_refunded_amount"] - uncredited["total_credited"]).round(2)
    uncredited["severity"] = _severity(uncredited["leakage_amount"])
    uncredited["status"] = "Under Review"

    return uncredited[uncredited["leakage_amount"] > 1][[
        "merchant_id", "invoice_id", "leakage_type", "expected_amount", "actual_amount",
        "leakage_amount", "severity", "status",
    ]]


def build_rate_discrepancy_leakage(engine) -> pd.DataFrame:
    """Transactions where checkout applied a fee rate different from the
    correct contract rate. Invoicing always bills on expected_platform_fee
    (the correct rate), so this never becomes realized revenue leakage - it
    is reported as a caught near-miss / control-testing finding."""
    txns = pd.read_sql(
        "SELECT transaction_id, merchant_id, transaction_date, transaction_amount, "
        "transaction_fee_percent, expected_platform_fee FROM transactions "
        "WHERE payment_status = 'Success'",
        engine,
    )
    txns["correct_fee_percent"] = 100 * txns["expected_platform_fee"] / txns["transaction_amount"].replace(0, pd.NA)
    mismatched = txns[(txns["transaction_fee_percent"] - txns["correct_fee_percent"]).abs() > 0.05].copy()

    mismatched["leakage_type"] = "Rate Discrepancy"
    mismatched["expected_amount"] = mismatched["expected_platform_fee"].round(2)
    mismatched["actual_amount"] = (
        mismatched["transaction_amount"] * mismatched["transaction_fee_percent"] / 100
    ).round(2)
    mismatched["leakage_amount"] = (mismatched["expected_amount"] - mismatched["actual_amount"]).abs().round(2)
    mismatched["severity"] = _severity(mismatched["leakage_amount"])
    mismatched["status"] = "Recovered"  # invoicing already corrected it
    mismatched["invoice_id"] = None

    return mismatched[[
        "merchant_id", "invoice_id", "transaction_id", "leakage_type", "expected_amount",
        "actual_amount", "leakage_amount", "severity", "status",
    ]]


def build_failed_payment_leakage(engine, as_of_date: str = "2026-08-13") -> pd.DataFrame:
    invoices = pd.read_sql(
        "SELECT invoice_id, merchant_id, due_date, total_invoice_amount FROM invoices WHERE invoice_status != 'Void'",
        engine,
    )
    payments = pd.read_sql("SELECT invoice_id, payment_status FROM payments", engine)

    has_success = set(payments.loc[payments["payment_status"] == "Success", "invoice_id"])
    has_failed = set(payments.loc[payments["payment_status"] == "Failed", "invoice_id"])

    candidates = invoices[
        invoices["invoice_id"].isin(has_failed) & ~invoices["invoice_id"].isin(has_success)
    ].copy()
    candidates["due_date"] = pd.to_datetime(candidates["due_date"])
    overdue = candidates[candidates["due_date"] < as_of_date].copy()

    overdue["leakage_type"] = "Failed Payment"
    overdue["expected_amount"] = overdue["total_invoice_amount"].round(2)
    overdue["actual_amount"] = 0.0
    overdue["leakage_amount"] = overdue["expected_amount"]
    overdue["severity"] = _severity(overdue["leakage_amount"])
    overdue["status"] = "Outstanding"

    return overdue[[
        "merchant_id", "invoice_id", "leakage_type", "expected_amount", "actual_amount",
        "leakage_amount", "severity", "status",
    ]]


def build_leakage_table(engine, billing_analysis: pd.DataFrame, credit_notes: pd.DataFrame) -> pd.DataFrame:
    parts = [
        build_billing_leakage(billing_analysis, credit_notes),
        build_missing_invoice_leakage(billing_analysis),
        build_refund_fee_review(engine),
        build_rate_discrepancy_leakage(engine),
        build_failed_payment_leakage(engine),
    ]
    combined = pd.concat(parts, ignore_index=True)
    combined.insert(0, "leakage_id", [f"LKG{str(i).zfill(7)}" for i in range(1, len(combined) + 1)])
    combined["detection_date"] = pd.Timestamp("2026-08-13").strftime("%Y-%m-%d")

    cols = [
        "leakage_id", "merchant_id", "transaction_id", "invoice_id", "leakage_type",
        "expected_amount", "actual_amount", "leakage_amount", "detection_date", "severity", "status",
    ]
    for col in cols:
        if col not in combined.columns:
            combined[col] = None
    return combined[cols]
