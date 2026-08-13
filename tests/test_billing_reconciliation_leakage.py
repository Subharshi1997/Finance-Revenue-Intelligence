"""Tests for billing validation, reconciliation, revenue leakage, and revenue
realization engines, using the richer `full_engine` fixture (merchants,
contracts, transactions, invoices, payments, credit_notes) from conftest.py.
"""
from __future__ import annotations

import pandas as pd

from src.billing.billing_engine import build_merchant_month_billing
from src.finance_metrics.revenue_realization import compute_revenue_realization
from src.reconciliation.reconciliation_engine import (
    reconcile_invoices,
    reconcile_missing_invoices,
    reconcile_payments,
    reconciliation_summary,
)
from src.revenue_leakage.leakage_engine import build_leakage_table


# ---------------------------------------------------------------------------
# Billing engine
# ---------------------------------------------------------------------------

def test_billing_status_correct_invoice(full_engine):
    billing = build_merchant_month_billing(full_engine)
    row = billing[billing["invoice_id"] == "INV_A_JAN"].iloc[0]
    assert row["billing_status"] == "Correct"
    assert row["revenue_difference"] == 0.0


def test_billing_status_underbilled_away_from_transition(full_engine):
    billing = build_merchant_month_billing(full_engine)
    row = billing[billing["invoice_id"] == "INV_A_FEB"].iloc[0]
    assert row["billing_status"] == "Underbilled"
    assert row["revenue_difference"] == -50.0


def test_billing_status_pricing_mismatch_near_contract_transition(full_engine):
    billing = build_merchant_month_billing(full_engine)
    row = billing[billing["invoice_id"] == "INV_A_MAR"].iloc[0]
    # Same -50 error as INV_A_FEB, but this one sits right at the 2026-03-01
    # rate change, so it must be classified differently.
    assert row["billing_status"] == "Pricing Mismatch"
    assert row["revenue_difference"] == -50.0


def test_billing_status_flags_missing_invoice(full_engine):
    billing = build_merchant_month_billing(full_engine)
    missing = billing[billing["billing_status"] == "Missing Invoice"]
    assert len(missing) == 1
    row = missing.iloc[0]
    assert row["merchant_id"] == "MA"
    assert row["billing_period"] == "2026-04"
    assert row["expected_revenue"] == 200.0
    assert row["invoice_id"] is None


# ---------------------------------------------------------------------------
# Reconciliation engine
# ---------------------------------------------------------------------------

def test_reconcile_invoices_status_per_scenario(full_engine):
    recon = reconcile_invoices(full_engine).set_index("invoice_id")
    assert recon.loc["INV_R1", "reconciliation_status"] == "MATCHED"
    assert recon.loc["INV_R2", "reconciliation_status"] == "MISSING_PAYMENT"
    assert recon.loc["INV_R3", "reconciliation_status"] == "DUPLICATE"
    assert recon.loc["INV_R4", "reconciliation_status"] == "AMOUNT_MISMATCH"
    assert recon.loc["INV_R5", "reconciliation_status"] == "TIMING_MISMATCH"
    assert recon.loc["INV_R6", "reconciliation_status"] == "PARTIAL"
    assert recon.loc["INV_R7", "reconciliation_status"] == "VOID"


def test_reconcile_payments_status_per_scenario(full_engine):
    recon = reconcile_payments(full_engine).set_index("payment_id")
    assert recon.loc["PR1", "reconciliation_status"] == "MATCHED"
    assert recon.loc["PORPHAN", "reconciliation_status"] == "ORPHAN"
    assert recon.loc["PGHOST", "reconciliation_status"] == "UNMATCHED"
    assert recon.loc["PR3A", "reconciliation_status"] == "DUPLICATE"
    assert recon.loc["PR3B", "reconciliation_status"] == "DUPLICATE"
    assert recon.loc["PFAIL", "reconciliation_status"] == "NOT_APPLICABLE_FAILED"


def test_reconcile_missing_invoices_detects_uninvoiced_month(full_engine):
    missing = reconcile_missing_invoices(full_engine)
    assert len(missing) == 1
    row = missing.iloc[0]
    assert row["merchant_id"] == "MA"
    assert row["billing_period"] == "2026-04"
    assert row["reconciliation_status"] == "MISSING_INVOICE"


