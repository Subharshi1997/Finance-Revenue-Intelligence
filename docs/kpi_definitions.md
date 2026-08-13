# KPI Definitions

Every KPI used across the SQL queries, Python engines, Excel model, and Power
BI dashboard, with its formula, business meaning, how to interpret it, and
why Finance tracks it. Source module is noted where the KPI is computed in code.

---

## Revenue KPIs

### Gross Transaction Value (GTV)
**Formula:** `SUM(transaction_amount)` for successful transactions
**Meaning:** Total value of goods/services processed through the platform.
**Interpretation:** The base the platform's take-rate is applied to; growth
here doesn't automatically mean revenue growth if take-rate or billing
accuracy slips.
**Why Finance cares:** It's the denominator for every fee/take-rate ratio and
the leading indicator of platform usage.

### Expected Revenue
**Formula:** `SUM(transaction_amount × contract_fee_percent)` plus applicable subscription/fixed fees
**Meaning:** What the company is contractually owed for the period.
**Interpretation:** The correctness benchmark every invoice is measured against.
**Why Finance cares:** Without it, "billed revenue" has no ground truth to validate against.

### Billed Revenue
**Formula:** `SUM(invoices.billed_fee)`
**Meaning:** What was actually invoiced to merchants.
**Interpretation:** Gap vs. Expected Revenue = billing errors (over/underbilling).
**Why Finance cares:** This is the number that flows into AR and, eventually, cash.

### Realized / Collected Revenue
**Formula:** `SUM(payments.payment_amount WHERE payment_status = 'Success')`
**Meaning:** Cash actually received against billed invoices.
**Interpretation:** The true top-line cash contribution, as opposed to accrued billing.
**Why Finance cares:** Billed revenue that never converts to cash is not real revenue.

### Revenue Realization Rate
**Formula:** `Collected Revenue / Billed Revenue × 100`
**Module:** `src/finance_metrics/revenue_realization.py`
**Meaning:** Of what was billed, how much has actually been collected.
**Interpretation:** Below 100% is normal for open AR (money still on its way);
persistently below 90% signals a collections problem; **above 100% signals a
control gap** (duplicate/overpaid/misapplied cash), not over-performance.
**Why Finance cares:** It's the single number that separates "billed" (an
accounting event) from "cash" (what actually funds the business).

### Revenue Growth %
**Formula:** `(Current Period Revenue − Prior Period Revenue) / Prior Period Revenue × 100`
**Meaning:** Period-over-period change in billed revenue.
**Interpretation:** Must be read alongside Realization Rate — growing billed
revenue with a falling realization rate means growth isn't converting to cash.
**Why Finance cares:** Standard growth tracking, but only meaningful in
context of collections health.

### Revenue Leakage
**Formula:** `SUM(leakage_amount)` across all realized leakage types (excludes advisory-only types)
**Module:** `src/revenue_leakage/leakage_engine.py`
**Meaning:** Revenue the company was owed but did not bill or collect, by mechanism.
**Interpretation:** Split by status (Recovered/Recoverable/Outstanding) to see
how much is a solved problem vs. still open.
**Why Finance cares:** This is money Finance can plausibly still recover — it's
the actionable subset of the revenue gap, distinct from GMV that never happened.

---

## AR KPIs

### Total Accounts Receivable (AR)
**Formula:** `SUM(total_invoice_amount − payments − credit_notes)` for all invoices with a positive balance
**Module:** `src/collections/ar_aging.py`
**Meaning:** Total open balance owed by merchants right now.
**Interpretation:** A balance-sheet snapshot, not a flow — must be read
alongside aging composition (see below).
**Why Finance cares:** This is cash not yet converted; its size and age
determine collections workload and bad-debt risk.

