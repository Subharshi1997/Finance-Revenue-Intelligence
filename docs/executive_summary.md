# Executive Summary — Finance Operations & Revenue Intelligence

**Chekk (synthetic D2C checkout/payments platform) · Prepared for: CFO / Finance Leadership**
**Period:** Trailing 90 days as of 2026-08-13 · **History analyzed:** Aug 2024 – Jul 2026

*Synthetic dataset created for portfolio and educational purposes. All figures in INR.*

---

### Revenue Performance
Billed revenue over the trailing 90 days was ₹24.14 lakh. All-time billed
revenue across 24 months is ₹15.87 crore against ₹6.69 crore in gross
transaction value processed. Billing accuracy — invoices billed at the
correct expected rate — stands at **91.4%**, meaning roughly 1 in 11 invoices
requires correction.

### Collections Performance
Trailing-90-day collection rate is **92.1%** (₹22.23 lakh collected against
₹24.14 lakh billed). Average time to collect a paid invoice is 10.1 days past
due date (5-day median), which is healthy. However, **recovery rate on
actively-chased overdue invoices is only 16.3%** — once an invoice requires
collector intervention, the odds of recovering it drop sharply, and
promise-to-pay commitments are honored only 13.8% of the time.

### Accounts Receivable Position
Total open AR is **₹28.92 lakh**. The composition is the single biggest
red flag in this report: **80.9% of that balance (₹23.40 lakh) is 90+ days
overdue.** Current and 1–30 day balances together make up only 10.4% of the
book — the AR portfolio is heavily back-weighted toward aged, hard-to-collect
balances rather than fresh billing.

### Days Sales Outstanding (DSO)
Headline DSO is **106.6 days**, but this figure is distorted by the aged
back-book described above — it measures all historical AR against only 90
days of recent sales. **Monthly DSO, which isolates current-period
performance, has run 4.4–5.9 days for the last six months** — current
collections execution is materially healthier than the headline number
suggests. Recommendation: report both metrics; do not manage the team to the
blended headline figure.

### Revenue Leakage
Realized revenue leakage totals **₹7.56 lakh**, led by Failed Payment
(₹3.26 lakh, now the largest category), Missing Invoice (₹2.51 lakh — 100%
unbilled merchant-months), Underbilling (₹1.66 lakh), and Pricing Mismatch
tied to contract rate transitions (₹0.14 lakh). **81% of total leakage
(₹6.12 lakh) remains outstanding with no recovery action yet.**

### Billing Accuracy
91.4% of invoices bill correctly. The remaining errors split roughly
two-thirds Underbilling/Pricing Mismatch (high frequency, low dollar value —
suggests a systematic rate-lookup issue around contract transitions) and
one-third Missing Invoice (low frequency, 100% severity per event).

### Major Risks
1. **Control gap in payment intake:** all-time realization rate exceeds
   100% (112.1%) because duplicate and orphaned payments are being posted
   without a matching gate — 568 duplicate payments and 197 orphaned
   payments are currently unresolved in the reconciliation output. This
   overstates realized revenue on paper.
2. **Aged AR concentration:** ₹23.4 lakh sitting past 90 days, disproportionately
   on churned merchants where collection leverage is weakest.
3. **Low collector effectiveness on the highest-volume channel:** Email
   carries 58% of collection activity but converts at only 2.1%, versus
   8.9% on WhatsApp.

### Recommended Actions (in priority order)
1. Close the payment-intake control gap: block duplicate postings, build a
   manual-match queue for orphaned payments, and re-state realization rate
   net of unresolved duplicates.
2. Stand up a dedicated Failed Payment recovery track (auto-retry + dedicated
   collector queue) — it's now the largest leakage category.
3. Escalate the 90+ day churned-merchant AR book to legal/agency review
   rather than routing it through the standard reminder sequence.
4. Add a contract-rate freshness check to invoice generation to eliminate
   Pricing Mismatch errors at the transition window.
5. Rebalance collection channel mix toward WhatsApp/Phone for
   overdue-45-days-plus accounts.

---
*Full methodology, KPI definitions, and reproducible queries are documented in
`docs/business_insights.md`, `docs/kpi_definitions.md`, and `sql/analytics_queries.sql`.*
