"""Collection priority scoring (Step 10).

A transparent, explainable score (0-100) per overdue invoice so collectors
know exactly which accounts to work first and why.

Collection Priority Score =
    40% Outstanding Amount Risk   - size of the balance at risk, normalized
                                     against the largest outstanding balance
    30% Days Overdue Risk         - how overdue the invoice is, normalized
                                     against a 120-day cap
    20% Historical Payment Behavior - the merchant's payer_segment, mapped to
                                     a risk score (Excellent=0 ... High-risk=100)
    10% Customer Risk             - merchant_status / segment risk (churned or
                                     long-tail merchants score higher risk)

Each component is normalized to a 0-100 scale before weighting so no single
raw unit (rupees vs. days) can dominate the score by magnitude alone.
"""
from __future__ import annotations

import pandas as pd

from src.collections.ar_aging import build_ar_aging
from src.collections.payment_behavior import payment_behavior_by_merchant

WEIGHTS = {
    "outstanding_amount_risk": 0.40,
    "days_overdue_risk": 0.30,
    "payment_behavior_risk": 0.20,
    "customer_risk": 0.10,
}

PAYER_SEGMENT_RISK = {
    "Excellent": 0, "Good": 30, "Moderate": 60, "High-risk": 100, "Insufficient Data": 50,
}

DAYS_OVERDUE_CAP = 120

RECOMMENDED_ACTION = {
    "Critical": "Immediate escalation - account manager + finance lead call",
    "High": "Phone + email follow-up within 48 hours",
    "Medium": "Standard reminder sequence (email, then phone)",
    "Low": "Automated reminder only",
}


def _priority_tier(score: float) -> str:
    if score >= 75:
        return "Critical"
    if score >= 55:
        return "High"
    if score >= 30:
        return "Medium"
    return "Low"


def build_collection_queue(engine, as_of_date: str = "2026-08-13") -> pd.DataFrame:
    ar = build_ar_aging(engine, as_of_date=as_of_date)
    overdue = ar[ar["days_overdue"] > 0].copy()

    behavior = payment_behavior_by_merchant(engine, as_of_date=as_of_date)[
        ["merchant_id", "payer_segment", "avg_payment_delay_days"]
    ]
    merchant_status = pd.read_sql("SELECT merchant_id, merchant_status FROM merchants", engine)

    df = overdue.merge(behavior, on="merchant_id", how="left").merge(merchant_status, on="merchant_id", how="left")
    df["payer_segment"] = df["payer_segment"].fillna("Insufficient Data")

    max_outstanding = df["outstanding_amount"].max() or 1.0
    df["outstanding_amount_risk"] = (100 * df["outstanding_amount"] / max_outstanding).clip(upper=100)
    df["days_overdue_risk"] = (100 * df["days_overdue"] / DAYS_OVERDUE_CAP).clip(upper=100)
    df["payment_behavior_risk"] = df["payer_segment"].map(PAYER_SEGMENT_RISK).fillna(50)
    df["customer_risk"] = df["merchant_status"].map({"Active": 20, "Suspended": 80, "Churned": 100}).fillna(50)

    df["priority_score"] = (
        WEIGHTS["outstanding_amount_risk"] * df["outstanding_amount_risk"]
        + WEIGHTS["days_overdue_risk"] * df["days_overdue_risk"]
        + WEIGHTS["payment_behavior_risk"] * df["payment_behavior_risk"]
        + WEIGHTS["customer_risk"] * df["customer_risk"]
    ).round(1)

    df["priority_tier"] = df["priority_score"].apply(_priority_tier)
    df["recommended_action"] = df["priority_tier"].map(RECOMMENDED_ACTION)

    df = df.sort_values("priority_score", ascending=False).reset_index(drop=True)
    df.insert(0, "priority_rank", df.index + 1)

    return df[[
        "priority_rank", "merchant_id", "merchant_name", "merchant_segment", "invoice_id",
        "outstanding_amount", "days_overdue", "aging_bucket", "payer_segment",
        "priority_score", "priority_tier", "recommended_action",
    ]]
