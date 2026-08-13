"""Generates the disputes table, concentrated on invoices flagged with billing errors."""
import numpy as np
import pandas as pd

from src.utils import config as cfg

RESOLUTION_WEIGHTS = {"Resolved": 0.55, "Open": 0.20, "Escalated": 0.15, "Rejected": 0.10}


def generate_disputes(invoices: pd.DataFrame) -> pd.DataFrame:
    rng = cfg.new_rng(offset=10)

    error_invoices = invoices[invoices["invoice_error_flag"]]
    error_sample = error_invoices.sample(n=min(650, len(error_invoices)), random_state=int(rng.integers(0, 1_000_000))).copy()
    error_sample["dispute_type"] = rng.choice(
        ["Pricing Discrepancy", "Incorrect Fee Rate", "Duplicate Charge"], size=len(error_sample), p=[0.5, 0.35, 0.15]
    )

    non_error = invoices[~invoices["invoice_error_flag"]]
    other_sample = non_error.sample(n=min(200, len(non_error)), random_state=int(rng.integers(0, 1_000_000))).copy()
    other_sample["dispute_type"] = rng.choice(["Service Issue", "Tax Error"], size=len(other_sample), p=[0.7, 0.3])

    combined = pd.concat([error_sample, other_sample], ignore_index=True)
    n = len(combined)

    disputed_amount = np.where(
        combined["invoice_error_flag"],
        (combined["billed_fee"] - combined["expected_fee"]).abs() * rng.uniform(0.9, 1.1, size=n),
        combined["total_invoice_amount"] * rng.uniform(0.05, 0.25, size=n),
    )

    status_names, status_probs = zip(*RESOLUTION_WEIGHTS.items())
    resolution_status = rng.choice(status_names, size=n, p=status_probs)

    lag_days = rng.integers(2, 25, size=n)
    dispute_date = pd.to_datetime(combined["invoice_date"].values) + pd.to_timedelta(lag_days, unit="D")

    resolved_mask = np.isin(resolution_status, ["Resolved", "Rejected"])
    resolution_lag = rng.integers(3, 30, size=n)
    resolution_date = np.where(resolved_mask, dispute_date + pd.to_timedelta(resolution_lag, unit="D"), pd.NaT)

    resolution_amount = np.where(
        resolution_status == "Resolved", disputed_amount * rng.uniform(0.7, 1.0, size=n),
        np.where(resolution_status == "Rejected", 0.0, np.nan),
    )

    df = pd.DataFrame({
        "dispute_id": [f"DSP{str(i).zfill(6)}" for i in range(1, n + 1)],
        "merchant_id": combined["merchant_id"].values,
        "invoice_id": combined["invoice_id"].values,
        "dispute_date": dispute_date,
        "dispute_type": combined["dispute_type"].values,
        "disputed_amount": np.round(disputed_amount, 2),
        "resolution_status": resolution_status,
        "resolution_date": pd.to_datetime(resolution_date),
        "resolution_amount": np.round(resolution_amount, 2),
    })
    return df
