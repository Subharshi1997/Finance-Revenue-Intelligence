# Finance Operations & Revenue Intelligence Platform

**End-to-End Billing, Accounts Receivable, Collections, Reconciliation & Revenue Leakage Analytics**

> Synthetic dataset created for portfolio and educational purposes. This project simulates a fictional D2C/SaaS checkout & payments infrastructure company ("Chekk"). It is not affiliated with, and does not use data from, any real company — no data from Shopflo, Pine Labs, or any other real business appears anywhere in this repository.

---

## 1. Project Overview

This project simulates the finance operations workflow of a payments-infrastructure
business: merchants transact through the platform, the company charges a
per-transaction fee (plus optional subscription fees), and a Finance Operations
team must bill correctly, collect on time, reconcile every rupee, and catch
revenue leakage before it becomes a write-off.

The platform is built end-to-end: synthetic data generation → validation →
a normalized SQL database → Python finance-calculation engines → a KPI layer
→ Power BI dashboard datasets → Excel operational model → tests → documented
business insights.

## 2. Business Problem

Finance/RevOps teams at checkout and payments platforms are responsible for a
chain of interdependent controls: bill the right amount, collect on time,
reconcile transactions against invoices against payments against bank
settlements, and catch revenue that slips through the cracks (underbilling,
missed invoices, failed payments, unrecovered refund fees). Each of those
controls fails in different, realistic ways — this project builds a system
that detects and quantifies each failure mode, then turns it into a
prioritized action list for the collections/finance team.

## 3. Business Context

**Chekk** provides checkout and payment infrastructure to ~950 D2C merchants
across 8 industries (Fashion, Beauty, Electronics, Home & Living, F&B, Health,
Jewellery, Sports). Revenue comes from a per-transaction platform fee
(1.5%–3.5%, tiered by merchant segment) plus optional monthly subscription
fees on Growth/Enterprise/Custom pricing plans. Merchants are billed monthly
in arrears on 15–60 day payment terms depending on segment.

## 4. Objectives

- Validate billing accuracy: expected revenue (contract rate × GMV) vs. actual billed revenue
- Track revenue realization: gross transactions → billed → collected → outstanding
- Detect and quantify revenue leakage across 6 distinct mechanisms
- Produce an AR aging report and a transparent, explainable collections priority queue
- Calculate DSO at overall, monthly, merchant, and segment grain
- Reconcile the full transaction → invoice → payment → settlement chain
- Deliver management-level KPIs via SQL, Python, Excel, and Power BI
- Translate every finding into a concrete Finance action

## 5. Architecture

```
RAW DATA (synthetic generation)
      |
DATA VALIDATION & CLEANING  (src/data_validation/)
      |
SQL DATABASE  (SQLite, sql/schema.sql)
      |
FINANCE CALCULATION ENGINES  (src/)
      |
      +-- Billing Validation        (src/billing/)
      +-- Revenue Realization       (src/finance_metrics/)
      +-- Reconciliation            (src/reconciliation/)
      +-- Revenue Leakage           (src/revenue_leakage/)
      +-- AR Aging & DSO            (src/collections/)
      +-- Collections Analytics     (src/collections/)
      +-- Payment Behavior          (src/collections/)
      +-- Collection Priority Score (src/collections/)
      |
FINANCE KPI DATASETS  (data/processed/*.csv)
      |
      +-- Power BI Dashboard  (powerbi/)
      +-- Excel Finance Model (excel/)
      +-- SQL Analytics       (sql/analytics_queries.sql — 28 queries)
      |
BUSINESS INSIGHTS & EXECUTIVE SUMMARY  (docs/)
```

See `docs/schema_diagram.md` for the full entity-relationship diagram.

## 6. Dataset Description

24 months (Aug 2024 – Jul 2026) of synthetic data with realistic imperfections
baked in by design (not randomly — see `src/data_generation/`):

| Table | Approx. rows | Purpose |
|---|---:|---|
| merchants | 950 | Merchant profile, segment, pricing plan, contract terms |
| contracts | ~1,150 | Pricing history — some merchants have rate changes over time |
| transactions | ~125,000 | Every checkout event: amount, fee, refunds, discounts, status |
| invoices | ~20,500 | Monthly bills per merchant with expected vs. billed fee |
| payments | ~20,500 | Invoice settlements — full, partial, duplicate, delayed, failed |
| refunds | ~12,700 | Transaction-level refunds |
| credit_notes | ~1,500 | Invoice-level billing corrections |
| collection_activity | 12,300 | Every collector touchpoint (email/phone/reminder/escalation) |
| disputes | ~700 | Merchant-raised invoice disputes |

Deliberate data-quality imperfections: missing values, duplicate transactions,
partial/duplicate/failed payments, incorrect invoices, missing invoices,
missing payments, contract/pricing mismatches, credit notes, discounts, tax
differences, and payment-timing differences — see `docs/data_quality_report.md`
for the full audit of what was found and corrected before loading.

## 7. Data Dictionary

