"""Generates the transactions table (120k+ rows): per-order GMV records with growth,
festive-season seasonality, segment-scaled volume, and a set of realistic data imperfections."""
import numpy as np
import pandas as pd

from src.utils import config as cfg

WRONG_RATE_SHARE = 0.04
DUPLICATE_SHARE = 0.004
MISSING_MERCHANT_SHARE = 0.01
MISSING_PAYMENT_STATUS_SHARE = 0.012
INVALID_AMOUNT_ROWS = 35

PAYMENT_STATUS_WEIGHTS = {"Success": 0.92, "Failed": 0.05, "Pending": 0.03}

ORDER_STATUS_BY_PAYMENT = {
    "Success": ({"Delivered": 0.82, "Returned": 0.11, "Cancelled": 0.04, "Processing": 0.03}),
    "Failed": ({"Cancelled": 0.7, "Processing": 0.3}),
    "Pending": ({"Processing": 0.8, "Cancelled": 0.2}),
}


def _month_end(month_start):
    return month_start + pd.offsets.MonthEnd(0)


def _merchant_month_batch(rng, merchant, month_start, count):
    days_in_month = (_month_end(month_start) - month_start).days + 1
    day_offsets = rng.integers(0, days_in_month, size=count)
    dates = month_start + pd.to_timedelta(day_offsets, unit="D")

    aov_base = cfg.INDUSTRY_AOV[merchant["industry"]] * cfg.SEGMENT_AOV_MULTIPLIER[merchant["merchant_segment"]]
    amounts = rng.lognormal(mean=np.log(aov_base), sigma=0.6, size=count)
    amounts = np.clip(amounts, 200, 60000).round(2)

    payment_methods = rng.choice(cfg.PAYMENT_METHODS, size=count, p=cfg.PAYMENT_METHOD_WEIGHTS)

    p_names, p_probs = zip(*PAYMENT_STATUS_WEIGHTS.items())
    payment_statuses = rng.choice(p_names, size=count, p=p_probs)

    order_statuses = np.empty(count, dtype=object)
    for status in p_names:
        mask = payment_statuses == status
        n_mask = mask.sum()
        if n_mask == 0:
            continue
        o_names, o_probs = zip(*ORDER_STATUS_BY_PAYMENT[status].items())
        order_statuses[mask] = rng.choice(o_names, size=n_mask, p=o_probs)

    discount_amount = np.zeros(count)
    discount_mask = rng.random(count) < 0.15
    discount_amount[discount_mask] = (amounts[discount_mask] * rng.uniform(0.05, 0.2, size=discount_mask.sum())).round(2)

    refund_amount = np.zeros(count)
    returned_mask = order_statuses == "Returned"
    if returned_mask.any():
        full_mask = returned_mask & (rng.random(count) < 0.7)
        partial_mask = returned_mask & ~full_mask
        refund_amount[full_mask] = amounts[full_mask]
        refund_amount[partial_mask] = (amounts[partial_mask] * rng.uniform(0.3, 0.9, size=partial_mask.sum())).round(2)

    cancelled_paid_mask = (order_statuses == "Cancelled") & (payment_statuses == "Success")
    if cancelled_paid_mask.any():
        refund_amount[cancelled_paid_mask] = (amounts[cancelled_paid_mask] * rng.uniform(0.85, 1.0, size=cancelled_paid_mask.sum())).round(2)

    return pd.DataFrame({
        "merchant_id": merchant["merchant_id"],
        "transaction_date": dates,
        "transaction_amount": amounts,
        "payment_method": payment_methods,
        "payment_status": payment_statuses,
        "order_status": order_statuses,
        "discount_amount": discount_amount,
        "refund_amount": refund_amount.round(2),
    })


