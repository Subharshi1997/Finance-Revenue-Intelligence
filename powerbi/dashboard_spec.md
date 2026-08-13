# Power BI Dashboard Specification

**Note on scope:** this environment does not have Power BI Desktop installed,
so no `.pbix` binary is committed here. What's provided instead is
everything needed to build the dashboard directly: star-schema-ready CSV
exports (via `src/reporting/prepare_powerbi_datasets.py`), the full data
model, every DAX measure, and a page-by-page layout spec. This is the
"explain the limitation, provide the best practical alternative" approach.

## 1. Data sources

Run `python -m src.reporting.prepare_powerbi_datasets` after building the SQL
database (see README Installation). It writes 7 CSVs to
`data/processed/powerbi/`:

| File | Grain | Role |
|---|---|---|
| `dim_merchant.csv` | 1 row per merchant | Dimension |
| `dim_date.csv` | 1 row per calendar day | Dimension |
| `fact_invoices.csv` | 1 row per invoice | Fact — billing status, revenue |
| `fact_payments.csv` | 1 row per payment | Fact — reconciliation status |
| `fact_collection_activity.csv` | 1 row per collector touchpoint | Fact — collections |
| `fact_revenue_leakage.csv` | 1 row per leakage event | Fact — leakage |
| `fact_ar_aging.csv` | 1 row per open invoice | Fact — AR aging (snapshot) |

Import all 7 via **Get Data → Text/CSV**, or point Power BI at
`data/processed/powerbi/` as a folder source if you want it to auto-refresh
as the CSVs regenerate.

## 2. Data model

Star schema — every fact table relates **only** to the two dimension tables,
never directly to another fact table (avoids ambiguous/many-to-many
relationship problems):

```
dim_merchant (merchant_id) ──1:*── fact_invoices (merchant_id)
             │                └──1:*── fact_payments (merchant_id)
             │                └──1:*── fact_collection_activity (merchant_id)
             │                └──1:*── fact_revenue_leakage (merchant_id)
             │                └──1:*── fact_ar_aging (merchant_id)
             │
dim_date (date_key) ──1:*── fact_invoices (invoice_date → date_key)
         └──1:*── fact_payments (payment_date → date_key)
         └──1:*── fact_collection_activity (activity_date → date_key)
         └──1:*── fact_revenue_leakage (detection_date → date_key)
```

All relationships: **Single direction, One-to-Many, dimension → fact.**
`fact_invoices` additionally has an *inactive* relationship on `due_date` for
overdue/AR-specific visuals — activate it with `USERELATIONSHIP()` inside
the specific DAX measures that need it (e.g. AR aging), rather than making it
the default active relationship.

## 3. Core DAX measures

```dax
Billed Revenue =
    SUM(fact_invoices[billed_fee])

Expected Revenue =
    SUM(fact_invoices[expected_fee])

Collected Revenue =
    CALCULATE(SUM(fact_payments[payment_amount]), fact_payments[payment_status] = "Success")

Revenue Realization % =
    DIVIDE([Collected Revenue], [Billed Revenue], BLANK())

Billing Accuracy % =
    DIVIDE(
        CALCULATE(SUM(fact_invoices[expected_fee]), fact_invoices[billing_status] = "Correct"),
        [Expected Revenue],
        BLANK()
    )

Total AR =
    SUM(fact_ar_aging[outstanding_amount])

AR 90+ Days % =
    DIVIDE(
        CALCULATE(SUM(fact_ar_aging[outstanding_amount]), fact_ar_aging[aging_bucket] = "90+ days"),
        [Total AR],
        BLANK()
    )

DSO (Trailing 90) =
    VAR TrailingSales =
        CALCULATE(
            SUM(fact_invoices[billed_fee]),
            DATESINPERIOD(dim_date[date], MAX(dim_date[date]), -90, DAY)
        )
    RETURN
        DIVIDE([Total AR], TrailingSales, BLANK()) * 90

Collection Rate % =
    VAR Billed = CALCULATE([Billed Revenue], DATESINPERIOD(dim_date[date], MAX(dim_date[date]), -90, DAY))
    VAR Collected = CALCULATE([Collected Revenue], DATESINPERIOD(dim_date[date], MAX(dim_date[date]), -90, DAY))
    RETURN DIVIDE(Collected, Billed, BLANK())

Revenue Leakage Total =
    CALCULATE(
        SUM(fact_revenue_leakage[leakage_amount]),
        fact_revenue_leakage[leakage_type] IN
            {"Underbilling", "Pricing Mismatch", "Missing Invoice", "Failed Payment"}
    )

Leakage Outstanding =
    CALCULATE([Revenue Leakage Total], fact_revenue_leakage[status] = "Outstanding")

Reconciliation Rate % =
    DIVIDE(
        CALCULATE(COUNTROWS(fact_payments), fact_payments[reconciliation_status] = "MATCHED"),
        COUNTROWS(fact_payments),
        BLANK()
    )

Revenue Growth % (MoM) =
    VAR CurrentRev = [Billed Revenue]
    VAR PriorRev = CALCULATE([Billed Revenue], DATEADD(dim_date[date], -1, MONTH))
    RETURN DIVIDE(CurrentRev - PriorRev, PriorRev, BLANK())
```

