"""Phase 7 entry point: run the reconciliation engine and write
invoice-level, payment-level, and missing-invoice results to data/processed/.

Run from the project root:
    python -m src.reconciliation.run_reconciliation
"""
from __future__ import annotations

from pathlib import Path

from src.reconciliation.reconciliation_engine import (
    reconcile_invoices,
    reconcile_missing_invoices,
    reconcile_payments,
    reconciliation_summary,
)
from src.utils.db import get_engine

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"


def main() -> None:
    engine = get_engine()

    invoice_recon = reconcile_invoices(engine)
    payment_recon = reconcile_payments(engine)
    missing_invoices = reconcile_missing_invoices(engine)
    summary = reconciliation_summary(invoice_recon, missing_invoices)

    invoice_recon.to_csv(PROCESSED_DIR / "reconciliation_invoices.csv", index=False)
    payment_recon.to_csv(PROCESSED_DIR / "reconciliation_payments.csv", index=False)
    missing_invoices.to_csv(PROCESSED_DIR / "reconciliation_missing_invoices.csv", index=False)
    summary.to_csv(PROCESSED_DIR / "reconciliation_summary.csv", index=False)

    print(f"Invoice reconciliation: {len(invoice_recon):,} rows")
    print(f"Payment reconciliation: {len(payment_recon):,} rows")
    print(f"Missing-invoice merchant-months: {len(missing_invoices):,} rows")
    print("\nReconciliation status breakdown (invoices + missing invoices):")
    print(summary.to_string(index=False))
    print(f"\nOverall reconciliation rate: {summary.attrs['reconciliation_rate_percent']}%")

    print("\nPayment-level status breakdown:")
    print(payment_recon["reconciliation_status"].value_counts())


if __name__ == "__main__":
    main()
