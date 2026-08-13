"""Phase 8 entry point: run the revenue leakage engine and write the
consolidated leakage table plus summary breakdowns to data/processed/.

Run from the project root:
    python -m src.revenue_leakage.run_leakage_engine
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.revenue_leakage.leakage_engine import build_billing_leakage, build_leakage_table
from src.utils.db import get_engine

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"


def main() -> None:
    engine = get_engine()
    billing_analysis = pd.read_csv(PROCESSED_DIR / "billing_analysis.csv")
    credit_notes = pd.read_sql("SELECT invoice_id, status FROM credit_notes", engine)

    leakage = build_leakage_table(engine, billing_analysis, credit_notes)
    leakage.to_csv(PROCESSED_DIR / "revenue_leakage.csv", index=False)
    print(f"Revenue leakage table written: {len(leakage):,} rows")

    # Real leakage excludes advisory rows: Rate Discrepancy was caught and
    # corrected before invoicing (never realized), and Refund Fee Retention
    # is a business-policy question, not a confirmed revenue loss.
    ADVISORY_TYPES = ["Rate Discrepancy", "Refund Fee Retention (Policy Review)"]
    realized = leakage[~leakage["leakage_type"].isin(ADVISORY_TYPES)]

    print("\nLeakage by type:")
    by_type = realized.groupby("leakage_type")["leakage_amount"].agg(["count", "sum"]).round(2)
    print(by_type)

    print("\nLeakage by status:")
    by_status = realized.groupby("status")["leakage_amount"].agg(["count", "sum"]).round(2)
    print(by_status)

    print("\nLeakage by severity:")
    by_severity = realized.groupby("severity")["leakage_amount"].agg(["count", "sum"]).round(2)
    print(by_severity)

    total = realized["leakage_amount"].sum()
    recoverable = realized.loc[realized["status"] == "Recoverable", "leakage_amount"].sum()
    recovered = realized.loc[realized["status"] == "Recovered", "leakage_amount"].sum()
    outstanding = realized.loc[realized["status"] == "Outstanding", "leakage_amount"].sum()
    print(f"\nTotal realized leakage: {total:,.2f}")
    print(f"  Recovered:    {recovered:,.2f}")
    print(f"  Recoverable:  {recoverable:,.2f}")
    print(f"  Outstanding:  {outstanding:,.2f}")

    billing_leak = build_billing_leakage(billing_analysis, credit_notes)
    overbilled_near_transition = billing_leak.attrs.get("overbilled_pricing_mismatch_count", 0)
    print(
        f"\nExcluded from leakage total: {overbilled_near_transition} invoices classified Pricing Mismatch "
        f"that were actually OVERbilled (tracked as an overcharge/compliance risk, not company-side leakage)."
    )

    rate_discrepancy = leakage[leakage["leakage_type"] == "Rate Discrepancy"]
    print(
        f"\nCaught near-misses (Rate Discrepancy, corrected before invoicing): "
        f"{len(rate_discrepancy):,} transactions, notional {rate_discrepancy['leakage_amount'].sum():,.2f}"
    )

    refund_review = leakage[leakage["leakage_type"] == "Refund Fee Retention (Policy Review)"]
    print(
        f"\nAdvisory (not counted as leakage): fee revenue retained on refunded transactions "
        f"with no offsetting credit note: {len(refund_review):,} merchant-months, "
        f"{refund_review['leakage_amount'].sum():,.2f} - flag for Finance policy review, not a confirmed loss."
    )


if __name__ == "__main__":
    main()