## 4. Pages

### Page 1 — Executive Finance Overview
**Cards:** Billed Revenue, Revenue Growth % (MoM), Collection Rate %, Total
AR, DSO (Trailing 90), Revenue Leakage Total, Billing Accuracy %.
**Charts:**
- Line: Billed Revenue vs. Collected Revenue by month (`fact_invoices` +
  `fact_payments`, both by `dim_date`)
- Bar: Revenue by merchant segment (`dim_merchant[merchant_segment]`)
- Table: Top 10 merchants by Billed Revenue
**Filters:** date range slicer (dim_date), merchant segment slicer.

### Page 2 — Billing & Revenue
**Cards:** Expected Revenue, Billed Revenue, Billing Accuracy %, Revenue
Realization %, Revenue Leakage Total.
**Charts:**
- Clustered column: Expected vs. Billed Revenue by month
- Donut: Leakage by type (`fact_revenue_leakage[leakage_type]`)
- Bar: Leakage by merchant (top 15)
- Waterfall: Billing status counts (Correct/Underbilled/Overbilled/Missing Invoice/Pricing Mismatch)
**Drill-through:** click a merchant bar → merchant-level invoice detail page.

### Page 3 — AR & Collections
**Cards:** Total AR, AR 90+ Days %, DSO, Collection Rate %.
**Charts:**
- Stacked bar: AR by aging bucket by merchant segment
- Line: DSO trend by month (monthly grain, not the trailing-90 headline — see KPI note below)
- Table: Collection priority queue (`priority_rank`, `merchant_name`,
  `outstanding_amount`, `days_overdue`, `priority_tier`) with conditional
  formatting (red/amber/green background on `priority_tier`)
- Bar: Collection success rate by channel and by segment
**Filters:** aging bucket, payer segment.

### Page 4 — Reconciliation & Controls
**Cards:** Total Transactions/Payments, Reconciliation Rate %, Unmatched
Payments count, Duplicate Payments count, Missing Invoices count.
**Charts:**
- Donut: Reconciliation status breakdown (`fact_payments[reconciliation_status]`)
- Bar: Mismatch types (DUPLICATE, AMOUNT_MISMATCH, TIMING_MISMATCH, ORPHAN, UNMATCHED)
- Line: Leakage trend by month
- Table: Top control failures (highest-value unmatched/duplicate items)

## 5. KPI presentation notes

- **Always show DSO alongside monthly DSO**, not the trailing-90 headline
  alone — see `docs/business_insights.md` insight #4 for why the headline
  number can mislead on its own.
- **Realization % above 100%** should trigger a visual alert (e.g. KPI card
  turns red) rather than being displayed as a positive result — it signals a
  reconciliation control gap, not strong performance (insight #7).
- Use the same color semantics across every page: red = risk/overdue/leakage,
  green = healthy/collected/matched, amber = needs review — consistent
  enough that a CFO can read status at a glance without re-learning the
  legend per page.
