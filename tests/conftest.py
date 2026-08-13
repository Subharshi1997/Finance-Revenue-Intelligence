"""Shared pytest fixtures: a tiny in-memory SQLite database with a
hand-crafted set of merchants/invoices/payments/credit_notes/collection_activity
rows that exercise the edge cases the finance engines need to handle -
zero-amount invoices, full/partial/duplicate/overpayment, credit notes,
missing invoices/payments, same-day payment, and extremely overdue invoices.
"""
from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

SCHEMA = """
CREATE TABLE merchants (
    merchant_id TEXT PRIMARY KEY,
    merchant_name TEXT,
    merchant_segment TEXT,
    payment_terms_days INTEGER,
    merchant_status TEXT
);
CREATE TABLE invoices (
    invoice_id TEXT PRIMARY KEY,
    merchant_id TEXT,
    invoice_date TEXT,
    due_date TEXT,
    total_invoice_amount REAL,
    billed_fee REAL,
    invoice_status TEXT,
    payment_status TEXT
);
CREATE TABLE payments (
    payment_id TEXT PRIMARY KEY,
    invoice_id TEXT,
    merchant_id TEXT,
    payment_date TEXT,
    payment_amount REAL,
    payment_status TEXT
);
CREATE TABLE credit_notes (
    credit_note_id TEXT PRIMARY KEY,
    invoice_id TEXT,
    merchant_id TEXT,
    credit_amount REAL,
    status TEXT
);
CREATE TABLE collection_activity (
    collection_id TEXT PRIMARY KEY,
    merchant_id TEXT,
    invoice_id TEXT,
    activity_date TEXT,
    activity_type TEXT,
    contact_channel TEXT,
    collector TEXT,
    outcome TEXT,
    promised_payment_date TEXT,
    promised_amount REAL
);
"""

AS_OF_DATE = "2026-06-01"

MERCHANTS = pd.DataFrame([
    {"merchant_id": "M1", "merchant_name": "Alpha Corp", "merchant_segment": "Enterprise",
     "payment_terms_days": 30, "merchant_status": "Active"},
    {"merchant_id": "M2", "merchant_name": "Beta Retail", "merchant_segment": "SMB",
     "payment_terms_days": 15, "merchant_status": "Active"},
    {"merchant_id": "M3", "merchant_name": "Gamma Long-tail", "merchant_segment": "Long-tail",
     "payment_terms_days": 15, "merchant_status": "Churned"},
])

INVOICES = pd.DataFrame([
    # INV1: paid in full, same-day payment (delay = 0)
    {"invoice_id": "INV1", "merchant_id": "M1", "invoice_date": "2025-12-01", "due_date": "2026-01-01",
     "total_invoice_amount": 1000.0, "billed_fee": 1000.0, "invoice_status": "Paid", "payment_status": "Paid"},
    # INV2: partially paid, moderately overdue vs AS_OF_DATE
    {"invoice_id": "INV2", "merchant_id": "M1", "invoice_date": "2026-01-01", "due_date": "2026-02-01",
     "total_invoice_amount": 2000.0, "billed_fee": 2000.0, "invoice_status": "Issued", "payment_status": "Partially Paid"},
    # INV3: unpaid, missing payment entirely
    {"invoice_id": "INV3", "merchant_id": "M2", "invoice_date": "2026-01-01", "due_date": "2026-01-15",
     "total_invoice_amount": 500.0, "billed_fee": 500.0, "invoice_status": "Issued", "payment_status": "Unpaid"},
    # INV4: paid early (negative delay), also receives a duplicate payment -> overpaid
    {"invoice_id": "INV4", "merchant_id": "M2", "invoice_date": "2026-02-01", "due_date": "2026-03-01",
     "total_invoice_amount": 300.0, "billed_fee": 300.0, "invoice_status": "Paid", "payment_status": "Paid"},
    # INV5: extremely overdue (90+ days), unpaid - churned merchant
    {"invoice_id": "INV5", "merchant_id": "M3", "invoice_date": "2025-01-01", "due_date": "2025-02-01",
     "total_invoice_amount": 5000.0, "billed_fee": 5000.0, "invoice_status": "Issued", "payment_status": "Unpaid"},
    # INV6: fully offset by a credit note -> should drop out of AR aging (outstanding ~0)
    {"invoice_id": "INV6", "merchant_id": "M1", "invoice_date": "2026-01-01", "due_date": "2026-01-10",
     "total_invoice_amount": 1000.0, "billed_fee": 1000.0, "invoice_status": "Issued", "payment_status": "Unpaid"},
    # INV7: zero-amount invoice -> should never appear as outstanding
    {"invoice_id": "INV7", "merchant_id": "M2", "invoice_date": "2026-01-01", "due_date": "2026-01-20",
     "total_invoice_amount": 0.0, "billed_fee": 0.0, "invoice_status": "Paid", "payment_status": "Paid"},
])