### AR Aging Buckets
**Formula:** Outstanding balance grouped by days overdue: Current, 1–30, 31–60, 61–90, 90+
**Meaning:** How "fresh" vs. "stale" the outstanding balance is.
**Interpretation:** A back-weighted distribution (most AR in 90+) signals
either weak early-stage collections or a build-up of effectively uncollectable
balances that should move to a different recovery track (see business_insights.md #1).
**Why Finance cares:** Aging composition, not just the total, tells you
whether AR is a healthy pipeline or a growing problem.

### Current AR / Overdue AR / 30+ / 60+ / 90+ AR
**Formula:** Sum of `outstanding_amount` within each aging bucket (or cumulative, e.g. 30+ = 1–30 + 31–60 + 61–90 + 90+)
**Meaning:** Segmented views of the AR total for risk-tiered reporting.
**Why Finance cares:** Different overdue tiers warrant different collection
intensity and different provisioning treatment for bad debt.

### Days Sales Outstanding (DSO)
**Formula:** `(Total AR / Total Credit Sales in period) × Number of Days`
**Module:** `src/collections/dso.py`
**Meaning:** Average number of days it takes to collect cash after billing.
**Interpretation:** A DSO of 45 against 30-day terms means the business is
effectively financing merchants for two extra weeks. **Caution:** if Total AR
includes a large aged back-book while the sales window is short (e.g.
trailing 90 days), DSO inflates independent of current collection
performance — always cross-check against monthly DSO.
**Why Finance cares:** DSO is the standard cross-industry benchmark for
collections efficiency and working-capital tie-up.

---

## Collections KPIs

### Collection Rate
**Formula:** `Cash Collected in Period / Revenue Billed in Period × 100`
**Module:** `src/collections/collections_analytics.py`
**Meaning:** Of what was billed in a period, how much cash came in during
that same window.
**Interpretation:** A period-flow view (contrast with Realization Rate, which
is cohort-based and tracks an invoice regardless of when it was billed).
**Why Finance cares:** The cleanest single number for "are we converting
current billing into current cash."

### Recovery Rate
**Formula:** `Amount Collected on Chased Invoices / Amount Owed at First Contact × 100`
**Meaning:** Of invoices that required active collector intervention, what
share of the balance owed at first contact was ultimately recovered.
**Interpretation:** Low recovery rate (e.g. under 20%) signals that once an
invoice needs a human collector, the odds of full recovery are poor — a cue
to intervene earlier, before an invoice needs chasing at all.
**Why Finance cares:** Measures the actual effectiveness of the collections
function, isolated from invoices that were always going to pay on their own.

### Average / Median Payment (Collection) Delay
**Formula:** `Last Payment Date − Invoice Due Date`, per paid invoice
**Meaning:** How many days late (or early, if negative) a merchant pays on average.
**Interpretation:** Negative = pays early; near-zero = on-time; large positive = chronic late payer.
**Why Finance cares:** Feeds directly into payer segmentation and the
collection priority score.

### Promise-to-Pay Rate / Fulfillment Rate
**Formula:** `Promises Made / Total Collection Activities`; `Promises Kept / Promises Made × 100`
**Meaning:** How often a collector contact results in a payment promise, and how often that promise is actually honored.
**Interpretation:** A high promise rate with low fulfillment means promises
are being logged as a soft close rather than a real commitment — treat as an
unreliable forecasting signal until fulfillment improves.
**Why Finance cares:** Prevents "promise to pay" from being mistaken for
collected cash in short-term forecasting.

### Collection Effectiveness (by Channel / Segment)
**Formula:** `Activities resulting in "Payment Received" / Total Activities × 100`, grouped by contact_channel or merchant_segment
**Meaning:** Which outreach channel or customer segment actually converts contact into payment.
**Why Finance cares:** Directs collector effort toward what statistically works, not just what's cheapest to execute (e.g. mass email).

---

## Billing KPIs

### Billing Accuracy
**Formula:** `Correctly Billed Amount / Expected Billing × 100`
**Module:** `src/finance_metrics/revenue_realization.py`
**Meaning:** Share of expected revenue that was billed at the exactly correct amount.
**Interpretation:** Below ~95% suggests a systematic issue (stale rate
lookups, manual override errors) rather than isolated mistakes.
**Why Finance cares:** Billing errors are the root cause of most downstream
leakage and AR disputes — this is a leading, not lagging, indicator.

### Invoice Count / Billing Errors
**Formula:** Count of invoices; count where `billing_status != 'Correct'`
**Why Finance cares:** Raw volume context for the accuracy percentage —
1% error on 100 invoices and 1% error on 20,000 invoices are operationally
very different problems.

### Underbilling / Overbilling
**Formula:** `SUM(billed_fee − expected_fee)` split by sign, for non-Correct, non-transition invoices
**Module:** `src/billing/billing_engine.py`
**Meaning:** Systematic direction of billing errors.
**Interpretation:** Underbilling is silent revenue loss (never triggers a
merchant complaint); overbilling is a compliance/trust risk (merchants notice
and dispute). Both need different remediation urgency.
**Why Finance cares:** Directs whether the fix is revenue-protective or
relationship-protective.

---

## Reconciliation KPIs

### Reconciliation Rate
**Formula:** `MATCHED invoices / Total invoices (incl. missing-invoice merchant-months) × 100`
**Module:** `src/reconciliation/reconciliation_engine.py`
**Meaning:** Share of the full transaction-to-cash chain that ties out cleanly with no exceptions.
**Interpretation:** Anything meaningfully below 100% represents open control
exceptions requiring manual review before revenue can be trusted at face value.
**Why Finance cares:** This is the audit-readiness number — the foundation
every other revenue KPI in this document assumes is clean.

### Unmatched Transactions / Amount Mismatches / Duplicate Payments
**Formula:** Counts of `UNMATCHED`, `AMOUNT_MISMATCH`, and `DUPLICATE` reconciliation statuses
**Meaning:** Specific, actionable exception categories within the reconciliation output.
**Why Finance cares:** Each maps to a distinct root-cause fix (e.g. duplicate
payments need an intake-time dedup gate, not a collections response).

### Variance %
**Formula:** `(Actual − Expected) / Expected × 100`, applied to any expected-vs-actual comparison (billing, month-over-month, budget-vs-actual)
**Meaning:** Standardized way to express any financial gap as a comparable percentage.
**Why Finance cares:** Lets Finance set a single materiality threshold (e.g.
"flag anything over 5%") across otherwise very differently-sized comparisons.
