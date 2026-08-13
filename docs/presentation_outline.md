# Presentation Outline — Finance Operations & Revenue Intelligence Platform

15 slides, sized for a portfolio walkthrough in an interview (10–15 minutes,
leaving room for Q&A). Each slide lists its purpose and the key content to
include — build these in whatever tool you present with (PowerPoint, Google
Slides, or as speaker notes over the artifact/dashboard directly).

---

**1. Title**
Finance Operations & Revenue Intelligence Platform — End-to-End Billing, AR,
Collections, Reconciliation & Revenue Leakage Analytics. Subtitle: synthetic
portfolio project. Your name / role target (Finance & Operations Associate).

**2. Business Problem**
One sentence: Finance Ops teams at payments platforms must bill correctly,
collect on time, reconcile every rupee, and catch leakage before it becomes a
write-off — this project builds the system that does all four.

**3. Business Context**
Introduce the fictional company (Chekk): D2C checkout/payments platform,
~950 merchants, revenue from transaction fees + subscriptions, billed
monthly in arrears. One line on why this mirrors a real Shopflo/Pine
Labs-style business without using any real company's data.

**4. Finance Operations Workflow**
The 10 responsibilities this project covers (billing → invoicing → revenue
tracking → AR monitoring → collections → reconciliation → leakage detection →
MIS reporting), shown as a simple left-to-right flow.

**5. Data Architecture**
The pipeline diagram from the README: raw data → validation → SQL database →
finance engines → KPI datasets → Power BI / Excel / SQL analytics →
insights. Keep it to one clean diagram, not a wall of text.

**6. Billing & Revenue Analysis**
Show the billing_status breakdown (Correct/Underbilled/Overbilled/Missing
Invoice/Pricing Mismatch) and the 91.4% billing accuracy headline. Explain
the Pricing-Mismatch-vs-contract-transition logic as your "this wasn't a
naive classifier" proof point.

**7. Revenue Leakage**
The six leakage mechanisms and the ₹7.56 lakh realized total, split
Recovered/Recoverable/Outstanding. Highlight that Failed Payment is now the
largest category — a specific, defensible finding, not a generic "leakage
exists" statement.

**8. AR Aging**
The five-bucket aging chart, with the headline: 80.9% of open AR sits in
90+ days. Pair it with the risk-category logic (balance size × age) as your
methodology differentiator.

**9. Collections**
Collection rate (92.1%), recovery rate (16.3%), and the channel-effectiveness
finding (WhatsApp converts 4x better than Email but gets 12% of the volume).
This is your best "translated data into an action" slide.

**10. Reconciliation**
The invoice-level and payment-level status breakdown, and the duplicate/
orphaned-payment control-gap finding that's driving realization rate above
100%. Frame this as "the reconciliation engine caught a real control issue,"
not just a status report.

**11. Power BI Dashboard**
Screenshot(s) of the 4-page dashboard (Executive Overview, Billing & Revenue,
AR & Collections, Reconciliation & Controls) if built, or the dashboard spec
diagram if not — be upfront either way, per the project's own
Limitations section.

**12. Key Findings**
The condensed "Where should Finance focus first" priority table from
business_insights.md — 5 rows, financial stake next to each. This is the
slide a CFO would actually remember.

**13. Business Recommendations**
The five recommended actions in priority order, each tied to a dollar figure.
Keep this action-oriented, not descriptive — "block duplicate payment
postings at intake" not "there is a duplicate payment issue."

**14. Technical Architecture**
Stack summary: Python/Pandas for engines, SQLite for the data layer (28
analytical queries), Excel for the operational model, Power BI for
reporting, pytest for validation (35 tests). One line each — this slide
exists to signal breadth, not depth.

**15. Conclusion**
Restate the core claim: this project demonstrates the ability to translate
raw transaction/billing data into the specific controls and actions a
Finance Operations team needs — not just descriptive dashboards. Close with
an invitation to Q&A on any specific engine or finding.