def test_reconciliation_summary_rate_bounded(full_engine):
    invoice_recon = reconcile_invoices(full_engine)
    missing = reconcile_missing_invoices(full_engine)
    summary = reconciliation_summary(invoice_recon, missing)
    rate = summary.attrs["reconciliation_rate_percent"]
    assert 0 <= rate <= 100
    # every status we deliberately created should show up in the summary
    statuses = set(summary["reconciliation_status"])
    assert {"MATCHED", "MISSING_PAYMENT", "DUPLICATE", "AMOUNT_MISMATCH",
            "TIMING_MISMATCH", "PARTIAL", "VOID", "MISSING_INVOICE"}.issubset(statuses)


# ---------------------------------------------------------------------------
# Revenue leakage engine
# ---------------------------------------------------------------------------

def test_leakage_table_contains_expected_types(full_engine):
    billing = build_merchant_month_billing(full_engine)
    credit_notes = pd.read_sql("SELECT invoice_id, status FROM credit_notes", full_engine)
    leakage = build_leakage_table(full_engine, billing, credit_notes)

    types_present = set(leakage["leakage_type"])
    assert "Underbilling" in types_present
    assert "Pricing Mismatch" in types_present
    assert "Missing Invoice" in types_present
    assert "Rate Discrepancy" in types_present
    assert "Refund Fee Retention (Policy Review)" in types_present


def test_leakage_underbilling_recovered_via_credit_note(full_engine):
    billing = build_merchant_month_billing(full_engine)
    credit_notes = pd.read_sql("SELECT invoice_id, status FROM credit_notes", full_engine)
    leakage = build_leakage_table(full_engine, billing, credit_notes)

    row = leakage[leakage["invoice_id"] == "INV_A_FEB"].iloc[0]
    assert row["leakage_type"] == "Underbilling"
    assert row["leakage_amount"] == 50.0
    assert row["status"] == "Recovered"  # FCN1 credit note was Applied


def test_leakage_pricing_mismatch_still_outstanding(full_engine):
    billing = build_merchant_month_billing(full_engine)
    credit_notes = pd.read_sql("SELECT invoice_id, status FROM credit_notes", full_engine)
    leakage = build_leakage_table(full_engine, billing, credit_notes)

    row = leakage[leakage["invoice_id"] == "INV_A_MAR"].iloc[0]
    assert row["leakage_type"] == "Pricing Mismatch"
    assert row["leakage_amount"] == 50.0
    assert row["status"] == "Outstanding"  # no credit note issued


def test_leakage_missing_invoice_amount_matches_expected_revenue(full_engine):
    billing = build_merchant_month_billing(full_engine)
    credit_notes = pd.read_sql("SELECT invoice_id, status FROM credit_notes", full_engine)
    leakage = build_leakage_table(full_engine, billing, credit_notes)

    row = leakage[leakage["leakage_type"] == "Missing Invoice"].iloc[0]
    assert row["merchant_id"] == "MA"
    assert row["leakage_amount"] == 200.0


def test_leakage_ids_are_unique(full_engine):
    billing = build_merchant_month_billing(full_engine)
    credit_notes = pd.read_sql("SELECT invoice_id, status FROM credit_notes", full_engine)
    leakage = build_leakage_table(full_engine, billing, credit_notes)
    assert leakage["leakage_id"].is_unique


# ---------------------------------------------------------------------------
# Revenue realization engine
# ---------------------------------------------------------------------------

def test_revenue_realization_overall_funnel_consistency(full_engine):
    overall = compute_revenue_realization(full_engine, group_by="overall").iloc[0]
    # collected + credited + outstanding must reconstruct billed revenue
    reconstructed = overall["collected_revenue"] + overall["credited_amount"] + overall["outstanding_revenue"]
    assert round(reconstructed, 2) == round(overall["billed_revenue"], 2)


def test_revenue_realization_rate_bounds(full_engine):
    overall = compute_revenue_realization(full_engine, group_by="overall").iloc[0]
    assert 0 <= overall["billing_accuracy_percent"] <= 100


def test_revenue_realization_by_merchant_includes_both_merchants(full_engine):
    by_merchant = compute_revenue_realization(full_engine, group_by="merchant")
    assert set(by_merchant["merchant_id"]) == {"MA", "MB"}
