# Interview Preparation

Model answers for likely interview questions about this project, organized by
domain. Written to be spoken naturally in an interview, not read verbatim —
use these as a foundation and adapt to the actual question asked.

---

## Finance

### 1. What is DSO, and how did you calculate it here?
DSO (Days Sales Outstanding) measures how many days, on average, it takes to
collect cash after billing: `(Total AR / Total Credit Sales) × Number of Days`.
I calculated it three ways — overall, monthly, and by merchant/segment —
because they answer different questions. Overall DSO uses all outstanding AR
against a 90-day sales window, which can be misleading if there's a lot of
old, aged AR sitting on the books (it inflates the number even if current
collections are fine). Monthly DSO isolates a single period's performance, so
I use that to judge whether current collections execution is actually
healthy. In my dataset, overall DSO looked like 106 days, but monthly DSO ran
4–6 days — the gap told me the real story was an aged back-book problem, not
a current-collections problem.

### 2. How do you calculate AR aging?
For every open invoice, outstanding = invoice total minus successful
payments minus applied credit notes. Then I bucket by days overdue relative
to the due date: Current, 1–30, 31–60, 61–90, 90+. I also built a combined
risk score that blends bucket age with balance size, because a ₹200
balance 95 days overdue and a ₹50,000 balance 95 days overdue are not the
same risk, even though they land in the same aging bucket.