PAYMENTS = pd.DataFrame([
    {"payment_id": "P1", "invoice_id": "INV1", "merchant_id": "M1", "payment_date": "2026-01-01",
     "payment_amount": 1000.0, "payment_status": "Success"},
    {"payment_id": "P2", "invoice_id": "INV2", "merchant_id": "M1", "payment_date": "2026-02-10",
     "payment_amount": 500.0, "payment_status": "Success"},
    # INV3 has no payment row at all (missing payment)
    {"payment_id": "P3", "invoice_id": "INV4", "merchant_id": "M2", "payment_date": "2026-02-25",
     "payment_amount": 300.0, "payment_status": "Success"},
    # duplicate payment on INV4 -> overpayment
    {"payment_id": "P4", "invoice_id": "INV4", "merchant_id": "M2", "payment_date": "2026-02-25",
     "payment_amount": 300.0, "payment_status": "Success"},
    {"payment_id": "P5", "invoice_id": "INV7", "merchant_id": "M2", "payment_date": "2026-01-01",
     "payment_amount": 0.0, "payment_status": "Success"},
    # a failed payment attempt on INV3 that should not count toward paid totals
    {"payment_id": "P6", "invoice_id": "INV3", "merchant_id": "M2", "payment_date": "2026-01-20",
     "payment_amount": 500.0, "payment_status": "Failed"},
])

CREDIT_NOTES = pd.DataFrame([
    {"credit_note_id": "CN1", "invoice_id": "INV6", "merchant_id": "M1", "credit_amount": 1000.0, "status": "Issued"},
])

COLLECTION_ACTIVITY = pd.DataFrame([
    {"collection_id": "C1", "merchant_id": "M1", "invoice_id": "INV2", "activity_date": "2026-02-05",
     "activity_type": "Reminder", "contact_channel": "Email", "collector": "Agent A", "outcome": "No Response",
     "promised_payment_date": None, "promised_amount": None},
    {"collection_id": "C2", "merchant_id": "M1", "invoice_id": "INV2", "activity_date": "2026-02-08",
     "activity_type": "Payment Promise", "contact_channel": "Phone", "collector": "Agent A",
     "outcome": "Promise to Pay", "promised_payment_date": "2026-02-12", "promised_amount": 500.0},
    {"collection_id": "C3", "merchant_id": "M2", "invoice_id": "INV3", "activity_date": "2026-01-20",
     "activity_type": "Escalation", "contact_channel": "Phone", "collector": "Agent B",
     "outcome": "Escalated", "promised_payment_date": None, "promised_amount": None},
    {"collection_id": "C4", "merchant_id": "M2", "invoice_id": "INV4", "activity_date": "2026-02-20",
     "activity_type": "Reminder", "contact_channel": "WhatsApp", "collector": "Agent B",
     "outcome": "Payment Received", "promised_payment_date": None, "promised_amount": None},
])


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as conn:
        for statement in SCHEMA.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
    MERCHANTS.to_sql("merchants", eng, if_exists="append", index=False)
    INVOICES.to_sql("invoices", eng, if_exists="append", index=False)
    PAYMENTS.to_sql("payments", eng, if_exists="append", index=False)
    CREDIT_NOTES.to_sql("credit_notes", eng, if_exists="append", index=False)
    COLLECTION_ACTIVITY.to_sql("collection_activity", eng, if_exists="append", index=False)
    return eng


# ---------------------------------------------------------------------------
# Richer fixture for billing / reconciliation / revenue-leakage / revenue-
# realization engines, which need transactions and contracts in addition to
# invoices/payments/credit_notes.
# ---------------------------------------------------------------------------

