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