def _generate_base_transactions(merchants: pd.DataFrame) -> pd.DataFrame:
    rng = cfg.new_rng(offset=3)
    batches = []

    for _, merchant in merchants.iterrows():
        lo, hi = cfg.SEGMENT_MONTHLY_TXN_RANGE[merchant["merchant_segment"]]
        base_size = rng.uniform(lo, hi)
        if base_size <= 0:
            continue

        window_end = merchant["contract_end_date"] if merchant["merchant_status"] == "Churned" else cfg.END_DATE
        onboarding_month = pd.Timestamp(year=merchant["onboarding_date"].year, month=merchant["onboarding_date"].month, day=1)

        for month_start in cfg.MONTH_STARTS:
            if month_start < onboarding_month or month_start > window_end:
                continue
            lam = base_size * cfg.growth_multiplier(month_start) * cfg.seasonality_multiplier(month_start)
            count = rng.poisson(lam)
            if count <= 0:
                continue
            batches.append(_merchant_month_batch(rng, merchant, month_start, count))

    return pd.concat(batches, ignore_index=True)


def _attach_pricing(transactions: pd.DataFrame, contracts: pd.DataFrame, rng) -> pd.DataFrame:
    contracts_sorted = contracts.sort_values(["effective_from"]).copy()
    txns_sorted = transactions.sort_values(["transaction_date"]).reset_index(drop=True)

    merged = pd.merge_asof(
        txns_sorted,
        contracts_sorted[["merchant_id", "effective_from", "transaction_fee_percent"]],
        left_on="transaction_date",
        right_on="effective_from",
        by="merchant_id",
        direction="backward",
    ).rename(columns={"transaction_fee_percent": "correct_fee_percent"})
    merged["correct_fee_percent"] = merged["correct_fee_percent"].fillna(2.5)
    merged["expected_platform_fee"] = (merged["transaction_amount"] * merged["correct_fee_percent"] / 100).round(2)

    applied_fee_percent = merged["correct_fee_percent"].copy()
    wrong_mask = rng.random(len(merged)) < WRONG_RATE_SHARE
    drift = rng.choice([-1, 1], size=wrong_mask.sum()) * rng.uniform(0.3, 1.0, size=wrong_mask.sum())
    applied_fee_percent.loc[wrong_mask] = (merged.loc[wrong_mask, "correct_fee_percent"] + drift).clip(lower=0.5).round(2)
    merged["transaction_fee_percent"] = applied_fee_percent

    return merged.drop(columns=["effective_from"])


def _apply_imperfections(transactions: pd.DataFrame, rng) -> pd.DataFrame:
    df = transactions.copy()
    n = len(df)

    n_dup = int(n * DUPLICATE_SHARE)
    dup_rows = df.sample(n=n_dup, random_state=rng.integers(0, 1_000_000))
    df = pd.concat([df, dup_rows], ignore_index=True)

    missing_merchant_idx = df.sample(frac=MISSING_MERCHANT_SHARE, random_state=rng.integers(0, 1_000_000)).index
    df.loc[missing_merchant_idx, "merchant_id"] = np.nan

    missing_status_idx = df.sample(frac=MISSING_PAYMENT_STATUS_SHARE, random_state=rng.integers(0, 1_000_000)).index
    df.loc[missing_status_idx, "payment_status"] = np.nan

    invalid_idx = df.sample(n=INVALID_AMOUNT_ROWS, random_state=rng.integers(0, 1_000_000)).index
    df.loc[invalid_idx, "transaction_amount"] = -df.loc[invalid_idx, "transaction_amount"].abs()

    return df


def generate_transactions(merchants: pd.DataFrame, contracts: pd.DataFrame) -> pd.DataFrame:
    rng = cfg.new_rng(offset=4)

    base = _generate_base_transactions(merchants)
    priced = _attach_pricing(base, contracts, rng).reset_index(drop=True)

    priced.insert(0, "transaction_id", [f"TXN{str(i).zfill(8)}" for i in range(1, len(priced) + 1)])
    priced["order_id"] = [f"ORD{str(i).zfill(8)}" for i in range(1, len(priced) + 1)]
    priced["currency"] = cfg.CURRENCY
    seconds_offset = rng.integers(0, 86400, size=len(priced))
    priced["created_timestamp"] = priced["transaction_date"] + pd.to_timedelta(seconds_offset, unit="s")

    final = _apply_imperfections(priced, rng)

    cols = [
        "transaction_id", "merchant_id", "transaction_date", "order_id", "transaction_amount",
        "transaction_fee_percent", "expected_platform_fee", "payment_method", "payment_status",
        "order_status", "refund_amount", "discount_amount", "currency", "created_timestamp",
    ]
    return final[cols]
