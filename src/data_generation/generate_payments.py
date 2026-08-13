"""Generates the payments table plus reconciled invoice payment_status/invoice_status.
Payment timing and completeness are driven by a per-merchant payer archetype so behaviour
is consistent across a merchant's invoices rather than random per row."""
import numpy as np
import pandas as pd

from src.utils import config as cfg

ARCHETYPE_PARAMS = {
    "Excellent": {"no_payment_prob": 0.02, "partial_prob": 0.05, "delay_mean": -2, "delay_sd": 3, "final_completion": 0.95, "fail_prob": 0.01},
    "Good": {"no_payment_prob": 0.07, "partial_prob": 0.12, "delay_mean": 5, "delay_sd": 6, "final_completion": 0.85, "fail_prob": 0.02},
    "Moderate": {"no_payment_prob": 0.15, "partial_prob": 0.25, "delay_mean": 18, "delay_sd": 10, "final_completion": 0.65, "fail_prob": 0.03},
    "High-risk": {"no_payment_prob": 0.30, "partial_prob": 0.40, "delay_mean": 35, "delay_sd": 15, "final_completion": 0.35, "fail_prob": 0.05},
}


def _random_reference(rng, prefix, n, width=10):
    letters = np.array(list("ABCDEFGHJKLMNPQRSTUVWXYZ23456789"))
    codes = rng.choice(letters, size=(n, width))
    return [prefix + "".join(row) for row in codes]


def _payment_batch(rng, invoice_ids, merchant_ids, due_dates, amounts, delay_mean, delay_sd, fail_prob):
    n = len(invoice_ids)
    if n == 0:
        return pd.DataFrame()
    delay = np.clip(rng.normal(delay_mean, delay_sd, size=n), -10, 150).astype(int)
    pay_dates = pd.to_datetime(due_dates) + pd.to_timedelta(delay, unit="D")
    statuses = rng.choice(["Success", "Failed"], size=n, p=[1 - fail_prob, fail_prob])
    settlement = pd.Series(pay_dates + pd.to_timedelta(rng.integers(1, 4, size=n), unit="D"))
    settlement = settlement.where(statuses == "Success", pd.NaT)

    return pd.DataFrame({
        "invoice_id": invoice_ids,
        "merchant_id": merchant_ids,
        "payment_date": pay_dates,
        "payment_amount": np.round(amounts, 2),
        "payment_method": rng.choice(cfg.PAYMENT_METHODS, size=n, p=cfg.PAYMENT_METHOD_WEIGHTS),
        "payment_reference": _random_reference(rng, "PAY", n),
        "payment_status": statuses,
        "bank_reference": _random_reference(rng, "BNK", n, width=12),
        "settlement_date": settlement,
    })