FULL_SCHEMA = """
CREATE TABLE merchants (
    merchant_id TEXT PRIMARY KEY,
    merchant_name TEXT,
    merchant_segment TEXT,
    payment_terms_days INTEGER,
    merchant_status TEXT
);
CREATE TABLE contracts (
    contract_id TEXT PRIMARY KEY,
    merchant_id TEXT,
    effective_from TEXT,
    effective_to TEXT,
    transaction_fee_percent REAL
);
CREATE TABLE transactions (
    transaction_id TEXT PRIMARY KEY,
    merchant_id TEXT,
    transaction_date TEXT,
    transaction_amount REAL,
    transaction_fee_percent REAL,
    expected_platform_fee REAL,
    payment_status TEXT,
    refund_amount REAL
);
CREATE TABLE invoices (
    invoice_id TEXT PRIMARY KEY,
    merchant_id TEXT,
    billing_period_start TEXT,
    invoice_date TEXT,
    due_date TEXT,
    total_invoice_amount REAL,
    expected_fee REAL,
    billed_fee REAL,
    invoice_status TEXT,
    invoice_error_flag INTEGER
);
CREATE TABLE payments (
    payment_id TEXT PRIMARY KEY,
    invoice_id TEXT,
    merchant_id TEXT,
    payment_date TEXT,
    payment_amount REAL,
    payment_status TEXT,
    settlement_date TEXT
);
CREATE TABLE credit_notes (
    credit_note_id TEXT PRIMARY KEY,
    invoice_id TEXT,
    merchant_id TEXT,
    credit_amount REAL,
    status TEXT
);
"""

FULL_MERCHANTS = pd.DataFrame([
    {"merchant_id": "MA", "merchant_name": "Alpha Retail", "merchant_segment": "Enterprise",
     "payment_terms_days": 15, "merchant_status": "Active"},
    {"merchant_id": "MB", "merchant_name": "Beta Stores", "merchant_segment": "SMB",
     "payment_terms_days": 15, "merchant_status": "Active"},
])

FULL_CONTRACTS = pd.DataFrame([
    # far enough in the past that Jan/Feb invoices are not "near" it - only
    # CT2's 2026-03-01 transition should trigger the Pricing Mismatch path
    {"contract_id": "CT1", "merchant_id": "MA", "effective_from": "2025-06-01",
     "effective_to": "2026-02-28", "transaction_fee_percent": 2.0},
    # rate change effective 2026-03-01 - anchors the Pricing Mismatch test
    {"contract_id": "CT2", "merchant_id": "MA", "effective_from": "2026-03-01",
     "effective_to": None, "transaction_fee_percent": 2.5},
    {"contract_id": "CT3", "merchant_id": "MB", "effective_from": "2026-01-01",
     "effective_to": None, "transaction_fee_percent": 3.0},
])

FULL_TRANSACTIONS = pd.DataFrame([
    {"transaction_id": "T1", "merchant_id": "MA", "transaction_date": "2026-01-15",
     "transaction_amount": 10000.0, "transaction_fee_percent": 2.0, "expected_platform_fee": 200.0,
     "payment_status": "Success", "refund_amount": 0.0},
    {"transaction_id": "T2", "merchant_id": "MA", "transaction_date": "2026-02-15",
     "transaction_amount": 10000.0, "transaction_fee_percent": 2.0, "expected_platform_fee": 200.0,
     "payment_status": "Success", "refund_amount": 0.0},
    # checkout applied the stale 2.0% rate but the correct new-contract rate is 2.5% -
    # a caught near-miss (invoicing bills on expected_platform_fee, the correct rate)
    {"transaction_id": "T3", "merchant_id": "MA", "transaction_date": "2026-03-10",
     "transaction_amount": 10000.0, "transaction_fee_percent": 2.0, "expected_platform_fee": 250.0,
     "payment_status": "Success", "refund_amount": 0.0},
    # partially refunded transaction, fee-on-refund never credited back
    {"transaction_id": "T4", "merchant_id": "MB", "transaction_date": "2026-01-20",
     "transaction_amount": 5000.0, "transaction_fee_percent": 3.0, "expected_platform_fee": 150.0,
     "payment_status": "Success", "refund_amount": 1000.0},
    # April transactions for MA with no invoice ever cut -> Missing Invoice
    {"transaction_id": "T5", "merchant_id": "MA", "transaction_date": "2026-04-05",
     "transaction_amount": 8000.0, "transaction_fee_percent": 2.5, "expected_platform_fee": 200.0,
     "payment_status": "Success", "refund_amount": 0.0},
])

