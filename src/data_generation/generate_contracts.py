"""Generates the contracts table: source-of-truth pricing terms per merchant, including
the ~15-20% of merchants who go through a mid-history pricing change (multiple contract rows)."""
import numpy as np
import pandas as pd

from src.utils import config as cfg

MULTI_PERIOD_PROBS = {1: 0.82, 2: 0.13, 3: 0.05}


def _num_periods(rng, n):
    values = list(MULTI_PERIOD_PROBS.keys())
    probs = list(MULTI_PERIOD_PROBS.values())
    return rng.choice(values, size=n, p=probs)


def generate_contracts(merchants: pd.DataFrame) -> pd.DataFrame:
    rng = cfg.new_rng(offset=2)
    n = len(merchants)
    periods = _num_periods(rng, n)

    rows = []
    contract_seq = 1
    for i, merchant in merchants.reset_index(drop=True).iterrows():
        n_periods = periods[i]
        start = merchant["onboarding_date"]
        hard_end = merchant["contract_end_date"] if pd.notna(merchant["contract_end_date"]) else cfg.END_DATE
        total_days = max((hard_end - start).days, 30)
        if total_days < 60:
            n_periods = 1

        boundaries = sorted(rng.choice(range(30, total_days), size=n_periods - 1, replace=False)) if n_periods > 1 else []
        cut_points = [0] + list(boundaries) + [total_days]

        base_fee = merchant["agreed_fee_percent"]
        base_plan = merchant["pricing_plan"]
        base_terms = merchant["payment_terms_days"]
        base_sub = merchant["monthly_subscription_fee"]

        for p in range(n_periods):
            eff_from = start + pd.Timedelta(days=cut_points[p])
            is_last = p == n_periods - 1
            eff_to = pd.NaT if (is_last and merchant["merchant_status"] == "Active") else start + pd.Timedelta(days=cut_points[p + 1])

            if p == 0:
                fee = base_fee
                plan = base_plan
                terms = base_terms
                sub = base_sub
            else:
                fee = round(base_fee + rng.uniform(-0.4, 0.3), 2)
                fee = max(fee, 1.0)
                plan = base_plan
                terms = base_terms
                sub = base_sub

            discount_percent = 0.0
            if rng.random() < 0.10:
                discount_percent = round(rng.uniform(5, 15), 1)

            fixed_fee = 0.0
            if rng.random() < 0.08:
                fixed_fee = round(rng.uniform(1, 3), 2)

            min_monthly_fee = 0.0
            if plan in ("Enterprise", "Custom") and rng.random() < 0.30:
                min_monthly_fee = float(rng.choice([2000, 5000, 10000]))

            if is_last:
                status = "Terminated" if merchant["merchant_status"] == "Churned" else "Active"
            else:
                status = "Superseded"

            rows.append({
                "contract_id": f"CTR{str(contract_seq).zfill(6)}",
                "merchant_id": merchant["merchant_id"],
                "effective_from": eff_from,
                "effective_to": eff_to,
                "pricing_plan": plan,
                "transaction_fee_percent": fee,
                "fixed_transaction_fee": fixed_fee,
                "subscription_fee": sub,
                "payment_terms_days": terms,
                "discount_percent": discount_percent,
                "minimum_monthly_fee": min_monthly_fee,
                "contract_status": status,
            })
            contract_seq += 1

    df = pd.DataFrame(rows)
    df["effective_from"] = pd.to_datetime(df["effective_from"])
    df["effective_to"] = pd.to_datetime(df["effective_to"])
    return df
