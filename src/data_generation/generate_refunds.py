"""Generates the refunds table, derived one-to-one from transactions with refund_amount > 0."""
import numpy as np
import pandas as pd

from src.utils import config as cfg

REASON_BY_ORDER_STATUS = {
    "Returned": {"Customer Return": 0.55, "Product Defect": 0.35, "Other": 0.10},
    "Cancelled": {"Order Cancelled": 0.85, "Duplicate Charge": 0.10, "Other": 0.05},
}

REFUND_STATUS_WEIGHTS = {"Processed": 0.85, "Pending": 0.10, "Rejected": 0.05}


def generate_refunds(transactions: pd.DataFrame) -> pd.DataFrame:
    rng = cfg.new_rng(offset=7)
    refunded = transactions[transactions["refund_amount"] > 0].copy().reset_index(drop=True)
    n = len(refunded)

    refund_reason = np.empty(n, dtype=object)
    for order_status, weights in REASON_BY_ORDER_STATUS.items():
        mask = refunded["order_status"] == order_status
        n_mask = mask.sum()
        if n_mask == 0:
            continue
        names, probs = zip(*weights.items())
        refund_reason[mask.values] = rng.choice(names, size=n_mask, p=probs)
    refund_reason[refund_reason == None] = "Other"  # noqa: E711

    status_names, status_probs = zip(*REFUND_STATUS_WEIGHTS.items())
    refund_status = rng.choice(status_names, size=n, p=status_probs)

    lag_days = rng.integers(1, 10, size=n)
    refund_date = refunded["transaction_date"].values + pd.to_timedelta(lag_days, unit="D")

    df = pd.DataFrame({
        "refund_id": [f"RFD{str(i).zfill(7)}" for i in range(1, n + 1)],
        "transaction_id": refunded["transaction_id"].values,
        "merchant_id": refunded["merchant_id"].values,
        "refund_date": refund_date,
        "refund_amount": refunded["refund_amount"].values,
        "refund_reason": refund_reason,
        "refund_status": refund_status,
    })
    return df
