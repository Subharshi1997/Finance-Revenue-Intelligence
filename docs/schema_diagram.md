# Database Schema

Entity-relationship diagram for the `finance_ops.db` SQLite database (see `sql/schema.sql` for full DDL).

```mermaid
erDiagram
    MERCHANTS ||--o{ CONTRACTS : "has pricing history"
    MERCHANTS ||--o{ TRANSACTIONS : "generates"
    MERCHANTS ||--o{ INVOICES : "is billed"
    MERCHANTS ||--o{ PAYMENTS : "makes"
    MERCHANTS ||--o{ REFUNDS : "issues"
    MERCHANTS ||--o{ CREDIT_NOTES : "receives"
    MERCHANTS ||--o{ COLLECTION_ACTIVITY : "is contacted for"
    MERCHANTS ||--o{ DISPUTES : "raises"

    TRANSACTIONS ||--o{ REFUNDS : "may be refunded"
    INVOICES ||--o{ PAYMENTS : "is paid by"
    INVOICES ||--o{ CREDIT_NOTES : "is adjusted by"
    INVOICES ||--o{ COLLECTION_ACTIVITY : "triggers"
    INVOICES ||--o{ DISPUTES : "may be disputed"

    MERCHANTS {
        text merchant_id PK
        text merchant_name
        text industry
        text merchant_segment
        text merchant_status
        real agreed_fee_percent
        int payment_terms_days
    }
    CONTRACTS {
        text contract_id PK
        text merchant_id FK
        text effective_from
        text effective_to
        real transaction_fee_percent
        text contract_status
    }
    TRANSACTIONS {
        text transaction_id PK
        text merchant_id FK
        text transaction_date
        real transaction_amount
        real expected_platform_fee
        text payment_status
    }
    INVOICES {
        text invoice_id PK
        text merchant_id FK
        text billing_period_start
        text due_date
        real expected_fee
        real billed_fee
        int invoice_error_flag
        text invoice_status
        text payment_status
    }
    PAYMENTS {
        text payment_id PK
        text invoice_id FK
        text merchant_id FK
        text payment_date
        real payment_amount
        text payment_status
    }
    REFUNDS {
        text refund_id PK
        text transaction_id FK
        text merchant_id FK
        real refund_amount
    }
    CREDIT_NOTES {
        text credit_note_id PK
        text invoice_id FK
        text merchant_id FK
        real credit_amount
    }
    COLLECTION_ACTIVITY {
        text collection_id PK
        text merchant_id FK
        text invoice_id FK
        text activity_type
        text outcome
    }
    DISPUTES {
        text dispute_id PK
        text merchant_id FK
        text invoice_id FK
        real disputed_amount
        text resolution_status
    }
```

## Design notes

- **`merchants` is the hub** — every other table hangs off `merchant_id`, matching how a real finance ops team slices everything by account.
- **`contracts` is the pricing history**, separate from the point-in-time `agreed_fee_percent` snapshot on `merchants`. A merchant with a mid-history price change has 2-3 contract rows with non-overlapping `effective_from`/`effective_to` windows; the billing engine (Phase 6) looks up the contract in effect on each transaction's date, which is what makes stale-rate billing errors detectable.
- **`payments.invoice_id` is nullable** — a handful of payments arrive with no invoice reference (orphan/unmatched cash), which is a real reconciliation exception, not a schema bug.
- **`invoices.expected_fee` vs `billed_fee`** is the core billing-accuracy signal: `invoice_error_flag = (billed_fee != expected_fee)`.
- No `ON DELETE CASCADE` is defined — this is an append-only analytical warehouse, not a transactional system; rows are never deleted after load, only appended.
