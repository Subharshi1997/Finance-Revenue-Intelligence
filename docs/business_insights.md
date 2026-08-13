# Business Insights Report

**Finance Operations & Revenue Intelligence Platform — Chekk (synthetic company)**
**As of:** 2026-08-13 · **Data window:** 2024-08-01 to 2026-07-31 (24 months)

Every insight below is generated directly from `data/processed/*.csv` (outputs of
the billing, reconciliation, revenue leakage, AR aging, DSO, and collections
engines in `src/`). Figures are in INR. All data is synthetic — see
`docs/README` for the fictional-company disclosure.

Each insight follows: **Observation → Financial Impact → Likely Cause → Recommended Action.**

---

## 1. AR is dangerously back-weighted into the 90+ day bucket

**Observation:** Of ₹28.92 lakh in total open AR, ₹23.40 lakh (80.9%) sits in the
90+ day aging bucket, spread across 3,191 invoices. Current and 1–30 day balances
together are only 10.4% of the book.

**Financial Impact:** ₹23.4 lakh of cash is effectively stuck, most of it long
past the point where standard reminder sequences work. This distorts DSO (see
insight 4) and represents the largest single pool of at-risk revenue on the
balance sheet.

**Likely Cause:** A subset of invoices — disproportionately concentrated in
churned or long-inactive merchants — never received escalation-level follow-up
before crossing 90 days, and once a merchant churns, collection leverage drops
sharply (`collection_priority_queue.csv` ranks two churned-merchant invoices as
`Critical`, both 90+ days overdue, ahead of every current-book account).

**Recommended Action:** Introduce a hard escalation trigger at day 45 (before
the invoice crosses 60), with automatic hand-off from email/reminder to phone +
account-manager involvement. For anything already past 90 days on a churned
account, route directly to legal/collections-agency review rather than the
standard reminder queue — the priority engine already flags these as top rank.

---

## 2. Failed payments are now the single largest leakage category

**Observation:** Realized revenue leakage totals **₹7.56 lakh** across four
mechanisms. Failed Payment leads at ₹3.26 lakh (357 invoices), ahead of Missing
Invoice (₹2.51 lakh, 340 invoices), Underbilling (₹1.66 lakh, 1,076 invoices),
and Pricing Mismatch (₹0.14 lakh, 99 invoices).

**Financial Impact:** ₹6.12 lakh of the ₹7.56 lakh total (81%) is still
**Outstanding** — no credit note or recovery action has closed it out. Only
₹0.68 lakh has been formally Recovered.

**Likely Cause:** Failed Payment leakage is invoices where every payment
attempt failed and the invoice is now overdue with zero successful collection
— these are functionally abandoned invoices sitting in the AR book without a
dedicated recovery workflow, distinct from invoices that were never billed
(Missing Invoice) or billed wrong (Underbilling/Pricing Mismatch).

**Recommended Action:** Failed Payment leakage needs its own recovery track —
automatic retry on an alternate payment method plus a dedicated collector
queue — rather than being treated identically to a routine overdue invoice.
Given it's now the largest leakage bucket, this should be the first fix ahead
of billing-accuracy work.

---

## 3. Underbilling is high-frequency but low-severity; Missing Invoice is the opposite

**Observation:** Underbilling accounts for 1,076 of 1,671 non-Correct billing
events (64%) but only ₹1.66 lakh of leakage — an average of ₹154 per invoice.
Missing Invoice is far rarer (340 events) but averages ₹738 per event and
represents merchant-months where a merchant transacted and **no invoice was
ever generated.**

**Financial Impact:** Underbilling is a high-volume, low-dollar control gap
(likely systematic, e.g. a rate-lookup bug); Missing Invoice is low-volume but
100% unbilled — every rupee of expected revenue on those merchant-months is
currently zero-billed.

**Likely Cause:** 156 of the underbilling-shaped errors are classified
separately as **Pricing Mismatch** — they cluster right around real contract
rate changes, meaning invoices are sometimes cut on a stale rate in the
transition window rather than a random calculation error. Missing Invoice
months correlate with billing-cycle gaps rather than contract activity.

