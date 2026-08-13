"""Phase 12: builds Power BI-ready star-schema CSV exports from the SQL
database and the already-computed finance engine outputs in data/processed/.

Produces two dimension tables and five fact tables, written to
data/processed/powerbi/ (git-ignored, regenerate via this script):

    dim_merchant.csv           one row per merchant
    dim_date.csv                one row per calendar day across the data window
    fact_invoices.csv           invoice grain: billing status, realization, AR
    fact_payments.csv           payment grain: reconciliation status
    fact_collection_activity.csv collector-activity grain
    fact_revenue_leakage.csv    leakage-event grain
    fact_ar_aging.csv           open-invoice grain: aging bucket, risk category

Load these into Power BI Desktop, relate each fact table to dim_merchant
(via merchant_id) and dim_date (via the relevant date column) rather than
relating fact tables to each other directly - see powerbi/dashboard_spec.md
for the full data model and DAX measures.

Run from the project root:
    python -m src.reporting.prepare_powerbi_datasets
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.utils.db import get_engine

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
POWERBI_DIR = PROCESSED_DIR / "powerbi"


def build_dim_merchant(engine) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT merchant_id, merchant_name, industry, merchant_segment, city, state, "
        "country, onboarding_date, account_manager, pricing_plan, agreed_fee_percent, "
        "monthly_subscription_fee, payment_terms_days, merchant_status FROM merchants",
        engine,
    )


def build_dim_date(start: str, end: str) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    dim = pd.DataFrame({"date": dates})
    dim["date_key"] = dim["date"].dt.strftime("%Y%m%d").astype(int)
    dim["year"] = dim["date"].dt.year
    dim["month"] = dim["date"].dt.month
    dim["month_name"] = dim["date"].dt.strftime("%b")
    dim["year_month"] = dim["date"].dt.strftime("%Y-%m")
    dim["quarter"] = "Q" + dim["date"].dt.quarter.astype(str)
    dim["day_of_week"] = dim["date"].dt.strftime("%A")
    dim["is_month_end"] = dim["date"].dt.is_month_end
    return dim


def build_fact_invoices(engine) -> pd.DataFrame:
    invoices = pd.read_sql(
        "SELECT invoice_id, merchant_id, billing_period_start, invoice_date, due_date, "
        "total_invoice_amount, expected_fee, billed_fee, invoice_status, payment_status "
        "FROM invoices",
        engine,
    )
    invoices["revenue_difference"] = (invoices["billed_fee"] - invoices["expected_fee"]).round(2)
    billing = pd.read_csv(PROCESSED_DIR / "billing_analysis.csv")[["invoice_id", "billing_status"]]
    return invoices.merge(billing, on="invoice_id", how="left")


def build_fact_payments(engine) -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / "reconciliation_payments.csv")


def build_fact_collection_activity(engine) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT collection_id, merchant_id, invoice_id, activity_date, activity_type, "
        "contact_channel, collector, outcome, promised_payment_date, promised_amount "
        "FROM collection_activity",
        engine,
    )


def build_fact_revenue_leakage() -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / "revenue_leakage.csv")


def build_fact_ar_aging() -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / "ar_aging.csv")


def main() -> None:
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)
    engine = get_engine()

    dim_merchant = build_dim_merchant(engine)
    dim_date = build_dim_date("2024-08-01", "2026-12-31")
    fact_invoices = build_fact_invoices(engine)
    fact_payments = build_fact_payments(engine)
    fact_collection_activity = build_fact_collection_activity(engine)
    fact_revenue_leakage = build_fact_revenue_leakage()
    fact_ar_aging = build_fact_ar_aging()

    outputs = {
        "dim_merchant.csv": dim_merchant,
        "dim_date.csv": dim_date,
        "fact_invoices.csv": fact_invoices,
        "fact_payments.csv": fact_payments,
        "fact_collection_activity.csv": fact_collection_activity,
        "fact_revenue_leakage.csv": fact_revenue_leakage,
        "fact_ar_aging.csv": fact_ar_aging,
    }
    for filename, df in outputs.items():
        df.to_csv(POWERBI_DIR / filename, index=False)
        print(f"{filename}: {len(df):,} rows, {len(df.columns)} columns")


if __name__ == "__main__":
    main()