Full column-level definitions for all 9 tables are in `sql/schema.sql` (DDL
with constraints/checks) and were originally specified in the data-generation
modules under `src/data_generation/`. Each table's business meaning is
documented in the module docstring that generates it.

## 8. Finance Methodology

| Engine | Module | What it computes |
|---|---|---|
| Billing validation | `src/billing/billing_engine.py` | Expected vs. billed revenue per merchant-month; classifies Correct / Underbilled / Overbilled / Missing Invoice / Pricing Mismatch |
| Revenue realization | `src/finance_metrics/revenue_realization.py` | GMV → expected → billed → collected → outstanding funnel; realization rate; billing accuracy |
| Reconciliation | `src/reconciliation/reconciliation_engine.py` | Invoice-level and payment-level match status against the transaction/payment/settlement chain |
| Revenue leakage | `src/revenue_leakage/leakage_engine.py` | 6 leakage mechanisms, each scoped to avoid double-counting; recovered/recoverable/outstanding status via credit notes |
| AR aging | `src/collections/ar_aging.py` | Outstanding balance per invoice net of payments and credit notes; 5 aging buckets; combined amount/age risk category |
| DSO | `src/collections/dso.py` | Overall, monthly, and merchant/segment DSO using the standard `AR / Credit Sales × Days` formula |
| Collections analytics | `src/collections/collections_analytics.py` | Collection rate, recovery rate, average collection time, promise-to-pay, channel/segment effectiveness |
| Payment behavior | `src/collections/payment_behavior.py` | Per-merchant delay stats and payer segmentation (Excellent/Good/Moderate/High-risk) |
| Collection priority | `src/collections/collection_priority.py` | Transparent weighted score (40% balance risk / 30% days overdue / 20% payer history / 10% customer risk) driving a ranked action queue |

Every engine module's docstring documents its classification logic and the
reasoning behind edge-case decisions (e.g., why "Pricing Mismatch" is anchored
to real contract transitions rather than reverse-engineered from the
billed/expected ratio).

## 9. KPI Definitions

See **`docs/kpi_definitions.md`** for the full catalogue — every KPI's
formula, business meaning, interpretation, and why Finance cares about it.

## 10. SQL Analysis

`sql/analytics_queries.sql` — **28 analytical queries** covering revenue
trends, AR aging, DSO, collections, billing errors, reconciliation, duplicate
payments, missing invoices/payments, customer segmentation, merchant
profitability, collection priority, variance analysis, revenue concentration,
payment delay distribution, high-risk accounts, and dispute/refund analysis.
Run against `data/finance_ops.db` (build it first — see Installation below).

## 11. Python Analysis

```
src/
├── data_generation/     synthetic data generators (Phase 3)
├── data_validation/     data-quality checks and cleaning (Phase 4)
├── billing/              billing validation engine (Phase 6)
├── finance_metrics/      revenue realization engine (Phase 6)
├── reconciliation/       transaction-invoice-payment reconciliation (Phase 7)
├── revenue_leakage/       revenue leakage detection (Phase 8)
├── collections/           AR aging, DSO, collections analytics, payment
│                          behavior, collection priority scoring (Phase 9)
└── utils/                 shared config, DB engine helper
```

Every phase has a `run_*.py` entry point that writes its outputs to
`data/processed/`. Run them in dependency order (see Installation).

## 12. Reconciliation Methodology

Reconciliation runs at two grains:
- **Invoice-level**: `MATCHED` / `PARTIAL` / `MISSING_PAYMENT` / `DUPLICATE` /
  `AMOUNT_MISMATCH` / `TIMING_MISMATCH` / `VOID`, checked in priority order
  since one invoice can technically trip more than one condition.
