"""Phase 6 entry point: run the revenue realization engine at all three
grain levels and write each to data/processed/.

Run from the project root:
    python -m src.finance_metrics.run_revenue_realization
"""
from __future__ import annotations

from pathlib import Path

from src.finance_metrics.revenue_realization import compute_revenue_realization
from src.utils.db import get_engine

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"

OUTPUT_FILES = {
    "overall": "revenue_realization_overall.csv",
    "month": "revenue_realization_by_month.csv",
    "merchant": "revenue_realization_by_merchant.csv",
}


def main() -> None:
    engine = get_engine()
    for grain, filename in OUTPUT_FILES.items():
        df = compute_revenue_realization(engine, group_by=grain)
        df.to_csv(PROCESSED_DIR / filename, index=False)
        print(f"{grain}: {len(df):,} rows -> {filename}")

    overall = compute_revenue_realization(engine, group_by="overall").iloc[0]
    print(f"\nOverall realization rate: {overall['realization_rate_percent']:.2f}%")
    print(f"Overall billing accuracy: {overall['billing_accuracy_percent']:.2f}%")
    print(f"Overall outstanding revenue: {overall['outstanding_revenue']:,.2f}")


if __name__ == "__main__":
    main()