### 3. What causes revenue leakage, and how did you detect it?
I split leakage into distinct, non-overlapping mechanisms rather than one
catch-all bucket: underbilling, pricing mismatches near contract rate
changes, missing invoices, failed payments with no successful collection,
plus two advisory categories (rate discrepancies caught before invoicing,
and refund-fee retention that's a policy question, not a confirmed loss).
Keeping them separate matters because each has a different root cause and a
different fix — underbilling needs a rate-freshness check, missing invoices
need a month-end reconciliation gate, failed payments need a dedicated
recovery workflow. A single "leakage %" number would have hidden all of that.

### 4. How do you reconcile invoices and payments?
I match at two levels. Invoice-level: for each invoice, sum successful
payments against it and classify — MATCHED, PARTIAL, MISSING_PAYMENT,
DUPLICATE (two payments of the same amount on one invoice), AMOUNT_MISMATCH
(overpaid), TIMING_MISMATCH (settlement date before payment date — a data or
process anomaly). Payment-level: classify each payment as MATCHED, ORPHAN (no
invoice reference at all), UNMATCHED (references an invoice that doesn't
exist), or DUPLICATE. I also separately catch merchant-months with real
transactions but no invoice at all, since those never even enter the
invoice-level reconciliation.

### 5. What is revenue realization, and why track it separately from billing accuracy?
Realization rate is collected revenue divided by billed revenue — it answers
"of what we billed, how much actually became cash." Billing accuracy is a
different question — "of what we billed, how much was the *correct* amount."
You can have 100% billing accuracy and still have poor realization if
merchants just aren't paying. Conflating the two would hide whether a
revenue shortfall is a billing problem or a collections problem, and those
need completely different fixes.

### 6. What is collection effectiveness, and what did you find?
I measured it a few ways: collection rate (cash in vs. billed in a period),
recovery rate (of invoices that needed active chasing, how much actually got
recovered), and success rate by channel/segment. The interesting finding was
that email carried the most volume (58% of all collector activity) but
converted worst (2.1% success), while WhatsApp got the least volume (7%) but
converted best (8.9%). That's a resourcing insight, not just a reporting
number — collectors were spending most effort on the weakest channel.

### 7. How would you handle an overdue customer?
I'd use the priority score rather than just "days overdue" — it blends
balance size, days overdue, the merchant's historical payment behavior, and
their account status (active/churned). A big, fresh balance from a
chronically-late-but-active merchant might rank higher than an old, small
balance from a merchant who otherwise pays well. Then I'd match the action to
the tier: automated reminders for Low, phone+email for Medium, immediate
escalation with account-manager involvement for Critical — and for anything
past 90 days on a churned merchant, I'd skip the standard sequence entirely
and go straight to legal/agency review, because the leverage to collect
through normal channels is essentially gone.

---

## Excel

### 8. How would you use XLOOKUP in a finance model?
XLOOKUP to pull invoice status, payment status, or merchant segment onto a
transaction-level sheet by matching on invoice_id or merchant_id — it's more
robust than VLOOKUP because it doesn't break if you insert a column, and it
has a clean built-in "not found" fallback instead of #N/A errors leaking
into downstream SUMIFS.

### 9. How would you use SUMIFS in AR aging?
`=SUMIFS(Outstanding, AgingBucket, "90+ days")` to total exposure per bucket,
or with multiple criteria — `SUMIFS(Outstanding, MerchantSegment, "SMB",
AgingBucket, "90+ days")` — to answer segment-specific questions directly in
the sheet without a pivot table, which is useful for a live MIS sheet that
needs to recalculate as data refreshes.

### 10. When would you use Pivot Tables vs. formulas?
Pivots for exploratory or summary views that change shape often — leakage by
type by month, AR by segment by bucket — because they don't require
rebuilding formulas when the grouping changes. Formulas (SUMIFS/COUNTIFS) for
fixed, repeatable outputs that feed other cells or need to sit inside a
templated report, since pivots don't play well as a formula input.

### 11. How would you build a reconciliation check in Excel?
A helper column with `=IF(ABS(SUM of payments - Invoice Total)<=Tolerance,
"MATCHED", IF(...))` mirroring the same priority-order logic I used in
Python, then conditional formatting to color-flag anything not MATCHED, and
a COUNTIFS-based summary table showing count and % by status — essentially
a lightweight version of the reconciliation engine for someone without
database access.

---

## SQL

### 12. Walk me through a JOIN you'd use here.
To get outstanding AR per invoice with merchant context, I'd LEFT JOIN
invoices to a payments subquery (grouped/summed by invoice_id) and to a
credit_notes subquery the same way, then INNER JOIN to merchants for segment
and name. LEFT JOINs matter here because an invoice with zero payments still
needs to appear in the AR report — an INNER JOIN would silently drop it.

### 13. When would you use a window function vs. GROUP BY?
GROUP BY collapses rows into one row per group — good for a monthly revenue
total. Window functions (e.g. `SUM(...) OVER (PARTITION BY merchant_id ORDER
BY billing_period)`) keep every row but add a running or comparative value —
I used that pattern for month-over-month revenue growth and running AR
balances, where I need the detail row *and* a comparison to another row in
the same result set.

### 14. Why use a CTE instead of a subquery?
Readability and reuse mainly — if I need the same intermediate result (say,
"invoices with their total paid amount") in more than one place in a query,
a CTE names it once and I can reference it multiple times, versus repeating
the same subquery or nesting it awkwardly. It also makes a multi-step
calculation (like the reconciliation status logic) easier to read top to
bottom instead of inside-out.

### 15. How would you find duplicate payments in SQL?
`SELECT invoice_id, payment_amount, COUNT(*) FROM payments WHERE
payment_status='Success' GROUP BY invoice_id, payment_amount HAVING
COUNT(*) > 1` — same invoice, same amount, more than once. That's the same
logic I implemented in the Python reconciliation engine, just expressed as a
GROUP BY/HAVING instead of a pandas `duplicated()` check.

---

## Python

### 16. Why pandas over raw SQL for the finance engines?
SQL handles the joins and aggregation well, but the classification logic
(billing status, reconciliation status, leakage type, priority tier) is
easier to express, test, and document as readable Python with named
conditions than as nested SQL CASE statements — especially when the logic
has real business nuance (like "Pricing Mismatch" needing to check proximity
to an actual contract change date, not just a ratio threshold). I used SQL
for the data layer and pandas for the judgment layer.

### 17. How did you handle data cleaning?
A dedicated validation module (`src/data_validation/`) checks for missing
values, duplicate IDs, invalid dates, negative amounts, out-of-range fee
rates, and referential integrity issues before anything loads into the SQL
database, and produces a data quality report documenting what was found and
what was corrected vs. intentionally preserved (some "errors" like duplicate
payments are deliberate data imperfections the downstream engines are
supposed to detect, not clean away).

### 18. How would you automate this pipeline end-to-end?
Each phase already has a `run_*.py` entry point that reads from the DB,
computes, and writes to `data/processed/`. Chaining them (as documented in
the README's Installation section) is the automation — the natural next
step would be wrapping that in a scheduler (cron/Airflow) so billing period
close automatically triggers validation → engines → KPI refresh, with a
failure alert if reconciliation rate or billing accuracy drops below a
threshold.

### 19. What edge cases did you test for, and why?
Zero-amount invoices, full/partial/duplicate/overpaid payments, credit notes
that fully offset an invoice, missing invoices and missing payments, same-day
and early payments, and extremely overdue invoices (400+ days). These aren't
arbitrary — they're the exact failure modes the reconciliation and leakage
engines exist to catch, so if the tests don't cover them, the engines aren't
really validated. I built a small hand-crafted fixture database rather than
testing against the full synthetic dataset, so each test's expected result
is something I can verify by hand.

---

## Power BI

### 20. How would you model this data in Power BI?
Star-schema-ish: fact tables (invoices, payments, transactions, leakage,
collection activity) each with a foreign key to a merchants dimension, plus a
shared date dimension table for consistent time intelligence across all the
fact tables. I'd avoid snowflaking contracts into a separate dimension unless
rate-history drill-down is a specific requirement, since it adds join
complexity for a relatively small table.

### 21. What DAX measures would you build first?
Collection Rate, Realization Rate, DSO (as an explicit measure, not a
calculated column, since it needs to recompute correctly at whatever
date-filter grain the user selects), and Leakage by Type — each written as a
DAX measure over the fact tables so they respond correctly to slicers instead
of being pre-aggregated and frozen.

### 22. How do you handle relationships between fact tables?
I wouldn't relate fact tables directly to each other (invoices to payments,
say) — I'd relate both to shared dimensions (merchant, date) and let
cross-filtering happen through those, which avoids ambiguous or
many-to-many relationship issues that are hard to debug later.

### 23. How would you design the dashboard for a non-technical CFO audience?
Executive Overview page first with the handful of numbers that matter most —
revenue, DSO, collection rate, leakage — each with a trend, not just a
snapshot. Drill-down detail (leakage by merchant, AR by invoice) lives on
separate pages a CFO can go to if something looks off, rather than
front-loading every metric onto one crowded page.

---

## Business

### 24. How would you reduce DSO?
First, separate the two problems DSO can represent: a large aged back-book
(a stock problem — needs write-off/recovery-agency review) versus slow
current collections (a flow problem — needs tighter terms, earlier
escalation, or channel reallocation). In this project's data, it was mostly
the first: monthly DSO was already healthy at 4–6 days, so the fix was
clearing 90+-day churned-merchant balances, not "collect faster" broadly.

### 25. How would you prioritize collections?
With a transparent weighted score rather than a single dimension like "days
overdue" alone — balance size, days overdue, historical payment behavior, and
account risk together, because the biggest overdue balance isn't always the
most collectable one, and vice versa. Explainability matters here: a
collector or manager should be able to see *why* an account ranked where it
did, not just trust a black-box number.

### 26. How would you detect revenue leakage?
By mechanism, not as one aggregate number — compare expected vs. billed at
the invoice level, check for merchant-months with transactions but no
invoice, check for invoices with only failed payment attempts, and check
whether refunded transactions had their fee correctly reversed. Each check
answers a different "where is money leaking" question and routes to a
different owner to fix.

### 27. What KPIs would you report to a CFO?
Revenue (billed and collected), Realization Rate, DSO (both headline and
monthly, with the distinction explained), Collection Rate, Total AR with
aging composition, and Revenue Leakage split by recovered/recoverable/
outstanding. I'd always pair a headline number with the one caveat that
changes how to read it — e.g. "DSO is 106 days, but that's back-book driven;
current-period DSO is 5 days."

### 28. What would you do if billed revenue increased but collections declined?
Don't treat it as one problem — check billing accuracy first (is the
increase real, correctly-priced revenue, or an artifact of billing errors),
then check whether the *mix* of new billings shifted toward slower-paying
segments or riskier merchants, then check whether collections capacity
(collector headcount, channel effectiveness) kept pace with invoice volume.
Rising billed revenue with falling collections is exactly the pattern that
inflates DSO and AR risk if left unaddressed, so I'd flag it immediately
rather than wait for it to show up in an aging report months later.

