"""Orchestrates synthetic data generation for all 9 tables, in dependency order,
and writes each to data/raw/<table_name>.csv."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.utils import config as cfg
from src.data_generation.generate_merchants import generate_merchants
from src.data_generation.generate_contracts import generate_contracts
from src.data_generation.generate_transactions import generate_transactions
from src.data_generation.generate_invoices import generate_invoices
from src.data_generation.generate_payments import generate_payments
from src.data_generation.generate_refunds import generate_refunds
from src.data_generation.generate_credit_notes import generate_credit_notes
from src.data_generation.generate_collection_activity import generate_collection_activity
from src.data_generation.generate_disputes import generate_disputes

RAW_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw"))


def _save(df: pd.DataFrame, name: str) -> pd.DataFrame:
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, f"{name}.csv")
    df.to_csv(path, index=False)
    print(f"  {name:<22} {len(df):>8,} rows -> {path}")
    return df


def main():
    print(f"Generating synthetic data for {cfg.COMPANY_NAME} (seed={cfg.SEED})")
    print(f"Date window: {cfg.START_DATE.date()} to {cfg.END_DATE.date()}\n")

    merchants = generate_merchants()
    _save(merchants, "merchants")

    contracts = generate_contracts(merchants)
    _save(contracts, "contracts")

    transactions = generate_transactions(merchants, contracts)
    _save(transactions, "transactions")

    invoices = generate_invoices(merchants, contracts, transactions)

    payer_archetypes = cfg.derive_payer_archetypes(merchants["merchant_id"])
    payments, invoices = generate_payments(invoices, merchants, payer_archetypes)
    _save(invoices, "invoices")
    _save(payments, "payments")

    refunds = generate_refunds(transactions)
    _save(refunds, "refunds")

    credit_notes = generate_credit_notes(invoices)
    _save(credit_notes, "credit_notes")

    collection_activity = generate_collection_activity(invoices, payer_archetypes)
    _save(collection_activity, "collection_activity")

    disputes = generate_disputes(invoices)
    _save(disputes, "disputes")

    print("\nSanity stats:")
    print(f"  merchants: {merchants['merchant_status'].value_counts().to_dict()}")
    print(f"  merchant_segment mix: {merchants['merchant_segment'].value_counts(normalize=True).round(3).to_dict()}")
    print(f"  transactions with missing merchant_id: {transactions['merchant_id'].isna().sum()}")
    print(f"  transactions duplicate transaction_id rows: {transactions['transaction_id'].duplicated().sum()}")
    print(f"  invoices error flag rate: {invoices['invoice_error_flag'].mean():.3f}")
    print(f"  invoices payment_status mix: {invoices['payment_status'].value_counts(normalize=True).round(3).to_dict()}")
    print(f"  payments orphan (no invoice_id): {payments['invoice_id'].isna().sum()}")
    print("\nGeneration complete.")


if __name__ == "__main__":
    main()
