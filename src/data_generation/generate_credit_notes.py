"""Generates the credit_notes table, mostly tied to invoices flagged with billing errors,
plus a smaller share of goodwill/dispute-driven adjustments."""
import numpy as np
import pandas as pd

from src.utils import config as cfg

STATUS_WEIGHTS = {"Issued": 0.45, "Applied": 0.45, "Pending": 0.10}


def generate_credit_notes(invoices: pd.DataFrame) -> pd.DataFrame:
    rng = cfg.new_rng(offset=8)

    error_invoices = invoices[invoices["invoice_error_flag"]].copy()
    error_sample = error_invoices.sample(frac=0.78, random_state=int(rng.integers(0, 1_000_000)))
    error_sample["reason"] = np.where(
        error_sample["billed_fee"] > error_sample["expected_fee"],
        rng.choice(["Billing Error", "Pricing Correction"], size=len(error_sample), p=[0.6, 0.4]),
        "Pricing Correction",
    )
    error_sample["credit_amount"] = (error_sample["billed_fee"] - error_sample["expected_fee"]).abs() * rng.uniform(0.85, 1.05, size=len(error_sample))

    non_error = invoices[~invoices["invoice_error_flag"]]
    n_goodwill = min(max(int(len(invoices) * 0.012), 150), 400)
    goodwill_sample = non_error.sample(n=n_goodwill, random_state=int(rng.integers(0, 1_000_000))).copy()
    goodwill_sample["reason"] = rng.choice(["Goodwill Adjustment", "Dispute Resolution"], size=len(goodwill_sample), p=[0.6, 0.4])
    goodwill_sample["credit_amount"] = goodwill_sample["total_invoice_amount"] * rng.uniform(0.02, 0.15, size=len(goodwill_sample))

    combined = pd.concat([error_sample, goodwill_sample], ignore_index=True)
    n = len(combined)

    status_names, status_probs = zip(*STATUS_WEIGHTS.items())
    status = rng.choice(status_names, size=n, p=status_probs)

    lag_days = rng.integers(2, 20, size=n)
    credit_note_date = pd.to_datetime(combined["invoice_date"].values) + pd.to_timedelta(lag_days, unit="D")

    df = pd.DataFrame({
        "credit_note_id": [f"CRN{str(i).zfill(6)}" for i in range(1, n + 1)],
        "invoice_id": combined["invoice_id"].values,
        "merchant_id": combined["merchant_id"].values,
        "credit_note_date": credit_note_date,
        "credit_amount": combined["credit_amount"].round(2).values,
        "reason": combined["reason"].values,
        "status": status,
    })
    return df