### 29. How do you decide what counts as "real" leakage vs. an advisory item?
I only count something as leakage if the company was actually owed the money
and didn't collect it. Rate Discrepancy transactions get corrected before
invoicing (never realized as loss), and Refund Fee Retention is a genuine
policy question — the business's own credit-note data shows refunds were
never designed to trigger fee reversal, so asserting it as "leakage" would
overstate the problem and understate the real, uncontested leakage sitting
right next to it (underbilling, missing invoices, failed payments).

### 30. What would you do differently with more time or real data?
Add the optional payment-delay-risk ML model now that the finance logic is
solid, wire the reconciliation control gaps (duplicate/orphaned payments)
into an intake-time validation gate instead of a post-hoc report, and
validate the synthetic data's correlations (payment delay vs. segment,
seasonality vs. industry) against real transaction data if this were a
production system, since synthetic correlations are designed to be
plausible but aren't fitted to actual behavior.

---

## A few questions to expect that aren't formula-based

**"Walk me through this project in two minutes."**
"I built an end-to-end Finance Operations & Revenue Intelligence Platform
that simulates the finance workflow of a D2C/SaaS checkout business —
billing validation, revenue realization, AR aging, collections prioritization,
invoice-payment reconciliation, and revenue leakage detection. I used SQL for
the financial data layer, Python for the calculation engines and automation,
Excel for the operational workflows, and Power BI for management reporting.
The dataset is synthetic but deliberately imperfect — duplicate payments,
missing invoices, contract rate changes mid-stream — because the whole point
was to build the controls that catch those problems, not just report on
clean data."

**"What was the hardest part?"**
Getting the classification logic right without hand-waving edge cases —
for example, deciding that "Pricing Mismatch" should be anchored to an actual
contract transition date rather than reverse-engineered from the
billed/expected ratio, because the underlying data-generation mechanisms
produce overlapping ratios that can't be reliably told apart by magnitude
alone. Getting that kind of judgment call right, and documenting *why*, was
more work than the plumbing.