FULL_INVOICES = pd.DataFrame([
    # Correct
    {"invoice_id": "INV_A_JAN", "merchant_id": "MA", "billing_period_start": "2026-01-01",
     "invoice_date": "2026-02-01", "due_date": "2026-02-15", "total_invoice_amount": 200.0,
     "expected_fee": 200.0, "billed_fee": 200.0, "invoice_status": "Issued", "invoice_error_flag": 0},
    # Underbilled (not near any contract transition)
    {"invoice_id": "INV_A_FEB", "merchant_id": "MA", "billing_period_start": "2026-02-01",
     "invoice_date": "2026-03-01", "due_date": "2026-03-15", "total_invoice_amount": 150.0,
     "expected_fee": 200.0, "billed_fee": 150.0, "invoice_status": "Issued", "invoice_error_flag": 1},
    # Underbilled AND right at the 2026-03-01 contract transition -> Pricing Mismatch
    {"invoice_id": "INV_A_MAR", "merchant_id": "MA", "billing_period_start": "2026-03-01",
     "invoice_date": "2026-04-01", "due_date": "2026-04-15", "total_invoice_amount": 200.0,
     "expected_fee": 250.0, "billed_fee": 200.0, "invoice_status": "Issued", "invoice_error_flag": 1},
    # MB January invoice - correct billing, but its transaction (T4) was refunded
    # without crediting back the fee -> refund-fee-retention review item
    {"invoice_id": "INV_B_JAN", "merchant_id": "MB", "billing_period_start": "2026-01-01",
     "invoice_date": "2026-02-01", "due_date": "2026-02-10", "total_invoice_amount": 150.0,
     "expected_fee": 150.0, "billed_fee": 150.0, "invoice_status": "Issued", "invoice_error_flag": 0},
    # ---- reconciliation-focused invoices (unrelated billing amounts) ----
    {"invoice_id": "INV_R1", "merchant_id": "MA", "billing_period_start": "2026-05-01",
     "invoice_date": "2026-05-01", "due_date": "2026-05-15", "total_invoice_amount": 1000.0,
     "expected_fee": 1000.0, "billed_fee": 1000.0, "invoice_status": "Issued", "invoice_error_flag": 0},
    {"invoice_id": "INV_R2", "merchant_id": "MA", "billing_period_start": "2026-05-01",
     "invoice_date": "2026-05-01", "due_date": "2026-05-15", "total_invoice_amount": 1000.0,
     "expected_fee": 1000.0, "billed_fee": 1000.0, "invoice_status": "Issued", "invoice_error_flag": 0},
    {"invoice_id": "INV_R3", "merchant_id": "MA", "billing_period_start": "2026-05-01",
     "invoice_date": "2026-05-01", "due_date": "2026-05-15", "total_invoice_amount": 1200.0,
     "expected_fee": 1200.0, "billed_fee": 1200.0, "invoice_status": "Issued", "invoice_error_flag": 0},
    {"invoice_id": "INV_R4", "merchant_id": "MA", "billing_period_start": "2026-05-01",
     "invoice_date": "2026-05-01", "due_date": "2026-05-15", "total_invoice_amount": 1000.0,
     "expected_fee": 1000.0, "billed_fee": 1000.0, "invoice_status": "Issued", "invoice_error_flag": 0},
    {"invoice_id": "INV_R5", "merchant_id": "MA", "billing_period_start": "2026-05-01",
     "invoice_date": "2026-05-01", "due_date": "2026-05-15", "total_invoice_amount": 1000.0,
     "expected_fee": 1000.0, "billed_fee": 1000.0, "invoice_status": "Issued", "invoice_error_flag": 0},
    {"invoice_id": "INV_R6", "merchant_id": "MA", "billing_period_start": "2026-05-01",
     "invoice_date": "2026-05-01", "due_date": "2026-05-15", "total_invoice_amount": 1000.0,
     "expected_fee": 1000.0, "billed_fee": 1000.0, "invoice_status": "Issued", "invoice_error_flag": 0},
    {"invoice_id": "INV_R7", "merchant_id": "MA", "billing_period_start": "2026-05-01",
     "invoice_date": "2026-05-01", "due_date": "2026-05-15", "total_invoice_amount": 500.0,
     "expected_fee": 500.0, "billed_fee": 500.0, "invoice_status": "Void", "invoice_error_flag": 0},
])

