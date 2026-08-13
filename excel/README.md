# Excel Finance Model — `finance_ops_model.xlsx`

Built by `src/reporting/build_excel_model.py`. Regenerate with:

```bash
python -m src.reporting.build_excel_model
```

## Why a 40-merchant sample, not the full dataset

The workbook uses 40 merchants stratified by segment (4 Enterprise, 8
Mid-Market, 14 SMB, 14 Long-tail — proportional to the real segment mix)
with **every** invoice, payment, credit note, and collection activity those
merchants have, so every cross-sheet formula (XLOOKUP, SUMIFS) joins against
a complete, consistent dataset rather than an independently-sampled one that
would break referential joins. `Raw Transactions` is the one exception — it's
capped at 2,500 rows since transactions aren't joined row-by-row elsewhere in
the workbook, so subsampling them doesn't affect any other sheet's formulas.

**Requires Excel 2019+ / Microsoft 365** (or a compatible tool) — `XLOOKUP`
and `IFS` are not available in Excel 2016 or earlier.

## Sheets

| Sheet | Purpose | Key techniques |
|---|---|---|
| **KPI Dashboard** | Headline metrics, opens first | SUMIFS, COUNTIF, cross-sheet references |
| Merchants | Lookup/reference table for the sample | Excel Table |
| Raw Transactions | Sampled transaction-level detail | Excel Table |
| Invoices | Full invoice detail for the 40 merchants | Excel Table |
| Payments | Full payment detail for those invoices | Excel Table |
| Invoice Validation | Expected vs. billed, live status classification | XLOOKUP, IF, conditional formatting, **Data Validation dropdown** (`review_status`) |
| AR Aging | Outstanding balance, aging bucket, summary block | SUMIFS, IFS, color-scale conditional formatting |
| Collections | Collection activity + channel-effectiveness summary | COUNTIFS |
| Revenue Reconciliation | Invoice vs. total payments, match status | XLOOKUP, SUMIFS, IFS |
| Monthly MIS | Month-by-month billed/expected revenue | SUMIFS/COUNTIFS with `DATE()`/`EDATE()` helper columns |

## Formula notes

- **Date handling:** every `*_date` column is written as a real Excel date
  value (not text), so date arithmetic (`DATE(...) - due_date`, `EDATE(...)`)
  works correctly. Monthly MIS builds explicit date-range bounds via
  `DATE(VALUE(LEFT(...)),...)` + `EDATE()` rather than comparing dates to
  text strings, which is a common source of silently-wrong SUMIFS/COUNTIFS
  results when a locale doesn't parse the text as the expected date format.
- **XLOOKUP** pulls `merchant_name` from the `Merchants` sheet onto
  `Invoice Validation` and `AR Aging`, and pulls `expected_fee`/`billed_fee`/
  `total_invoice_amount`/`due_date` from the `Invoices` table using
  structured references (`tblInvoices[column]`) so the formulas stay
  correct if rows are inserted or sorted.
- **SUMIFS/COUNTIFS** compute total_paid per invoice (against `tblPayments`,
  filtered to `payment_status = "Success"`), aging bucket counts/totals, and
  channel-level collection effectiveness.
- **IF / IFS** classify billing status (Correct/Underbilled/Overbilled) and
  aging bucket (Current/1-30/31-60/61-90/90+), mirroring the same
  classification logic used in `src/billing/billing_engine.py` and
  `src/collections/ar_aging.py` (simplified — the Python engines additionally
  handle the Pricing-Mismatch-near-contract-transition case, which needs the
  `contracts` table and isn't reproduced here for scope).
- **Conditional formatting:** red/amber/green fills on billing status, a
  color scale on outstanding AR balance.
- **Data Validation:** a dropdown list (`Pending Review`, `Reviewed - No
  Action`, `Escalated to Billing`, `Corrected`) on the `review_status` column
  in Invoice Validation — the manual sign-off step layered on top of the
  system-derived `billing_status`.

## Known limitation: native Pivot Tables

Openpyxl (the library used to build this workbook) can only read existing
PivotTable definitions, not create new native ones — there's no supported
way to programmatically insert a real Excel PivotTable object. Rather than
fake it, the **Monthly MIS**, **AR Aging summary block**, and **Collections
channel-effectiveness summary** sheets provide the same output a pivot would
(grouped counts/sums) using live SUMIFS/COUNTIFS formulas instead.

To add a true native PivotTable for the interview/demo: open the workbook in
Excel, select `tblInvoices` or `tblTransactions`, **Insert → PivotTable**,
and build it against the sample data already in the sheet — this takes under
a minute and demonstrates the same skill directly in front of an interviewer.