**Recommended Action:** For Underbilling/Pricing Mismatch: add a contract-rate
freshness check to the invoice generation job so it always pulls the rate
effective as of the billing period, not a cached value. For Missing Invoice:
add a monthly reconciliation check (already implemented in
`reconcile_missing_invoices()`) as a hard gate before month-end close — no
month should close with un-invoiced merchant-months outstanding.

---

## 4. Headline DSO (106.6 days) is inflated by aged back-book AR, not current collection performance

**Observation:** Overall DSO (total AR ÷ trailing 90-day billed revenue × 90)
is 106.6 days. But **monthly DSO** — which measures AR generated and collected
within each individual month — has run 4.4 to 5.9 days for the last six
months. Segment-level DSO is also uneven: Mid-Market sits at 126.8 days vs.
Enterprise at 76.9 days.

**Financial Impact:** The 106.6-day headline number overstates how badly
*current* collections are performing, because it divides all historically
accumulated AR (including insight #1's 90+ day back-book) by only 90 days of
recent sales. Left unadjusted, this KPI would misdirect Finance toward
"fix collections" when the real issue is "clear the back-book."

**Likely Cause:** Total AR is a stock measure across the full 24-month
history; trailing credit sales is a 90-day flow measure. When a large share of
stock is old and unresolved (insight #1), the ratio inflates independent of
how well *new* invoices are being collected.

**Recommended Action:** Report both metrics side by side on the executive
dashboard — headline DSO for balance-sheet health, monthly DSO for
"are we currently collecting well" — and set the collections team's
performance target on monthly DSO, not the blended headline figure. Separately
track back-book AR (90+ days) as a distinct write-off/recovery workstream with
its own aging-based targets.

---

## 5. Collection channels are working, but not the ones getting the most volume

**Observation:** WhatsApp converts at 8.88% success (payments received per
activity), more than 1.6x Phone (5.35%) and over 4x Email (2.13%) — yet Email
receives 58% of all collection activity volume (7,126 of 12,300 activities)
while WhatsApp gets only 6.7% (822 activities).

**Financial Impact:** Collectors are spending most of their effort on the
lowest-converting channel. Reallocating volume toward WhatsApp and Phone,
even partially, should lift overall recovery without adding headcount.

**Likely Cause:** Email is the cheapest, most automatable channel, so it's
the default first-touch — but this dataset shows it is also the weakest
closer, likely because low-priority automated reminders get filtered/ignored
long before a human channel would.

**Recommended Action:** Restructure the sequence so WhatsApp/Phone enter
sooner — e.g., Email as day-1 auto-reminder, escalate to WhatsApp by day 7 if
unresolved, rather than the current pattern where Email dominates the full
overdue lifecycle. Segment-wise, Enterprise accounts convert best (5.71%) —
prioritize live-channel effort there first.

---

## 6. Promise-to-pay is common but rarely honored

**Observation:** 28.2% of all collection activities result in a "Promise to
Pay" outcome (3,469 of 12,300), but only **13.75%** of those promises are
actually fulfilled by the promised date (477 of 3,469).

**Financial Impact:** Roughly 2,992 broken promises represent both wasted
collector follow-up time and a false sense of expected near-term cash that
doesn't materialize — this likely distorts short-term cash forecasting if
promise-to-pay is used as a leading indicator anywhere downstream.

**Likely Cause:** Promises are being logged as a soft outcome to close out a
contact attempt rather than backed by a real commitment mechanism (deposit,
signed schedule, etc.) — there's no visible cost to a merchant for missing a
promised date.

**Recommended Action:** Stop treating "Promise to Pay" as a resolved outcome
in collector scorecards. Track promise-fulfillment rate as its own KPI, and
for merchants with 2+ broken promises, skip the promise step entirely and
escalate straight to firmer terms (partial upfront, revised payment plan).

---

## 7. Realization rate exceeding 100% flags a reconciliation control gap, not strong performance

**Observation:** All-time cumulative realization rate (collected ÷ billed) is
**112.09%** — collected revenue (₹1.78 crore) exceeds billed revenue
(₹1.59 crore). Outstanding revenue is *negative* (-₹21.3 lakh). Meanwhile,
reconciliation flags 568 payments as `DUPLICATE` and 284 invoices as
`DUPLICATE` status, plus 197 `ORPHAN` payments (no invoice_id at all).

**Financial Impact:** A realization rate above 100% is not a sign of
over-performance — it means more cash has been recorded against invoices than
those invoices actually billed, which is only possible through duplicate
payments, orphaned payments, or misapplied cash. This overstates realized
revenue and understates true outstanding risk until cleaned up.

**Likely Cause:** Payment intake has no duplicate-detection gate before
posting to the ledger, and orphaned payments (no invoice reference) are being
accepted without a matching workflow.

**Recommended Action:** Treat this as a control-remediation priority, not a
revenue story: (1) block duplicate payment postings at intake using the
existing `payment_reference`/amount check the reconciliation engine already
implements, (2) build a manual-match queue for the 197 orphaned payments so
they get applied to the correct invoice or refunded, (3) re-state realization
rate excluding unresolved duplicates until the book is clean.

---

## 8. Revenue is concentrated but not dangerously so

**Observation:** The top 10 merchants by billed revenue contribute 12.4% of
total billed revenue (₹15.87 crore all-time) — no single merchant dominates.
The single largest merchant (MER00016) contributes ₹3.14 lakh, under 2% of
total.

**Financial Impact:** Low concentration risk — losing any one merchant,
including the top account, would not materially impair revenue. This is a
healthy diversification profile for a payments-infrastructure business.

**Likely Cause:** The merchant base is deliberately long-tail-weighted (40%
of merchants are Long-tail segment per the data model), which naturally caps
single-account concentration.

**Recommended Action:** No urgent action — this is a strength to state
explicitly in board/investor reporting. Continue monitoring concentration
quarterly as Enterprise-segment accounts grow, since that segment carries
disproportionately large individual contracts.

---

## 9. Recurring billing errors cluster in a small set of merchants

**Observation:** A short list of merchants (e.g., MER00934, MER00095,
MER00250, MER00591) each show 6–8 non-Correct billing events across the
24-month history — far above the modal merchant, which has 0–1.

**Financial Impact:** These merchants are disproportionately consuming
billing-team rework time and are the most likely source of recurring,
avoidable revenue leakage if left unaddressed.

**Likely Cause:** Repeat errors on the same merchant point to a
merchant-specific configuration issue (e.g., a contract with unusual terms,
frequent plan changes, or a manual billing override) rather than a systemic
platform bug, since the wider merchant base doesn't show the same pattern.

**Recommended Action:** Pull the contract history for the top repeat-offender
merchants and manually audit their billing configuration — a one-time fix per
merchant is likely cheaper than continuing to catch and correct the same
error every billing cycle.

---

## Summary: Where should Finance focus first?

| Priority | Issue | Financial stake |
|---|---|---|
| 1 | Duplicate/orphaned payment cleanup (control gap) | Overstates realized revenue by ≥₹21 lakh |
| 2 | Failed Payment leakage recovery track | ₹3.26 lakh, largest leakage category |
| 3 | 90+ day AR back-book (churned-merchant escalation) | ₹23.4 lakh, 81% of open AR |
| 4 | Missing Invoice monthly gate | ₹2.51 lakh, 100% unbilled |
| 5 | Collection channel reallocation (Email → WhatsApp/Phone) | Efficiency gain, no new spend |

Full supporting figures for every insight above are reproducible by running
`python -m src.collections.run_collections`, `python -m src.revenue_leakage.run_leakage_engine`,
and `python -m src.reconciliation.run_reconciliation`, then reading the corresponding
CSVs in `data/processed/`.
