"""Generates the monthly invoices table: one invoice per active merchant per active month,
aggregating expected platform fees and deliberately mis-billing ~8-10% of them (the core
billing-error signal) plus dropping invoices for a small share of merchant-months entirely."""
import numpy as np
import pandas as pd

from src.utils import config as cfg

BILLING_ERROR_SHARE = 0.09
MISSING_INVOICE_SHARE = 0.018
VOID_SHARE = 0.01


def _aggregate_merchant_months(transactions: pd.DataFrame) -> pd.DataFrame:
    txns = transactions.dropna(subset=["merchant_id"]).copy()
    txns["billing_month"] = pd.to_datetime(txns["transaction_date"].values.astype("datetime64[M]")).astype("datetime64[ns]")
    grouped = txns.groupby(["merchant_id", "billing_month"]).agg(
        expected_fee=("expected_platform_fee", "sum"),
        txn_count=("transaction_id", "count"),
    ).reset_index()
    return grouped


def generate_invoices(merchants: pd.DataFrame, contracts: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    rng = cfg.new_rng(offset=5)
    merchant_lookup = merchants.set_index("merchant_id")
    contracts_sorted = contracts.sort_values(["effective_from"])

    merchant_months = _aggregate_merchant_months(transactions)
    merchant_months = merchant_months[merchant_months["merchant_id"].isin(merchant_lookup.index)]

    drop_mask = rng.random(len(merchant_months)) < MISSING_INVOICE_SHARE
    merchant_months = merchant_months[~drop_mask].reset_index(drop=True)

    n = len(merchant_months)
    billing_period_start = merchant_months["billing_month"]
    billing_period_end = pd.to_datetime(billing_period_start) + pd.offsets.MonthEnd(0)
    invoice_date = billing_period_end + pd.Timedelta(days=2)

    payment_terms = merchant_months["merchant_id"].map(merchant_lookup["payment_terms_days"])
    due_date = invoice_date + pd.to_timedelta(payment_terms.values, unit="D")

    merged_contract = pd.merge_asof(
        merchant_months.sort_values("billing_month"),
        contracts_sorted[["merchant_id", "effective_from", "transaction_fee_percent", "discount_percent"]],
        left_on="billing_month",
        right_on="effective_from",
        by="merchant_id",
        direction="backward",
    ).sort_index()

    expected_fee = merchant_months["expected_fee"].round(2)

    billed_fee = expected_fee.copy()
    error_mask = rng.random(n) < BILLING_ERROR_SHARE
    error_type = rng.choice(["underbill", "overbill", "stale_rate"], size=error_mask.sum(), p=[0.4, 0.35, 0.25])

    err_positions = np.where(error_mask)[0]
    under_positions = err_positions[error_type == "underbill"]
    over_positions = err_positions[error_type == "overbill"]
    stale_positions = err_positions[error_type == "stale_rate"]

    billed_fee.iloc[under_positions] = (expected_fee.iloc[under_positions] * rng.uniform(0.65, 0.92, size=len(under_positions))).round(2)
    billed_fee.iloc[over_positions] = (expected_fee.iloc[over_positions] * rng.uniform(1.08, 1.35, size=len(over_positions))).round(2)

    stale_rate = merged_contract["transaction_fee_percent"].iloc[stale_positions].values * rng.uniform(0.7, 0.9, size=len(stale_positions))
    approx_gmv = expected_fee.iloc[stale_positions].values / (merged_contract["transaction_fee_percent"].iloc[stale_positions].values / 100)
    billed_fee.iloc[stale_positions] = (approx_gmv * stale_rate / 100).round(2)

    discount_percent = merged_contract["discount_percent"].fillna(0).values
    discount = (billed_fee.values * discount_percent / 100).round(2)
    subtotal = billed_fee.values
    taxable_amount = (subtotal - discount).round(2)
    tax_amount = (taxable_amount * cfg.GST_RATE).round(2)
    total_invoice_amount = (taxable_amount + tax_amount).round(2)

    invoice_error_flag = (billed_fee.round(2) != expected_fee.round(2)).values

    days_since_invoice = (cfg.END_DATE + pd.Timedelta(days=13) - invoice_date).dt.days
    is_void = rng.random(n) < VOID_SHARE
    invoice_status = np.where(is_void, "Void", np.where(days_since_invoice < 3, "Draft", "Issued"))

    df = pd.DataFrame({
        "invoice_id": [f"INV{str(i).zfill(7)}" for i in range(1, n + 1)],
        "merchant_id": merchant_months["merchant_id"].values,
        "billing_period_start": billing_period_start.values,
        "billing_period_end": billing_period_end.values,
        "invoice_date": invoice_date.values,
        "due_date": due_date,
        "subtotal": subtotal,
        "discount": discount,
        "taxable_amount": taxable_amount,
        "tax_rate": cfg.GST_RATE,
        "tax_amount": tax_amount,
        "total_invoice_amount": total_invoice_amount,
        "currency": cfg.CURRENCY,
        "invoice_status": invoice_status,
        "payment_status": "Unpaid",
        "expected_fee": expected_fee.values,
        "billed_fee": billed_fee.values,
        "invoice_error_flag": invoice_error_flag,
    })

    return df
