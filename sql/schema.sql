-- Finance Operations & Revenue Intelligence Platform
-- Database schema (SQLite). Run via src/utils/db.py's build_database(), or
-- with the sqlite3 module directly: pass this file to `executescript`.
--
-- Load order matters for foreign keys: merchants -> contracts -> transactions
-- -> invoices -> payments -> refunds -> credit_notes -> collection_activity
-- -> disputes.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS disputes;
DROP TABLE IF EXISTS collection_activity;
DROP TABLE IF EXISTS credit_notes;
DROP TABLE IF EXISTS refunds;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS invoices;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS contracts;
DROP TABLE IF EXISTS merchants;

CREATE TABLE merchants (
    merchant_id               TEXT PRIMARY KEY,
    merchant_name              TEXT NOT NULL,
    industry                   TEXT NOT NULL,
    merchant_segment           TEXT NOT NULL CHECK (merchant_segment IN ('Enterprise','Mid-Market','SMB','Long-tail')),
    city                       TEXT,
    state                      TEXT,
    country                    TEXT,
    onboarding_date            TEXT NOT NULL,
    account_manager            TEXT,
    pricing_plan                TEXT,
    contract_start_date        TEXT,
    contract_end_date          TEXT,
    agreed_fee_percent         REAL NOT NULL CHECK (agreed_fee_percent >= 0),
    monthly_subscription_fee   REAL DEFAULT 0,
    payment_terms_days         INTEGER NOT NULL CHECK (payment_terms_days > 0),
    merchant_status             TEXT NOT NULL CHECK (merchant_status IN ('Active','Churned','Suspended'))
);

CREATE TABLE contracts (
    contract_id             TEXT PRIMARY KEY,
    merchant_id             TEXT NOT NULL REFERENCES merchants(merchant_id),
    effective_from          TEXT NOT NULL,
    effective_to            TEXT,
    pricing_plan            TEXT,
    transaction_fee_percent REAL NOT NULL CHECK (transaction_fee_percent >= 0),
    fixed_transaction_fee   REAL DEFAULT 0,
    subscription_fee        REAL DEFAULT 0,
    payment_terms_days      INTEGER NOT NULL CHECK (payment_terms_days > 0),
    discount_percent        REAL DEFAULT 0,
    minimum_monthly_fee     REAL DEFAULT 0,
    contract_status         TEXT NOT NULL CHECK (contract_status IN ('Active','Superseded','Terminated'))
);

CREATE TABLE transactions (
    transaction_id           TEXT PRIMARY KEY,
    merchant_id              TEXT NOT NULL REFERENCES merchants(merchant_id),
    transaction_date         TEXT NOT NULL,
    order_id                 TEXT,
    transaction_amount       REAL NOT NULL CHECK (transaction_amount >= 0),
    transaction_fee_percent  REAL,
    expected_platform_fee    REAL,
    payment_method           TEXT,
    payment_status           TEXT NOT NULL CHECK (payment_status IN ('Success','Failed','Pending','Unknown')),
    order_status              TEXT,
    refund_amount            REAL DEFAULT 0,
    discount_amount          REAL DEFAULT 0,
    currency                 TEXT DEFAULT 'INR',
    created_timestamp        TEXT
);

CREATE TABLE invoices (
    invoice_id             TEXT PRIMARY KEY,
    merchant_id            TEXT NOT NULL REFERENCES merchants(merchant_id),
    billing_period_start   TEXT NOT NULL,
    billing_period_end     TEXT NOT NULL,
    invoice_date           TEXT NOT NULL,
    due_date               TEXT NOT NULL,
    subtotal               REAL,
    discount               REAL DEFAULT 0,
    taxable_amount         REAL,
    tax_rate               REAL,
    tax_amount             REAL,
    total_invoice_amount   REAL NOT NULL,
    currency               TEXT DEFAULT 'INR',
    invoice_status         TEXT NOT NULL CHECK (invoice_status IN ('Draft','Issued','Paid','Overdue','Void')),
    payment_status         TEXT NOT NULL CHECK (payment_status IN ('Unpaid','Partially Paid','Paid')),
    expected_fee            REAL,
    billed_fee              REAL,
    invoice_error_flag     INTEGER NOT NULL CHECK (invoice_error_flag IN (0,1))
);

