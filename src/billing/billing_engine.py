"""Billing validation engine: for every merchant/billing-month, compares
expected revenue (correct contract rate x GMV) against actual billed revenue
and classifies the result.

billing_status classification (in priority order):
  - Missing Invoice: the merchant transacted that month but no invoice exists
  - Pricing Mismatch: the invoice is wrong AND a contract rate change took
    effect at or just before this billing month - the likely cause is the
    invoice having been cut on a stale rate, not a one-off calculation error
  - Underbilled / Overbilled: the invoice is wrong for any other reason
  - Correct: billed_fee matches expected_fee

"Pricing Mismatch" is deliberately scoped to invoices near a real contract
transition (from the contracts table) rather than reverse-engineered from the
billed/expected ratio - the three error mechanisms used to generate this data
(underbill, overbill, stale-rate) produce overlapping billed/expected ratios,
so ratio alone cannot reliably tell them apart. Anchoring "pricing mismatch"
to an actual contract change is the honest, defensible signal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import text

CONTRACT_TRANSITION_WINDOW_DAYS = 45
CORRECT_TOLERANCE = 0.01


def load_invoices(engine) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM invoices", engine)
    for col in ["billing_period_start", "invoice_date", "due_date"]:
        df[col] = pd.to_datetime(df[col])
    return df


def load_contracts(engine) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM contracts", engine)
    df["effective_from"] = pd.to_datetime(df["effective_from"])
    return df


def load_missing_invoice_months(engine) -> pd.DataFrame:
    """Merchant-months with successful transactions but no invoice row,
    computed directly from the SQL database (mirrors Phase 4's cross-table
    check, kept independent so the billing engine doesn't depend on the
    validation module's internals)."""
    txns = pd.read_sql(
        "SELECT merchant_id, transaction_date, transaction_amount, expected_platform_fee "
        "FROM transactions WHERE payment_status = 'Success'",
        engine,
    )
    txns["transaction_date"] = pd.to_datetime(txns["transaction_date"])
    txns["billing_period_start"] = txns["transaction_date"].values.astype("datetime64[M]")
    monthly_gmv = txns.groupby(["merchant_id", "billing_period_start"]).agg(
        gross_transaction_value=("transaction_amount", "sum"),
        expected_revenue=("expected_platform_fee", "sum"),
    ).reset_index()

    invoices = pd.read_sql("SELECT merchant_id, billing_period_start FROM invoices", engine)
    invoices["billing_period_start"] = pd.to_datetime(invoices["billing_period_start"])
    invoiced = set(zip(invoices["merchant_id"], invoices["billing_period_start"]))

    monthly_gmv["has_invoice"] = [
        (m, p) in invoiced for m, p in zip(monthly_gmv["merchant_id"], monthly_gmv["billing_period_start"])
    ]
    return monthly_gmv[~monthly_gmv["has_invoice"]].drop(columns="has_invoice")


def _near_contract_transition(invoices: pd.DataFrame, contracts: pd.DataFrame) -> pd.Series:
    """True where a contract effective_from date for that merchant falls
    within CONTRACT_TRANSITION_WINDOW_DAYS before the invoice's billing
    period start (i.e. a pricing change had just taken effect or was about
    to)."""
    transitions = contracts[["merchant_id", "effective_from"]].sort_values("effective_from")
    inv_sorted = invoices.sort_values("billing_period_start")

    merged = pd.merge_asof(
        inv_sorted,
        transitions.rename(columns={"effective_from": "nearest_transition"}),
        left_on="billing_period_start",
        right_on="nearest_transition",
        by="merchant_id",
        direction="backward",
    )
    merged.index = inv_sorted.index
    days_since_transition = (merged["billing_period_start"] - merged["nearest_transition"]).dt.days
    is_near = (days_since_transition >= 0) & (days_since_transition <= CONTRACT_TRANSITION_WINDOW_DAYS)
    # merge_asof requires sorting invoices by date; restore original row order
    # before returning so the boolean mask aligns with the caller's DataFrame.
    return is_near.fillna(False).reindex(invoices.index).values


def classify_billing_status(invoices: pd.DataFrame, contracts: pd.DataFrame) -> pd.DataFrame:
    df = invoices.copy()
    df["revenue_difference"] = (df["billed_fee"] - df["expected_fee"]).round(2)
    df["variance_percent"] = (100 * df["revenue_difference"] / df["expected_fee"].replace(0, np.nan)).round(2)

    # Classification is driven by the actual billed-vs-expected variance, not
    # the invoice_error_flag column: a handful of invoices were recovered
    # during Phase 4 cleaning (billed_fee set equal to expected_fee) while
    # invoice_error_flag was left True as a historical marker, so trusting
    # the flag would mislabel an already-correct invoice as an error.
    is_error = df["revenue_difference"].abs() > CORRECT_TOLERANCE
    near_transition = _near_contract_transition(df, contracts)

    status = np.select(
        [
            ~is_error,
            is_error & near_transition,
            is_error & (df["revenue_difference"] < 0),
            is_error & (df["revenue_difference"] > 0),
        ],
        ["Correct", "Pricing Mismatch", "Underbilled", "Overbilled"],
        default="Correct",
    )
    df["billing_status"] = status
    return df


def build_merchant_month_billing(engine) -> pd.DataFrame:
    invoices = load_invoices(engine)
    contracts = load_contracts(engine)

    classified = classify_billing_status(invoices, contracts)
    classified["billing_period"] = classified["billing_period_start"].dt.strftime("%Y-%m")

    result = classified[[
        "merchant_id", "billing_period", "invoice_id", "expected_fee", "billed_fee",
        "revenue_difference", "variance_percent", "billing_status",
    ]].rename(columns={"expected_fee": "expected_revenue", "billed_fee": "actual_billed_revenue"})

    missing = load_missing_invoice_months(engine)
    if len(missing):
        missing_rows = pd.DataFrame({
            "merchant_id": missing["merchant_id"],
            "billing_period": pd.to_datetime(missing["billing_period_start"]).dt.strftime("%Y-%m"),
            "invoice_id": None,
            "expected_revenue": missing["expected_revenue"].round(2),
            "actual_billed_revenue": 0.0,
            "revenue_difference": (0.0 - missing["expected_revenue"]).round(2),
            "variance_percent": -100.0,
            "billing_status": "Missing Invoice",
        })
        result = pd.concat([result, missing_rows], ignore_index=True)

    return result.sort_values(["merchant_id", "billing_period"]).reset_index(drop=True)
