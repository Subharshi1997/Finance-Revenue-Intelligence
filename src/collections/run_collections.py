"""Phase 9 entry point: run the AR aging, DSO, collections analytics, payment
behavior, and collection priority engines, writing each result to
data/processed/.

Run from the project root:
    python -m src.collections.run_collections
"""
from __future__ import annotations

import json
from pathlib import Path

from src.collections.ar_aging import aging_summary, build_ar_aging
from src.collections.collection_priority import build_collection_queue
from src.collections.collections_analytics import (
    average_collection_time,
    channel_effectiveness,
    collection_rate,
    promise_to_pay,
    recovery_rate,
    segment_effectiveness,
)
from src.collections.dso import dso_by, monthly_dso, overall_dso
from src.collections.payment_behavior import payer_segment_summary, payment_behavior_by_merchant
from src.utils.db import get_engine

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
AS_OF_DATE = "2026-08-13"


def main() -> None:
    engine = get_engine()

    # AR aging
    ar_aging = build_ar_aging(engine, as_of_date=AS_OF_DATE)
    ar_summary = aging_summary(ar_aging)
    ar_aging.to_csv(PROCESSED_DIR / "ar_aging.csv", index=False)
    ar_summary.to_csv(PROCESSED_DIR / "ar_aging_summary.csv", index=False)
    print(f"AR aging: {len(ar_aging):,} open invoices, total outstanding {ar_aging['outstanding_amount'].sum():,.2f}")
    print(ar_summary.to_string(index=False))

    # DSO
    dso_overall = overall_dso(engine, as_of_date=AS_OF_DATE)
    dso_monthly = monthly_dso(engine, as_of_date=AS_OF_DATE)
    dso_by_merchant = dso_by(engine, "merchant_id", as_of_date=AS_OF_DATE)
    dso_by_segment = dso_by(engine, "merchant_segment", as_of_date=AS_OF_DATE)
    dso_monthly.to_csv(PROCESSED_DIR / "dso_by_month.csv", index=False)
    dso_by_merchant.to_csv(PROCESSED_DIR / "dso_by_merchant.csv", index=False)
    dso_by_segment.to_csv(PROCESSED_DIR / "dso_by_segment.csv", index=False)
    print(f"\nOverall DSO (trailing 90 days): {dso_overall['dso_days']} days")

    # Collections analytics
    coll_rate = collection_rate(engine, as_of_date=AS_OF_DATE)
    recov_rate = recovery_rate(engine)
    avg_time = average_collection_time(engine)
    ptp = promise_to_pay(engine)
    channel = channel_effectiveness(engine)
    segment = segment_effectiveness(engine)
    channel.to_csv(PROCESSED_DIR / "collection_channel_effectiveness.csv", index=False)
    segment.to_csv(PROCESSED_DIR / "collection_segment_effectiveness.csv", index=False)

    collections_summary = {
        "collection_rate": coll_rate,
        "recovery_rate": recov_rate,
        "average_collection_time": avg_time,
        "promise_to_pay": ptp,
        "dso_overall": dso_overall,
    }
    with open(PROCESSED_DIR / "collections_summary.json", "w", encoding="utf-8") as f:
        json.dump(collections_summary, f, indent=2)
    print(f"\nCollection rate (trailing 90 days): {coll_rate['collection_rate_percent']}%")
    print(f"Recovery rate: {recov_rate['recovery_rate_percent']}%")
    print(f"Avg collection time: {avg_time['avg_collection_days']} days")
    print(f"Promise-to-pay fulfillment: {ptp['promise_fulfillment_rate_percent']}%")

    # Payment behavior
    behavior = payment_behavior_by_merchant(engine, as_of_date=AS_OF_DATE)
    behavior_summary = payer_segment_summary(behavior)
    behavior.to_csv(PROCESSED_DIR / "payment_behavior.csv", index=False)
    behavior_summary.to_csv(PROCESSED_DIR / "payment_behavior_summary.csv", index=False)
    print("\nPayer segment breakdown:")
    print(behavior_summary.to_string(index=False))

    # Collection priority queue
    queue = build_collection_queue(engine, as_of_date=AS_OF_DATE)
    queue.to_csv(PROCESSED_DIR / "collection_priority_queue.csv", index=False)
    print(f"\nCollection priority queue: {len(queue):,} overdue invoices")
    print(queue["priority_tier"].value_counts().to_string())
    print("\nTop 5 priority accounts:")
    print(queue.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
