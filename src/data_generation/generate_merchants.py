"""Generates the merchants master table: ~950 fictional D2C merchants with segment,
pricing plan and lifecycle attributes that drive every downstream table."""
import numpy as np
import pandas as pd
from faker import Faker

from src.utils import config as cfg

N_MERCHANTS = 950


def _sample_onboarding_dates(rng, n):
    span_days = (cfg.END_DATE - cfg.START_DATE).days
    is_founding_cohort = rng.random(n) < 0.90
    offsets = np.where(
        is_founding_cohort,
        rng.integers(0, 35, size=n),
        rng.integers(35, span_days, size=n),
    )
    return cfg.START_DATE + pd.to_timedelta(offsets, unit="D")


def _sample_pricing_plans(rng, segments):
    plans = np.empty(len(segments), dtype=object)
    for segment in cfg.SEGMENTS:
        mask = segments == segment
        n = mask.sum()
        weights = cfg.SEGMENT_PRICING_PLAN_WEIGHTS[segment]
        names, probs = zip(*weights.items())
        plans[mask] = rng.choice(names, size=n, p=probs)
    return plans


def generate_merchants(n_merchants: int = N_MERCHANTS) -> pd.DataFrame:
    rng = cfg.new_rng(offset=1)
    faker = Faker()
    Faker.seed(cfg.SEED)

    merchant_id = [f"MER{str(i).zfill(5)}" for i in range(1, n_merchants + 1)]
    merchant_name = [faker.company() for _ in range(n_merchants)]
    industry = rng.choice(cfg.INDUSTRIES, size=n_merchants)
    segment = rng.choice(cfg.SEGMENTS, size=n_merchants, p=cfg.SEGMENT_WEIGHTS)

    city_idx = rng.integers(0, len(cfg.CITY_STATE), size=n_merchants)
    city = [cfg.CITY_STATE[i][0] for i in city_idx]
    state = [cfg.CITY_STATE[i][1] for i in city_idx]

    onboarding_date = _sample_onboarding_dates(rng, n_merchants)
    account_manager = rng.choice(cfg.ACCOUNT_MANAGERS, size=n_merchants)
    pricing_plan = _sample_pricing_plans(rng, segment)

    agreed_fee_percent = np.empty(n_merchants)
    payment_terms_days = np.empty(n_merchants, dtype=int)
    for seg in cfg.SEGMENTS:
        mask = segment == seg
        lo, hi = cfg.SEGMENT_FEE_RANGE[seg]
        agreed_fee_percent[mask] = rng.uniform(lo, hi, size=mask.sum()).round(2)
        payment_terms_days[mask] = rng.choice(cfg.SEGMENT_PAYMENT_TERMS[seg], size=mask.sum())

    monthly_subscription_fee = np.array([cfg.PRICING_PLAN_SUBSCRIPTION_FEE[p] for p in pricing_plan])

    status_names, status_probs = zip(*cfg.MERCHANT_STATUS_WEIGHTS.items())
    merchant_status = rng.choice(status_names, size=n_merchants, p=status_probs)

    contract_start_date = onboarding_date
    contract_end_date = pd.Series(pd.NaT, index=range(n_merchants))
    churned_mask = merchant_status == "Churned"
    n_churned = churned_mask.sum()
    max_tenure_days = (cfg.END_DATE - pd.Series(onboarding_date)[churned_mask]).dt.days.clip(lower=30)
    churn_offsets = (rng.uniform(0.3, 1.0, size=n_churned) * max_tenure_days.values).astype(int)
    contract_end_date.loc[churned_mask] = (
        pd.Series(onboarding_date)[churned_mask].values + pd.to_timedelta(churn_offsets, unit="D")
    )

    df = pd.DataFrame({
        "merchant_id": merchant_id,
        "merchant_name": merchant_name,
        "industry": industry,
        "merchant_segment": segment,
        "city": city,
        "state": state,
        "country": cfg.COUNTRY,
        "onboarding_date": onboarding_date,
        "account_manager": account_manager,
        "pricing_plan": pricing_plan,
        "contract_start_date": contract_start_date,
        "contract_end_date": contract_end_date,
        "agreed_fee_percent": agreed_fee_percent,
        "monthly_subscription_fee": monthly_subscription_fee,
        "payment_terms_days": payment_terms_days,
        "merchant_status": merchant_status,
    })

    for col in ["onboarding_date", "contract_start_date", "contract_end_date"]:
        df[col] = pd.to_datetime(df[col])

    return df
