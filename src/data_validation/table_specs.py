"""Per-table validation specs: which generic checks to run and with what
parameters. Declarative so `validators.run_table_checks` can stay a single
generic loop instead of nine near-identical hand-written functions.
"""

MIN_DATE = "2020-01-01"
# Wide enough to cover legitimate forward-looking dates (due dates, late
# payments, settlement dates) that extend past the 2024-08 to 2026-07
# transaction history window - this bound exists to catch garbage dates
# (e.g. year 1900 or 2099), not near-term dates driven by payment terms.
MAX_DATE = "2027-12-31"

TABLE_SPECS = {
    "merchants": {
        "id_col": "merchant_id",
        "required": ["merchant_id", "merchant_name", "onboarding_date", "merchant_status", "agreed_fee_percent"],
        "date_cols": ["onboarding_date", "contract_start_date"],
        "negative_cols": ["agreed_fee_percent", "monthly_subscription_fee", "payment_terms_days"],
        "range_checks": [("agreed_fee_percent", 0, 15)],
        "categorical": {
            "merchant_segment": {"Enterprise", "Mid-Market", "SMB", "Long-tail"},
            "merchant_status": {"Active", "Churned", "Suspended"},
        },
        "references": [],
    },
    "contracts": {
        "id_col": "contract_id",
        "required": ["contract_id", "merchant_id", "effective_from", "transaction_fee_percent"],
        "date_cols": ["effective_from"],
        "date_order": [("effective_from", "effective_to")],
        "negative_cols": ["fixed_transaction_fee", "subscription_fee", "minimum_monthly_fee", "discount_percent"],
        "range_checks": [("transaction_fee_percent", 0, 15)],
        "categorical": {"contract_status": {"Active", "Superseded", "Terminated"}},
        "references": [("merchant_id", "merchants", "merchant_id")],
    },
    "transactions": {
        "id_col": "transaction_id",
        "required": ["transaction_id", "merchant_id", "transaction_date", "transaction_amount", "payment_status"],
        "date_cols": ["transaction_date"],
        "negative_cols": ["transaction_amount", "refund_amount", "discount_amount", "expected_platform_fee"],
        "range_checks": [("transaction_fee_percent", 0, 15)],
        "categorical": {
            "payment_status": {"Success", "Failed", "Pending"},
            "order_status": {"Delivered", "Cancelled", "Returned", "Processing"},
        },
        "duplicate_subset": ["merchant_id", "order_id", "transaction_date", "transaction_amount"],
        "references": [("merchant_id", "merchants", "merchant_id")],
    },
    "invoices": {
        "id_col": "invoice_id",
        "required": ["invoice_id", "merchant_id", "invoice_date", "due_date", "total_invoice_amount"],
        "date_cols": ["invoice_date", "due_date"],
        "date_order": [("invoice_date", "due_date")],
        "negative_cols": ["subtotal", "tax_amount", "total_invoice_amount"],
        "range_checks": [],
        "categorical": {
            "invoice_status": {"Draft", "Issued", "Paid", "Overdue", "Void"},
            "payment_status": {"Unpaid", "Partially Paid", "Paid"},
        },
        "references": [("merchant_id", "merchants", "merchant_id")],
    },
    "payments": {
        "id_col": "payment_id",
        "required": ["payment_id", "payment_date", "payment_amount", "payment_status"],
        "date_cols": ["payment_date"],
        "negative_cols": ["payment_amount"],
        "range_checks": [],
        "categorical": {"payment_status": {"Success", "Failed", "Pending"}},
        "references": [("merchant_id", "merchants", "merchant_id")],
    },
    "refunds": {
        "id_col": "refund_id",
        "required": ["refund_id", "transaction_id", "merchant_id", "refund_amount"],
        "date_cols": ["refund_date"],
        "negative_cols": ["refund_amount"],
        "range_checks": [],
        "categorical": {"refund_status": {"Processed", "Pending", "Rejected"}},
        "references": [("transaction_id", "transactions", "transaction_id"), ("merchant_id", "merchants", "merchant_id")],
    },
    "credit_notes": {
        "id_col": "credit_note_id",
        "required": ["credit_note_id", "invoice_id", "credit_amount"],
        "date_cols": ["credit_note_date"],
        "negative_cols": ["credit_amount"],
        "range_checks": [],
        "categorical": {"status": {"Issued", "Applied", "Pending"}},
        "references": [("invoice_id", "invoices", "invoice_id"), ("merchant_id", "merchants", "merchant_id")],
    },
    "collection_activity": {
        "id_col": "collection_id",
        "required": ["collection_id", "merchant_id", "activity_date", "activity_type"],
        "date_cols": ["activity_date"],
        "negative_cols": [],
        "range_checks": [],
        "categorical": {
            "activity_type": {"Email", "Phone", "Reminder", "Escalation", "Payment Promise", "Dispute", "Resolution"},
        },
        "references": [("merchant_id", "merchants", "merchant_id"), ("invoice_id", "invoices", "invoice_id")],
    },
    "disputes": {
        "id_col": "dispute_id",
        "required": ["dispute_id", "merchant_id", "invoice_id", "disputed_amount"],
        "date_cols": ["dispute_date"],
        "negative_cols": ["disputed_amount"],
        "range_checks": [],
        "categorical": {"resolution_status": {"Open", "Resolved", "Rejected", "Escalated"}},
        "references": [("merchant_id", "merchants", "merchant_id"), ("invoice_id", "invoices", "invoice_id")],
    },
}