- **Payment-level**: `MATCHED` / `ORPHAN` (no invoice_id) / `UNMATCHED`
  (invoice_id doesn't exist) / `DUPLICATE` / `NOT_APPLICABLE_<STATUS>` (failed/pending payments).

Merchant-months with successful transactions but no invoice at all are
surfaced separately as `MISSING_INVOICE` since there's no invoice_id to
anchor them to the invoice-level table.

## 13. Revenue Leakage Methodology

Six non-overlapping mechanisms, each scoped to avoid double-counting money
already caught by another engine:

1. **Underbilling** — invoice billed less than the correct contract rate
2. **Pricing Mismatch** — same, but the invoice falls near a real contract rate change (likely stale-rate billing, not a calculation error)
3. **Missing Invoice** — merchant transacted, no invoice was ever cut
4. **Refund Fee Retention** *(advisory, not counted in the leakage total)* — fee revenue kept on refunded transactions with no offsetting credit note; flagged for policy review, not asserted as a confirmed loss
5. **Rate Discrepancy** *(advisory)* — checkout applied the wrong rate but invoicing corrected it before billing; a caught near-miss, not realized leakage
6. **Failed Payment** — invoice has only failed payment attempts and is now overdue with zero successful collection

Each leakage row carries a `status` (Recovered / Recoverable / Outstanding)
driven by whether a credit note was issued and applied.

## 14. AR Aging Methodology

`outstanding_amount = total_invoice_amount − payments (Success only) − credit_notes (Issued/Applied)`,
bucketed into Current / 1–30 / 31–60 / 61–90 / 90+ days overdue. A combined
**risk category** (Low/Medium/High/Critical) blends balance size and days
overdue so a small stale balance and a large fresh one don't land in the same
tier.

## 15. Collection Priority Methodology

A transparent, explainable 0–100 score per overdue invoice:
`40% outstanding-amount risk + 30% days-overdue risk + 20% payer-history risk + 10% customer-status risk`,
each component normalized to 0–100 before weighting. Produces a ranked queue
with a tier (Critical/High/Medium/Low) and a recommended action per tier —
see `src/collections/collection_priority.py` for the full weighting rationale.

## 16. Power BI Dashboard

Dashboard-ready datasets and the full dataset/measure/page specification are
in `powerbi/` — see `powerbi/dashboard_spec.md`. (Note: this environment does
not have Power BI Desktop installed, so the `.pbix` file itself cannot be
built here; the spec is written so it can be assembled directly from the
`data/processed/` CSVs.)

## 17. Excel Finance Model

`excel/finance_ops_model.xlsx` — a 9-sheet operational workbook (raw
transactions, invoices, payments, invoice validation, AR aging, collections,
revenue reconciliation, monthly MIS, KPI dashboard) built with XLOOKUP,
SUMIFS, COUNTIFS, pivot tables, and conditional formatting. See
`excel/README.md` for a sheet-by-sheet formula guide.

## 18. Key Findings

Full write-up with quantified financial impact: **`docs/business_insights.md`**
(9 insights, each with Observation / Financial Impact / Likely Cause /
Recommended Action) and **`docs/executive_summary.md`** (CFO-level one-pager).

Headlines: 80.9% of open AR is 90+ days overdue; realized revenue leakage
totals ₹7.56 lakh with Failed Payment now the largest category; headline DSO
(106.6 days) is inflated by aged back-book AR while monthly DSO runs a
healthy 4.4–5.9 days; and reconciliation surfaces a payment-intake control
gap (568 duplicate + 197 orphaned payments) that overstates realized revenue.

## 19. Business Recommendations

See the "Summary: Where should Finance focus first?" table at the end of
`docs/business_insights.md` — duplicate/orphaned payment cleanup, a dedicated
Failed Payment recovery track, churned-merchant AR escalation, a Missing
Invoice month-end gate, and collection-channel reallocation, in priority order.

## 20. Testing

`pytest` suite (35 tests, `tests/`) against hand-built fixture databases
covering deliberate edge cases: zero-amount invoices, full/partial/duplicate/
overpaid payments, credit-note offsets, missing invoices/payments, same-day
and early payments, extreme overdue (400+ days), every billing-status branch,
every reconciliation status at invoice and payment level, and leakage
recovery-status logic.

```bash
python -m pytest tests/ -v
```

## 21. Limitations

- Data is fully synthetic; correlations are designed to be realistic but are
  not fitted to real transaction data.
- Power BI `.pbix` and Excel `.xlsx` binaries are described/specified here
  rather than screenshotted, since this environment has no licensed Power BI
  Desktop or Excel installation to render them visually.
- The optional payment-delay ML model (Step 26 in the original spec) is not
  implemented — finance/accounting logic was prioritized over ML per the
  project's own design principle.
- DSO's trailing-90-day credit-sales window can occasionally divide by a
  small number in low-volume slices (e.g. a single merchant with no recent
  invoices); this is handled by returning `None` rather than raising.

## 22. Future Improvements

- Wire the duplicate/orphaned-payment findings (insight #7) into an automated
  intake-time validation gate rather than a post-hoc reconciliation report.
- Add the optional payment-delay-risk ML model (Logistic Regression / Random
  Forest / XGBoost comparison) as a genuinely additive layer once the core
  finance logic is stable.
- Build a Streamlit front-end over the collection priority queue for a live
  operational view instead of a static CSV.

## 23. Installation & Reproduction

```bash
pip install -r requirements.txt

# 1. Generate synthetic data
python -m src.data_generation.run_generation

# 2. Validate & clean
python -m src.data_validation.run_validation

# 3. Build the SQL database
python -m src.utils.db

# 4. Run the finance engines, in order
python -m src.billing.run_billing_engine
python -m src.finance_metrics.run_revenue_realization
python -m src.reconciliation.run_reconciliation
python -m src.revenue_leakage.run_leakage_engine
python -m src.collections.run_collections

# 5. Run tests
python -m pytest tests/ -v
```

All generated data lives in `data/processed/` (git-ignored — regenerate via
the commands above rather than committing large CSVs).

---

## Additional Documentation

- `docs/kpi_definitions.md` — every KPI's formula and business meaning
- `docs/business_insights.md` — quantified findings and recommended actions
- `docs/executive_summary.md` — CFO-level one-pager
- `docs/data_quality_report.md` — pre-cleaning data quality audit
- `docs/schema_diagram.md` — entity-relationship diagram
- `INTERVIEW_PREPARATION.md` — 30+ likely interview questions with model answers
- `docs/presentation_outline.md` — 15-slide interview presentation outline