CREATE TABLE payments (
    payment_id          TEXT PRIMARY KEY,
    invoice_id          TEXT REFERENCES invoices(invoice_id),
    merchant_id         TEXT NOT NULL REFERENCES merchants(merchant_id),
    payment_date        TEXT NOT NULL,
    payment_amount      REAL NOT NULL CHECK (payment_amount >= 0),
    payment_method       TEXT,
    payment_reference   TEXT,
    payment_status      TEXT NOT NULL CHECK (payment_status IN ('Success','Failed','Pending')),
    bank_reference      TEXT,
    settlement_date     TEXT
);

CREATE TABLE refunds (
    refund_id       TEXT PRIMARY KEY,
    transaction_id  TEXT NOT NULL REFERENCES transactions(transaction_id),
    merchant_id     TEXT NOT NULL REFERENCES merchants(merchant_id),
    refund_date     TEXT NOT NULL,
    refund_amount   REAL NOT NULL CHECK (refund_amount >= 0),
    refund_reason   TEXT,
    refund_status   TEXT CHECK (refund_status IN ('Processed','Pending','Rejected'))
);

CREATE TABLE credit_notes (
    credit_note_id    TEXT PRIMARY KEY,
    invoice_id        TEXT NOT NULL REFERENCES invoices(invoice_id),
    merchant_id       TEXT NOT NULL REFERENCES merchants(merchant_id),
    credit_note_date  TEXT NOT NULL,
    credit_amount     REAL NOT NULL CHECK (credit_amount >= 0),
    reason            TEXT,
    status            TEXT CHECK (status IN ('Issued','Applied','Pending'))
);

CREATE TABLE collection_activity (
    collection_id           TEXT PRIMARY KEY,
    merchant_id             TEXT NOT NULL REFERENCES merchants(merchant_id),
    invoice_id              TEXT REFERENCES invoices(invoice_id),
    activity_date           TEXT NOT NULL,
    activity_type           TEXT NOT NULL CHECK (activity_type IN ('Email','Phone','Reminder','Escalation','Payment Promise','Dispute','Resolution')),
    contact_channel         TEXT,
    collector               TEXT,
    outcome                 TEXT,
    promised_payment_date   TEXT,
    promised_amount         REAL,
    notes                   TEXT
);

CREATE TABLE disputes (
    dispute_id          TEXT PRIMARY KEY,
    merchant_id         TEXT NOT NULL REFERENCES merchants(merchant_id),
    invoice_id          TEXT NOT NULL REFERENCES invoices(invoice_id),
    dispute_date        TEXT NOT NULL,
    dispute_type        TEXT,
    disputed_amount     REAL CHECK (disputed_amount >= 0),
    resolution_status   TEXT CHECK (resolution_status IN ('Open','Resolved','Rejected','Escalated')),
    resolution_date     TEXT,
    resolution_amount   REAL
);

CREATE INDEX idx_contracts_merchant ON contracts(merchant_id);
CREATE INDEX idx_contracts_effective_from ON contracts(effective_from);

CREATE INDEX idx_transactions_merchant ON transactions(merchant_id);
CREATE INDEX idx_transactions_date ON transactions(transaction_date);
CREATE INDEX idx_transactions_status ON transactions(payment_status);

CREATE INDEX idx_invoices_merchant ON invoices(merchant_id);
CREATE INDEX idx_invoices_due_date ON invoices(due_date);
CREATE INDEX idx_invoices_status ON invoices(invoice_status);
CREATE INDEX idx_invoices_payment_status ON invoices(payment_status);
CREATE INDEX idx_invoices_billing_period ON invoices(billing_period_start);

CREATE INDEX idx_payments_invoice ON payments(invoice_id);
CREATE INDEX idx_payments_merchant ON payments(merchant_id);
CREATE INDEX idx_payments_date ON payments(payment_date);
CREATE INDEX idx_payments_status ON payments(payment_status);

CREATE INDEX idx_refunds_transaction ON refunds(transaction_id);
CREATE INDEX idx_refunds_merchant ON refunds(merchant_id);

CREATE INDEX idx_credit_notes_invoice ON credit_notes(invoice_id);
CREATE INDEX idx_credit_notes_merchant ON credit_notes(merchant_id);

CREATE INDEX idx_collection_merchant ON collection_activity(merchant_id);
CREATE INDEX idx_collection_invoice ON collection_activity(invoice_id);
CREATE INDEX idx_collection_date ON collection_activity(activity_date);

CREATE INDEX idx_disputes_merchant ON disputes(merchant_id);
CREATE INDEX idx_disputes_invoice ON disputes(invoice_id);
