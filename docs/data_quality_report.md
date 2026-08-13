# Data Quality Report

Generated: 2026-08-13 19:10

This report covers the 9 raw finance tables before cleaning. See 'Cleaning actions applied' for what was corrected before loading into the SQL database, and 'Cross-table finance checks' for business exceptions that are intentionally preserved for downstream analysis.

## merchants
Rows: 950

**Missing required values**
None found

**Duplicate primary key rows**
0

**Invalid or out-of-range dates**
None found

**Date sequence violations**
None found

**Negative amounts**
None found

**Invalid rates (outside 0-15%)**
None found

**Invalid categorical values**
None found

**Referential integrity violations**
None found

## contracts
Rows: 1,155

**Missing required values**
None found

**Duplicate primary key rows**
0

**Invalid or out-of-range dates**
None found

**Date sequence violations**
None found

**Negative amounts**
None found

**Invalid rates (outside 0-15%)**
None found

**Invalid categorical values**
None found

**Referential integrity violations**
None found

## transactions
Rows: 271,633

**Missing required values**
- merchant_id: 2716
- payment_status: 3260

**Duplicate primary key rows**
2164

**Duplicate transactions (same merchant/order/date/amount)**
2100

**Invalid or out-of-range dates**
None found

**Date sequence violations**
None found

**Negative amounts**
- transaction_amount: 35

**Invalid rates (outside 0-15%)**
None found

**Invalid categorical values**
None found

**Referential integrity violations**
None found

## invoices
Rows: 20,200

**Missing required values**
- total_invoice_amount: 20

**Duplicate primary key rows**
0

**Invalid or out-of-range dates**
None found

**Date sequence violations**
None found

**Negative amounts**
None found

**Invalid rates (outside 0-15%)**
None found

**Invalid categorical values**
None found

**Referential integrity violations**
None found

## payments
Rows: 19,959

**Missing required values**
- payment_amount: 21

**Duplicate primary key rows**
0

**Invalid or out-of-range dates**
None found

**Date sequence violations**
None found

**Negative amounts**
None found

**Invalid rates (outside 0-15%)**
None found

**Invalid categorical values**
None found

**Referential integrity violations**
None found

## refunds
Rows: 37,172

**Missing required values**
None found

**Duplicate primary key rows**
0

**Invalid or out-of-range dates**
None found

**Date sequence violations**
None found

**Negative amounts**
None found

**Invalid rates (outside 0-15%)**
None found

**Invalid categorical values**
None found

**Referential integrity violations**
None found

## credit_notes
Rows: 1,695

**Missing required values**
- credit_amount: 11

**Duplicate primary key rows**
0

**Invalid or out-of-range dates**
None found

**Date sequence violations**
None found

**Negative amounts**
None found

**Invalid rates (outside 0-15%)**
None found

**Invalid categorical values**
None found

**Referential integrity violations**
None found

## collection_activity
Rows: 12,300

**Missing required values**
None found

**Duplicate primary key rows**
0

**Invalid or out-of-range dates**
None found

**Date sequence violations**
None found

**Negative amounts**
None found

**Invalid rates (outside 0-15%)**
None found

**Invalid categorical values**
None found

**Referential integrity violations**
None found

## disputes
Rows: 850

**Missing required values**
- disputed_amount: 10

**Duplicate primary key rows**
0

**Invalid or out-of-range dates**
None found

**Date sequence violations**
None found

**Negative amounts**
None found

**Invalid rates (outside 0-15%)**
None found

**Invalid categorical values**
None found

**Referential integrity violations**
None found

## Cross-table finance checks

**Missing invoices** (merchant-months with successful transactions but no invoice): 340

**Duplicate payments** (same invoice + amount paid more than once): 572

**Unmatched payments** (payment references a non-existent invoice_id): 0

**Orphan payments** (cash received with no invoice_id to apply it against): 197

**Invoices with no payment recorded** (open AR balance): 2,719

**Invoice/payment amount mismatches** (paid total != invoice total): 4,306

These are not treated as ingestion errors and are left in the cleaned dataset - they are the business exceptions that the reconciliation engine (Phase 7) and revenue leakage engine (Phase 8) are built to quantify.

## Cleaning actions applied

Only genuine ingestion garbage was corrected before loading into the SQL database - system-level duplicate IDs, orphan rows with no merchant reference, and physically invalid (negative) amounts. Business-meaningful exceptions were left in place.

**transactions**: 271,633 -> 267,820 rows
- duplicate_transaction_id_rows_dropped: 1082
- missing_merchant_id_rows_dropped: 2698
- negative_amount_rows_dropped: 33
- missing_payment_status_imputed: 3209

**invoices**: 20,200 -> 20,200 rows
- incomplete_invoice_amounts_recovered_from_expected_fee: 20

**merchants**: 950 -> 950 rows

**contracts**: 1,155 -> 1,155 rows

**payments**: 19,959 -> 19,959 rows

**refunds**: 37,172 -> 37,172 rows

**credit_notes**: 1,695 -> 1,695 rows

**collection_activity**: 12,300 -> 12,300 rows

**disputes**: 850 -> 850 rows