FULL_PAYMENTS = pd.DataFrame([
    # INV_R1: exact match -> MATCHED
    {"payment_id": "PR1", "invoice_id": "INV_R1", "merchant_id": "MA", "payment_date": "2026-05-20",
     "payment_amount": 1000.0, "payment_status": "Success", "settlement_date": "2026-05-21"},
    # INV_R2: no payments at all -> MISSING_PAYMENT
    # INV_R3: two payments of the same amount -> DUPLICATE
    {"payment_id": "PR3A", "invoice_id": "INV_R3", "merchant_id": "MA", "payment_date": "2026-05-20",
     "payment_amount": 600.0, "payment_status": "Success", "settlement_date": "2026-05-21"},
    {"payment_id": "PR3B", "invoice_id": "INV_R3", "merchant_id": "MA", "payment_date": "2026-05-21",
     "payment_amount": 600.0, "payment_status": "Success", "settlement_date": "2026-05-22"},
    # INV_R4: overpaid -> AMOUNT_MISMATCH
    {"payment_id": "PR4", "invoice_id": "INV_R4", "merchant_id": "MA", "payment_date": "2026-05-20",
     "payment_amount": 1500.0, "payment_status": "Success", "settlement_date": "2026-05-21"},
    # INV_R5: settled before it was paid -> TIMING_MISMATCH
    {"payment_id": "PR5", "invoice_id": "INV_R5", "merchant_id": "MA", "payment_date": "2026-05-20",
     "payment_amount": 1000.0, "payment_status": "Success", "settlement_date": "2026-05-18"},
    # INV_R6: partial payment -> PARTIAL
    {"payment_id": "PR6", "invoice_id": "INV_R6", "merchant_id": "MA", "payment_date": "2026-05-20",
     "payment_amount": 400.0, "payment_status": "Success", "settlement_date": "2026-05-21"},
    # INV_R7 is Void - a payment here should still resolve to VOID at invoice level
    {"payment_id": "PR7", "invoice_id": "INV_R7", "merchant_id": "MA", "payment_date": "2026-05-20",
     "payment_amount": 500.0, "payment_status": "Success", "settlement_date": "2026-05-21"},
    # Orphan payment - no invoice_id at all
    {"payment_id": "PORPHAN", "invoice_id": None, "merchant_id": "MA", "payment_date": "2026-05-20",
     "payment_amount": 250.0, "payment_status": "Success", "settlement_date": "2026-05-21"},
    # Unmatched payment - references an invoice_id that does not exist
    {"payment_id": "PGHOST", "invoice_id": "INV_GHOST", "merchant_id": "MA", "payment_date": "2026-05-20",
     "payment_amount": 100.0, "payment_status": "Success", "settlement_date": "2026-05-21"},
    # A failed payment attempt - should not affect invoice-level status
    {"payment_id": "PFAIL", "invoice_id": "INV_R2", "merchant_id": "MA", "payment_date": "2026-05-10",
     "payment_amount": 1000.0, "payment_status": "Failed", "settlement_date": None},
])

FULL_CREDIT_NOTES = pd.DataFrame([
    # Credit note against the underbilled-but-not-near-transition invoice -> Recovered
    {"credit_note_id": "FCN1", "invoice_id": "INV_A_FEB", "merchant_id": "MA",
     "credit_amount": 50.0, "status": "Applied"},
    # No credit note issued against INV_B_JAN despite the refund on T4 -> leakage stays open
])


@pytest.fixture()
def full_engine():
    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as conn:
        for statement in FULL_SCHEMA.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
    FULL_MERCHANTS.to_sql("merchants", eng, if_exists="append", index=False)
    FULL_CONTRACTS.to_sql("contracts", eng, if_exists="append", index=False)
    FULL_TRANSACTIONS.to_sql("transactions", eng, if_exists="append", index=False)
    FULL_INVOICES.to_sql("invoices", eng, if_exists="append", index=False)
    FULL_PAYMENTS.to_sql("payments", eng, if_exists="append", index=False)
    FULL_CREDIT_NOTES.to_sql("credit_notes", eng, if_exists="append", index=False)
    return eng
