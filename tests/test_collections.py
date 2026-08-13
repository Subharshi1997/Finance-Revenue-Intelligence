"""Tests for the Phase 9 collections engines: AR aging, DSO, collections
analytics, payment behavior, and collection priority scoring.

Uses the fixture DB from conftest.py which deliberately includes edge cases:
zero-amount invoice, full/partial/duplicate/failed payments, a credit note
that fully offsets an invoice, a same-day payment, an early payment, a
missing payment, and an invoice overdue by more than a year.
"""
from __future__ import annotations

import math

from src.collections.ar_aging import aging_summary, build_ar_aging
from src.collections.collection_priority import build_collection_queue
from src.collections.collections_analytics import (
    average_collection_time,
    channel_effectiveness,
    promise_to_pay,
    recovery_rate,
)
from src.collections.dso import dso_by, monthly_dso, overall_dso
from src.collections.payment_behavior import payer_segment_summary, payment_behavior_by_merchant

AS_OF = "2026-06-01"


# ---------------------------------------------------------------------------
# AR aging
# ---------------------------------------------------------------------------

def test_ar_aging_excludes_fully_settled_and_zero_invoices(engine):
    ar = build_ar_aging(engine, as_of_date=AS_OF)
    ids = set(ar["invoice_id"])
    # INV1 fully paid, INV6 fully offset by credit note, INV7 zero-amount,
    # INV4 overpaid (negative outstanding) - none should appear.
    assert ids == {"INV2", "INV3", "INV5"}


def test_ar_aging_nets_credit_notes(engine):
    ar = build_ar_aging(engine, as_of_date=AS_OF)
    inv2 = ar[ar["invoice_id"] == "INV2"].iloc[0]
    assert inv2["outstanding_amount"] == 1500.0  # 2000 - 500 paid


def test_ar_aging_extremely_overdue_invoice_buckets_correctly(engine):
    ar = build_ar_aging(engine, as_of_date=AS_OF)
    inv5 = ar[ar["invoice_id"] == "INV5"].iloc[0]
    assert inv5["days_overdue"] > 365
    assert inv5["aging_bucket"] == "90+ days"
    assert inv5["risk_category"] == "High"


def test_aging_summary_percentages_sum_to_100(engine):
    ar = build_ar_aging(engine, as_of_date=AS_OF)
    summary = aging_summary(ar)
    total_pct = summary["percent_of_total_ar"].sum()
    assert math.isclose(total_pct, 100.0, abs_tol=0.05)


# ---------------------------------------------------------------------------
# DSO
# ---------------------------------------------------------------------------

def test_overall_dso_handles_zero_credit_sales(engine):
    # No invoices fall inside the trailing 90-day window from AS_OF, so
    # credit_sales is 0 - DSO must degrade to None rather than raising.
    result = overall_dso(engine, as_of_date=AS_OF)
    assert result["dso_days"] is None
    # 1500 (INV2) + 500 (INV3) + 5000 (INV5) - 300 (INV4 overpaid by duplicate payment)
    assert result["total_ar"] == 6700.0


def test_overall_dso_computes_when_sales_present(engine):
    result = overall_dso(engine, as_of_date="2026-02-15", window_days=90)
    assert result["dso_days"] is not None
    assert result["dso_days"] > 0


def test_monthly_dso_runs_without_error(engine):
    monthly = monthly_dso(engine, as_of_date=AS_OF)
    assert len(monthly) > 0
    assert "dso_days" in monthly.columns


def test_dso_by_merchant_segment(engine):
    by_segment = dso_by(engine, "merchant_segment", as_of_date="2026-02-15")
    assert "dso_days" in by_segment.columns
    assert set(by_segment["merchant_segment"]).issubset({"Enterprise", "SMB", "Long-tail"})


# ---------------------------------------------------------------------------
# Collections analytics
# ---------------------------------------------------------------------------

def test_average_collection_time_same_day_and_early_payment(engine):
    result = average_collection_time(engine)
    # INV1 paid same day as due date (delay 0), INV4 paid before due date (negative delay)
    assert result["paid_invoices_measured"] >= 2
    assert result["avg_collection_days"] <= 0


def test_recovery_rate_only_counts_chased_invoices(engine):
    result = recovery_rate(engine)
    # Only INV2, INV3, INV4 have collection_activity rows
    assert result["invoices_chased"] == 3
    assert 0 <= result["recovery_rate_percent"] <= 100


def test_promise_to_pay_fulfillment_detects_kept_promise(engine):
    result = promise_to_pay(engine)
    # C2 promises payment on INV2 by 2026-02-12; actual payment P2 landed 2026-02-10 (kept)
    assert result["promises_made"] == 1
    assert result["promises_fulfilled"] == 1
    assert result["promise_fulfillment_rate_percent"] == 100.0


def test_channel_effectiveness_reflects_outcomes(engine):
    result = channel_effectiveness(engine)
    whatsapp = result[result["contact_channel"] == "WhatsApp"].iloc[0]
    assert whatsapp["payments_received"] == 1
    assert whatsapp["success_rate_percent"] == 100.0


# ---------------------------------------------------------------------------
# Payment behavior
# ---------------------------------------------------------------------------

def test_payment_behavior_flags_early_and_ontime_payers(engine):
    behavior = payment_behavior_by_merchant(engine, as_of_date=AS_OF)
    m1 = behavior[behavior["merchant_id"] == "M1"].iloc[0]
    # M1's only paid invoice (INV1) was paid exactly on the due date.
    assert m1["avg_payment_delay_days"] == 0.0
    assert m1["payer_segment"] == "Excellent"


def test_payment_behavior_merchant_with_no_paid_invoices(engine):
    behavior = payment_behavior_by_merchant(engine, as_of_date=AS_OF)
    m3 = behavior[behavior["merchant_id"] == "M3"].iloc[0]
    assert math.isnan(m3["avg_payment_delay_days"])
    assert m3["payer_segment"] == "Insufficient Data"


def test_payer_segment_summary_covers_all_segments_present(engine):
    behavior = payment_behavior_by_merchant(engine, as_of_date=AS_OF)
    summary = payer_segment_summary(behavior)
    assert set(summary["payer_segment"]).issubset({"Excellent", "Good", "Moderate", "High-risk", "Insufficient Data"})
    assert summary["merchant_count"].sum() == len(behavior)


# ---------------------------------------------------------------------------
# Collection priority
# ---------------------------------------------------------------------------

def test_collection_queue_only_includes_overdue_invoices(engine):
    queue = build_collection_queue(engine, as_of_date=AS_OF)
    assert (queue["days_overdue"] > 0).all()
    assert set(queue["invoice_id"]) == {"INV2", "INV3", "INV5"}


def test_collection_queue_ranks_by_score_descending(engine):
    queue = build_collection_queue(engine, as_of_date=AS_OF)
    scores = queue["priority_score"].tolist()
    assert scores == sorted(scores, reverse=True)
    assert queue["priority_rank"].tolist() == list(range(1, len(queue) + 1))


def test_collection_queue_extreme_overdue_churned_merchant_ranks_critical(engine):
    queue = build_collection_queue(engine, as_of_date=AS_OF)
    inv5 = queue[queue["invoice_id"] == "INV5"].iloc[0]
    # 485+ days overdue, largest balance, churned merchant -> should be top priority
    assert inv5["priority_rank"] == 1
    assert inv5["priority_tier"] == "Critical"


def test_priority_score_bounded_0_to_100(engine):
    queue = build_collection_queue(engine, as_of_date=AS_OF)
    assert (queue["priority_score"] >= 0).all()
    assert (queue["priority_score"] <= 100).all()