def generate_payments(invoices: pd.DataFrame, merchants: pd.DataFrame, payer_archetypes: dict):
    rng = cfg.new_rng(offset=6)
    inv = invoices.copy()
    inv["archetype"] = inv["merchant_id"].map(payer_archetypes)
    payable = inv[inv["invoice_status"] == "Issued"].copy()

    batches = []
    for archetype, params in ARCHETYPE_PARAMS.items():
        grp = payable[payable["archetype"] == archetype]
        n = len(grp)
        if n == 0:
            continue

        draw = rng.random(n)
        has_payment = draw >= params["no_payment_prob"]
        is_partial = has_payment & (rng.random(n) < params["partial_prob"])
        full_pay = has_payment & ~is_partial

        full_grp = grp[full_pay]
        batches.append(_payment_batch(
            rng, full_grp["invoice_id"].values, full_grp["merchant_id"].values,
            full_grp["due_date"].values, full_grp["total_invoice_amount"].values,
            params["delay_mean"], params["delay_sd"], params["fail_prob"],
        ))

        partial_grp = grp[is_partial]
        n_partial = len(partial_grp)
        if n_partial:
            first_share = rng.uniform(0.3, 0.7, size=n_partial)
            first_amounts = partial_grp["total_invoice_amount"].values * first_share
            batches.append(_payment_batch(
                rng, partial_grp["invoice_id"].values, partial_grp["merchant_id"].values,
                partial_grp["due_date"].values, first_amounts,
                params["delay_mean"], params["delay_sd"], params["fail_prob"],
            ))

            completes = rng.random(n_partial) < params["final_completion"]
            final_grp = partial_grp[completes]
            final_amounts = final_grp["total_invoice_amount"].values * (1 - first_share[completes])
            batches.append(_payment_batch(
                rng, final_grp["invoice_id"].values, final_grp["merchant_id"].values,
                final_grp["due_date"].values, final_amounts,
                params["delay_mean"] + 15, params["delay_sd"], params["fail_prob"],
            ))

    payments = pd.concat([b for b in batches if not b.empty], ignore_index=True)

    paid_success = payments[payments["payment_status"] == "Success"]
    dup_source = paid_success.sample(frac=0.015, random_state=int(rng.integers(0, 1_000_000)))
    if len(dup_source):
        dup_rows = dup_source.copy()
        dup_rows["payment_date"] = dup_rows["payment_date"] + pd.to_timedelta(rng.integers(0, 3, size=len(dup_rows)), unit="D")
        dup_rows["payment_reference"] = _random_reference(rng, "PAY", len(dup_rows))
        dup_rows["bank_reference"] = _random_reference(rng, "BNK", len(dup_rows), width=12)
        payments = pd.concat([payments, dup_rows], ignore_index=True)

    n_orphan = max(int(len(payments) * 0.01), 1)
    orphan_merchants = rng.choice(merchants["merchant_id"].values, size=n_orphan)
    orphan_dates = cfg.START_DATE + pd.to_timedelta(rng.integers(0, (cfg.END_DATE - cfg.START_DATE).days, size=n_orphan), unit="D")
    orphan = pd.DataFrame({
        "invoice_id": [None] * n_orphan,
        "merchant_id": orphan_merchants,
        "payment_date": orphan_dates,
        "payment_amount": np.round(rng.uniform(500, 20000, size=n_orphan), 2),
        "payment_method": rng.choice(cfg.PAYMENT_METHODS, size=n_orphan, p=cfg.PAYMENT_METHOD_WEIGHTS),
        "payment_reference": _random_reference(rng, "PAY", n_orphan),
        "payment_status": "Success",
        "bank_reference": _random_reference(rng, "BNK", n_orphan, width=12),
        "settlement_date": orphan_dates + pd.to_timedelta(2, unit="D"),
    })
    payments = pd.concat([payments, orphan], ignore_index=True)

    payments = payments.reset_index(drop=True)
    payments.insert(0, "payment_id", [f"PAY{str(i).zfill(7)}" for i in range(1, len(payments) + 1)])

    updated_invoices = _reconcile_invoices(inv, payments)
    return payments, updated_invoices


def _reconcile_invoices(inv: pd.DataFrame, payments: pd.DataFrame) -> pd.DataFrame:
    successful = payments[(payments["payment_status"] == "Success") & payments["invoice_id"].notna()]
    paid_totals = successful.groupby("invoice_id")["payment_amount"].sum()

    inv = inv.copy()
    inv["_paid_total"] = inv["invoice_id"].map(paid_totals).fillna(0.0)

    ratio = inv["_paid_total"] / inv["total_invoice_amount"].replace(0, np.nan)
    inv["payment_status"] = np.select(
        [ratio >= 0.995, inv["_paid_total"] > 0],
        ["Paid", "Partially Paid"],
        default="Unpaid",
    )

    as_of = cfg.END_DATE + pd.Timedelta(days=13)
    overdue_mask = (inv["payment_status"] != "Paid") & (inv["due_date"] < as_of) & (inv["invoice_status"] == "Issued")
    inv.loc[overdue_mask, "invoice_status"] = "Overdue"
    inv.loc[(inv["payment_status"] == "Paid") & (inv["invoice_status"].isin(["Issued", "Overdue"])), "invoice_status"] = "Paid"

    return inv.drop(columns=["_paid_total", "archetype"])
