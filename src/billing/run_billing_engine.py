"""Phase 6 entry point: run the billing validation engine and write
merchant/month billing status to data/processed/billing_analysis.csv.

Run from the project root:
    python -m src.billing.run_billing_engine
"""
from __future__ import annotations

from pathlib import Path

from src.billing.billing_engine import build_merchant_month_billing
from src.utils.db import get_engine

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "data" / "processed" / "billing_analysis.csv"


def main() -> None:
    engine = get_engine()
    result = build_merchant_month_billing(engine)

    result.to_csv(OUTPUT_PATH, index=False)
    print(f"Billing analysis written to {OUTPUT_PATH} ({len(result):,} merchant-month rows)")

    print("\nBilling status breakdown:")
    print(result["billing_status"].value_counts())

    leakage_rows = result[result["billing_status"].isin(["Underbilled", "Pricing Mismatch", "Missing Invoice"])]
    total_underbill_leakage = -result.loc[
        result["billing_status"].isin(["Underbilled", "Pricing Mismatch"]), "revenue_difference"
    ].sum()
    print(f"\nInvoices flagged as billing errors: {len(leakage_rows):,}")
    print(f"Total underbilling revenue difference (Underbilled + Pricing Mismatch): {total_underbill_leakage:,.2f}")


if __name__ == "__main__":
    main()
