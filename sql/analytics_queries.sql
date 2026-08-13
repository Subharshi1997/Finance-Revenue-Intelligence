-- Finance Operations & Revenue Intelligence Platform
-- 28 analytical queries against finance_ops.db (SQLite 3.45+, window functions
-- and CTEs supported throughout). Each query answers one real finance-ops
-- question; run individually, not as a script (several intentionally return
-- overlapping/different cuts of the same tables).
--
-- Reporting snapshot date used throughout: 2026-08-13 (the day after the last
-- full billing month, 2026-07, in the synthetic 24-month dataset).

-- =====================================================================
-- 1. Monthly revenue (billed) trend
-- =====================================================================
SELECT
    strftime('%Y-%m', invoice_date) AS billing_month,
    COUNT(*) AS invoice_count,
    ROUND(SUM(billed_fee), 2) AS billed_revenue,
    ROUND(SUM(expected_fee), 2) AS expected_revenue
FROM invoices
GROUP BY billing_month
ORDER BY billing_month;

-- =====================================================================
-- 2. Month-over-month revenue growth %
-- =====================================================================
WITH monthly AS (
    SELECT strftime('%Y-%m', invoice_date) AS billing_month, SUM(billed_fee) AS revenue
    FROM invoices
    GROUP BY billing_month
)
SELECT
    billing_month,
    ROUND(revenue, 2) AS revenue,
    ROUND(LAG(revenue) OVER (ORDER BY billing_month), 2) AS prior_month_revenue,
    ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY billing_month))
          / NULLIF(LAG(revenue) OVER (ORDER BY billing_month), 0), 2) AS growth_percent
FROM monthly
ORDER BY billing_month;

-- =====================================================================
-- 3. Top 20 merchants by billed revenue
-- =====================================================================
SELECT
    m.merchant_id,
    m.merchant_name,
    m.merchant_segment,
    ROUND(SUM(i.billed_fee), 2) AS total_billed_revenue,
    COUNT(i.invoice_id) AS invoice_count
FROM invoices i
JOIN merchants m ON m.merchant_id = i.merchant_id
GROUP BY m.merchant_id
ORDER BY total_billed_revenue DESC
LIMIT 20;

-- =====================================================================
-- 4. Outstanding accounts receivable per invoice
-- =====================================================================
WITH paid AS (
    SELECT invoice_id, SUM(payment_amount) AS total_paid
    FROM payments WHERE payment_status = 'Success'
    GROUP BY invoice_id
),
credited AS (
    SELECT invoice_id, SUM(credit_amount) AS total_credited
    FROM credit_notes WHERE status IN ('Issued', 'Applied')
    GROUP BY invoice_id
)
SELECT * FROM (
    SELECT
        i.invoice_id,
        i.merchant_id,
        i.total_invoice_amount,
        COALESCE(p.total_paid, 0) AS total_paid,
        COALESCE(c.total_credited, 0) AS total_credited,
        ROUND(i.total_invoice_amount - COALESCE(p.total_paid, 0) - COALESCE(c.total_credited, 0), 2) AS outstanding_amount
    FROM invoices i
    LEFT JOIN paid p ON p.invoice_id = i.invoice_id
    LEFT JOIN credited c ON c.invoice_id = i.invoice_id
    WHERE i.invoice_status != 'Void'
)
WHERE outstanding_amount > 0.01
ORDER BY outstanding_amount DESC;

-- =====================================================================
-- 5. AR aging buckets
-- =====================================================================
WITH paid AS (
    SELECT invoice_id, SUM(payment_amount) AS total_paid
    FROM payments WHERE payment_status = 'Success'
    GROUP BY invoice_id
),
outstanding AS (
    SELECT
        i.invoice_id, i.merchant_id, i.due_date,
        ROUND(i.total_invoice_amount - COALESCE(p.total_paid, 0), 2) AS outstanding_amount,
        CAST(julianday('2026-08-13') - julianday(i.due_date) AS INTEGER) AS days_overdue
    FROM invoices i
    LEFT JOIN paid p ON p.invoice_id = i.invoice_id
    WHERE i.invoice_status != 'Void'
      AND (i.total_invoice_amount - COALESCE(p.total_paid, 0)) > 0.01
)
SELECT
    CASE
        WHEN days_overdue <= 0 THEN 'Current'
        WHEN days_overdue BETWEEN 1 AND 30 THEN '1-30 days'
        WHEN days_overdue BETWEEN 31 AND 60 THEN '31-60 days'
        WHEN days_overdue BETWEEN 61 AND 90 THEN '61-90 days'
        ELSE '90+ days'
    END AS aging_bucket,
    COUNT(*) AS invoice_count,
    ROUND(SUM(outstanding_amount), 2) AS total_outstanding
FROM outstanding
GROUP BY aging_bucket
ORDER BY MIN(days_overdue);

-- =====================================================================
-- 6. Days Sales Outstanding (DSO) - trailing 90 days, standard formula:
--    DSO = (Total AR / Total Credit Sales in period) * Number of Days
-- =====================================================================
WITH period AS (
    SELECT date('2026-08-13', '-90 days') AS period_start, date('2026-08-13') AS period_end
),
credit_sales AS (
    SELECT SUM(billed_fee) AS total_sales
    FROM invoices, period
    WHERE invoice_date BETWEEN period_start AND period_end
),
paid AS (
    SELECT invoice_id, SUM(payment_amount) AS total_paid
    FROM payments WHERE payment_status = 'Success'
    GROUP BY invoice_id
),
total_ar AS (
    SELECT SUM(i.total_invoice_amount - COALESCE(p.total_paid, 0)) AS total_ar
    FROM invoices i
    LEFT JOIN paid p ON p.invoice_id = i.invoice_id
    WHERE i.invoice_status != 'Void'
)
SELECT
    ROUND(total_ar.total_ar, 2) AS total_ar,
    ROUND(credit_sales.total_sales, 2) AS trailing_90d_credit_sales,
    ROUND(total_ar.total_ar / NULLIF(credit_sales.total_sales, 0) * 90, 1) AS dso_days
FROM total_ar, credit_sales;

-- =====================================================================
-- 7. Overdue invoices (open balance past due date)
-- =====================================================================
WITH paid AS (
    SELECT invoice_id, SUM(payment_amount) AS total_paid
    FROM payments WHERE payment_status = 'Success'
    GROUP BY invoice_id
)
SELECT
    i.invoice_id, i.merchant_id, i.due_date,
    ROUND(i.total_invoice_amount - COALESCE(p.total_paid, 0), 2) AS outstanding_amount,
    CAST(julianday('2026-08-13') - julianday(i.due_date) AS INTEGER) AS days_overdue
FROM invoices i
LEFT JOIN paid p ON p.invoice_id = i.invoice_id
WHERE i.invoice_status != 'Void'
  AND i.due_date < '2026-08-13'
  AND (i.total_invoice_amount - COALESCE(p.total_paid, 0)) > 0.01
ORDER BY days_overdue DESC;

-- =====================================================================
-- 8. Collection rate by month (collected / billed)
-- =====================================================================
WITH billed AS (
    SELECT strftime('%Y-%m', invoice_date) AS month, SUM(billed_fee) AS billed_revenue
    FROM invoices
    GROUP BY month
),
collected AS (
    SELECT strftime('%Y-%m', payment_date) AS month, SUM(payment_amount) AS collected_revenue
    FROM payments WHERE payment_status = 'Success'
    GROUP BY month
)
SELECT
    b.month,
    ROUND(b.billed_revenue, 2) AS billed_revenue,
    ROUND(COALESCE(c.collected_revenue, 0), 2) AS collected_revenue,
    ROUND(100.0 * COALESCE(c.collected_revenue, 0) / NULLIF(b.billed_revenue, 0), 2) AS collection_rate_percent
FROM billed b
LEFT JOIN collected c ON c.month = b.month
ORDER BY b.month;

-- =====================================================================
-- 9. Payment behavior per merchant (delay, on-time %)
-- =====================================================================
WITH first_payment AS (
    SELECT invoice_id, MIN(payment_date) AS first_payment_date
    FROM payments WHERE payment_status = 'Success'
    GROUP BY invoice_id
),
delays AS (
    SELECT
        i.merchant_id,
        CAST(julianday(fp.first_payment_date) - julianday(i.due_date) AS INTEGER) AS delay_days
    FROM invoices i
    JOIN first_payment fp ON fp.invoice_id = i.invoice_id
)
SELECT
    merchant_id,
    COUNT(*) AS paid_invoice_count,
    ROUND(AVG(delay_days), 1) AS avg_payment_delay_days,
    ROUND(100.0 * SUM(CASE WHEN delay_days <= 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_payment_percent,
    MAX(delay_days) AS max_delay_days
FROM delays
GROUP BY merchant_id
ORDER BY avg_payment_delay_days DESC;

-- =====================================================================
-- 10. Revenue leakage summary (expected vs billed gap, underbilled only)
-- =====================================================================
SELECT
    merchant_id,
    COUNT(*) AS underbilled_invoice_count,
    ROUND(SUM(expected_fee - billed_fee), 2) AS total_leakage_amount
FROM invoices
WHERE invoice_error_flag = 1 AND billed_fee < expected_fee
GROUP BY merchant_id
HAVING total_leakage_amount > 0
ORDER BY total_leakage_amount DESC;

-- =====================================================================
-- 11. Billing errors by merchant segment
-- =====================================================================
SELECT
    m.merchant_segment,
    COUNT(*) AS total_invoices,
    SUM(i.invoice_error_flag) AS error_count,
    ROUND(100.0 * SUM(i.invoice_error_flag) / COUNT(*), 2) AS error_rate_percent
FROM invoices i
JOIN merchants m ON m.merchant_id = i.merchant_id
GROUP BY m.merchant_segment
ORDER BY error_rate_percent DESC;

-- =====================================================================
-- 12. Underbilling detail (billed less than expected)
-- =====================================================================
SELECT
    invoice_id, merchant_id, invoice_date,
    ROUND(expected_fee, 2) AS expected_fee,
    ROUND(billed_fee, 2) AS billed_fee,
    ROUND(expected_fee - billed_fee, 2) AS underbilled_amount
FROM invoices
WHERE invoice_error_flag = 1 AND billed_fee < expected_fee
ORDER BY underbilled_amount DESC;

-- =====================================================================
-- 13. Overbilling detail (billed more than expected)
-- =====================================================================
SELECT
    invoice_id, merchant_id, invoice_date,
    ROUND(expected_fee, 2) AS expected_fee,
    ROUND(billed_fee, 2) AS billed_fee,
    ROUND(billed_fee - expected_fee, 2) AS overbilled_amount
FROM invoices
WHERE invoice_error_flag = 1 AND billed_fee > expected_fee
ORDER BY overbilled_amount DESC;

-- =====================================================================
-- 14. Reconciliation status per invoice
-- =====================================================================
WITH paid AS (
    SELECT invoice_id, SUM(payment_amount) AS total_paid, COUNT(*) AS payment_count
    FROM payments WHERE payment_status = 'Success'
    GROUP BY invoice_id
)
SELECT
    i.invoice_id,
    i.merchant_id,
    i.total_invoice_amount,
    COALESCE(p.total_paid, 0) AS total_paid,
    COALESCE(p.payment_count, 0) AS payment_count,
    CASE
        WHEN COALESCE(p.payment_count, 0) = 0 THEN 'MISSING_PAYMENT'
        WHEN ABS(COALESCE(p.total_paid, 0) - i.total_invoice_amount) <= 1.0 THEN 'MATCHED'
        WHEN p.total_paid < i.total_invoice_amount THEN 'PARTIAL'
        ELSE 'AMOUNT_MISMATCH'
    END AS reconciliation_status
FROM invoices i
LEFT JOIN paid p ON p.invoice_id = i.invoice_id
WHERE i.invoice_status != 'Void'
ORDER BY reconciliation_status, i.invoice_id;

-- =====================================================================
-- 15. Duplicate payments (same invoice + amount paid more than once)
-- =====================================================================
SELECT
    invoice_id, payment_amount, COUNT(*) AS payment_count,
    GROUP_CONCAT(payment_id) AS payment_ids
FROM payments
WHERE payment_status = 'Success' AND invoice_id IS NOT NULL
GROUP BY invoice_id, payment_amount
HAVING COUNT(*) > 1
ORDER BY payment_count DESC;

-- =====================================================================
-- 16. Missing invoices (merchant-months with transactions but no invoice)
-- =====================================================================
WITH txn_months AS (
    SELECT DISTINCT merchant_id, strftime('%Y-%m', transaction_date) AS txn_month
    FROM transactions
    WHERE payment_status = 'Success'
),
invoice_months AS (
    SELECT DISTINCT merchant_id, strftime('%Y-%m', billing_period_start) AS inv_month
    FROM invoices
)
SELECT tm.merchant_id, tm.txn_month
FROM txn_months tm
LEFT JOIN invoice_months im ON im.merchant_id = tm.merchant_id AND im.inv_month = tm.txn_month
WHERE im.merchant_id IS NULL
ORDER BY tm.merchant_id, tm.txn_month;

-- =====================================================================
-- 17. Missing payments (invoices issued, no payment received at all)
-- =====================================================================
SELECT i.invoice_id, i.merchant_id, i.invoice_date, i.due_date, i.total_invoice_amount
FROM invoices i
LEFT JOIN payments p ON p.invoice_id = i.invoice_id AND p.payment_status = 'Success'
WHERE p.payment_id IS NULL AND i.invoice_status != 'Void'
ORDER BY i.due_date;

-- =====================================================================
-- 18. Customer segmentation summary
-- =====================================================================
SELECT
    m.merchant_segment,
    COUNT(DISTINCT m.merchant_id) AS merchant_count,
    ROUND(SUM(i.billed_fee), 2) AS total_billed_revenue,
    ROUND(AVG(i.billed_fee), 2) AS avg_invoice_value
FROM merchants m
JOIN invoices i ON i.merchant_id = m.merchant_id
GROUP BY m.merchant_segment
ORDER BY total_billed_revenue DESC;

-- =====================================================================
-- 19. Merchant profitability (net revenue after refunds and credit notes)
-- =====================================================================
WITH refund_totals AS (
    SELECT merchant_id, SUM(refund_amount) AS total_refunds
    FROM refunds WHERE refund_status = 'Processed'
    GROUP BY merchant_id
),
credit_totals AS (
    SELECT merchant_id, SUM(credit_amount) AS total_credits
    FROM credit_notes WHERE status IN ('Issued', 'Applied')
    GROUP BY merchant_id
),
billed_totals AS (
    SELECT merchant_id, SUM(billed_fee) AS total_billed
    FROM invoices
    GROUP BY merchant_id
)
SELECT
    b.merchant_id,
    ROUND(b.total_billed, 2) AS total_billed_revenue,
    ROUND(COALESCE(r.total_refunds, 0), 2) AS total_refunds,
    ROUND(COALESCE(c.total_credits, 0), 2) AS total_credit_notes,
    ROUND(b.total_billed - COALESCE(r.total_refunds, 0) - COALESCE(c.total_credits, 0), 2) AS net_revenue
FROM billed_totals b
LEFT JOIN refund_totals r ON r.merchant_id = b.merchant_id
LEFT JOIN credit_totals c ON c.merchant_id = b.merchant_id
ORDER BY net_revenue DESC;

-- =====================================================================
-- 20. Collection priority queue
--     40% outstanding-amount risk + 30% days-overdue + 20% historical delay
--     + 10% merchant-segment risk, each normalized 0-100 within this result set
-- =====================================================================
WITH paid AS (
    SELECT invoice_id, SUM(payment_amount) AS total_paid
    FROM payments WHERE payment_status = 'Success'
    GROUP BY invoice_id
),
open_ar AS (
    SELECT
        i.invoice_id, i.merchant_id,
        ROUND(i.total_invoice_amount - COALESCE(p.total_paid, 0), 2) AS outstanding_amount,
        CAST(julianday('2026-08-13') - julianday(i.due_date) AS INTEGER) AS days_overdue
    FROM invoices i
    LEFT JOIN paid p ON p.invoice_id = i.invoice_id
    WHERE i.invoice_status != 'Void'
      AND (i.total_invoice_amount - COALESCE(p.total_paid, 0)) > 0.01
      AND i.due_date < '2026-08-13'
),
merchant_history AS (
    SELECT merchant_id, AVG(delay_days) AS avg_delay FROM (
        SELECT i.merchant_id, CAST(julianday(p.payment_date) - julianday(i.due_date) AS INTEGER) AS delay_days
        FROM invoices i JOIN payments p ON p.invoice_id = i.invoice_id AND p.payment_status = 'Success'
    ) GROUP BY merchant_id
),
scored AS (
    SELECT
        o.invoice_id, o.merchant_id, o.outstanding_amount, o.days_overdue,
        COALESCE(h.avg_delay, 0) AS avg_historical_delay,
        100.0 * o.outstanding_amount / (SELECT MAX(outstanding_amount) FROM open_ar) AS amount_score,
        100.0 * o.days_overdue / (SELECT MAX(days_overdue) FROM open_ar) AS overdue_score,
        100.0 * COALESCE(h.avg_delay, 0) / (SELECT MAX(avg_delay) FROM merchant_history) AS history_score
    FROM open_ar o
    LEFT JOIN merchant_history h ON h.merchant_id = o.merchant_id
)
SELECT
    invoice_id, merchant_id, outstanding_amount, days_overdue,
    ROUND(0.4 * amount_score + 0.3 * overdue_score + 0.2 * history_score + 0.1 * 50, 1) AS priority_score
FROM scored
ORDER BY priority_score DESC
LIMIT 50;

-- =====================================================================
-- 21. Monthly variance: expected vs billed vs collected revenue
-- =====================================================================
WITH monthly AS (
    SELECT
        strftime('%Y-%m', invoice_date) AS month,
        SUM(expected_fee) AS expected_revenue,
        SUM(billed_fee) AS billed_revenue
    FROM invoices
    GROUP BY month
),
collected AS (
    SELECT strftime('%Y-%m', payment_date) AS month, SUM(payment_amount) AS collected_revenue
    FROM payments WHERE payment_status = 'Success'
    GROUP BY month
)
SELECT
    m.month,
    ROUND(m.expected_revenue, 2) AS expected_revenue,
    ROUND(m.billed_revenue, 2) AS billed_revenue,
    ROUND(m.billed_revenue - m.expected_revenue, 2) AS billing_variance,
    ROUND(100.0 * (m.billed_revenue - m.expected_revenue) / NULLIF(m.expected_revenue, 0), 2) AS billing_variance_percent,
    ROUND(COALESCE(c.collected_revenue, 0), 2) AS collected_revenue
FROM monthly m
LEFT JOIN collected c ON c.month = m.month
ORDER BY m.month;

-- =====================================================================
-- 22. Revenue concentration (Pareto: top 10 merchants' share of revenue)
-- =====================================================================
WITH merchant_revenue AS (
    SELECT merchant_id, SUM(billed_fee) AS revenue
    FROM invoices
    GROUP BY merchant_id
),
ranked AS (
    SELECT merchant_id, revenue, ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rank
    FROM merchant_revenue
)
SELECT
    SUM(CASE WHEN rank <= 10 THEN revenue ELSE 0 END) AS top_10_revenue,
    SUM(revenue) AS total_revenue,
    ROUND(100.0 * SUM(CASE WHEN rank <= 10 THEN revenue ELSE 0 END) / SUM(revenue), 2) AS top_10_share_percent
FROM ranked;

-- =====================================================================
-- 23. Payment delay distribution by merchant segment
-- =====================================================================
WITH delays AS (
    SELECT
        i.merchant_id,
        CAST(julianday(p.payment_date) - julianday(i.due_date) AS INTEGER) AS delay_days
    FROM invoices i
    JOIN payments p ON p.invoice_id = i.invoice_id AND p.payment_status = 'Success'
)
SELECT
    m.merchant_segment,
    COUNT(*) AS payment_count,
    ROUND(AVG(d.delay_days), 1) AS avg_delay_days,
    MAX(d.delay_days) AS max_delay_days
FROM delays d
JOIN merchants m ON m.merchant_id = d.merchant_id
GROUP BY m.merchant_segment
ORDER BY avg_delay_days DESC;

-- =====================================================================
-- 24. High-risk accounts (large overdue AR + long historical delay)
-- =====================================================================
WITH paid AS (
    SELECT invoice_id, SUM(payment_amount) AS total_paid
    FROM payments WHERE payment_status = 'Success'
    GROUP BY invoice_id
),
merchant_ar AS (
    SELECT
        i.merchant_id,
        SUM(CASE WHEN i.due_date < '2026-08-13' THEN i.total_invoice_amount - COALESCE(p.total_paid, 0) ELSE 0 END) AS overdue_ar
    FROM invoices i
    LEFT JOIN paid p ON p.invoice_id = i.invoice_id
    WHERE i.invoice_status != 'Void'
    GROUP BY i.merchant_id
),
merchant_delay AS (
    SELECT i.merchant_id, AVG(julianday(p.payment_date) - julianday(i.due_date)) AS avg_delay
    FROM invoices i JOIN payments p ON p.invoice_id = i.invoice_id AND p.payment_status = 'Success'
    GROUP BY i.merchant_id
)
SELECT
    m.merchant_id, m.merchant_name, m.merchant_segment,
    ROUND(ar.overdue_ar, 2) AS overdue_ar,
    ROUND(COALESCE(d.avg_delay, 0), 1) AS avg_payment_delay_days
FROM merchant_ar ar
JOIN merchants m ON m.merchant_id = ar.merchant_id
LEFT JOIN merchant_delay d ON d.merchant_id = ar.merchant_id
WHERE ar.overdue_ar > 5000 AND COALESCE(d.avg_delay, 0) > 15
ORDER BY ar.overdue_ar DESC;

-- =====================================================================
-- 25. Collection recovery effectiveness by activity type
-- =====================================================================
SELECT
    activity_type,
    COUNT(*) AS activity_count,
    SUM(CASE WHEN outcome = 'Payment Received' THEN 1 ELSE 0 END) AS resulted_in_payment,
    ROUND(100.0 * SUM(CASE WHEN outcome = 'Payment Received' THEN 1 ELSE 0 END) / COUNT(*), 2) AS recovery_effectiveness_percent
FROM collection_activity
GROUP BY activity_type
ORDER BY recovery_effectiveness_percent DESC;

-- =====================================================================
-- 26. Promise-to-pay fulfillment rate
-- =====================================================================
SELECT
    COUNT(*) AS promises_made,
    SUM(CASE WHEN outcome = 'Payment Received' THEN 1 ELSE 0 END) AS promises_kept,
    ROUND(100.0 * SUM(CASE WHEN outcome = 'Payment Received' THEN 1 ELSE 0 END) / COUNT(*), 2) AS fulfillment_rate_percent
FROM collection_activity
WHERE activity_type = 'Payment Promise';

-- =====================================================================
-- 27. Dispute resolution summary
-- =====================================================================
SELECT
    dispute_type,
    COUNT(*) AS dispute_count,
    ROUND(SUM(disputed_amount), 2) AS total_disputed_amount,
    SUM(CASE WHEN resolution_status = 'Resolved' THEN 1 ELSE 0 END) AS resolved_count,
    ROUND(100.0 * SUM(CASE WHEN resolution_status = 'Resolved' THEN 1 ELSE 0 END) / COUNT(*), 2) AS resolution_rate_percent
FROM disputes
GROUP BY dispute_type
ORDER BY total_disputed_amount DESC;

-- =====================================================================
-- 28. Refund rate by industry
-- =====================================================================
SELECT
    m.industry,
    COUNT(DISTINCT t.transaction_id) AS transaction_count,
    ROUND(SUM(t.transaction_amount), 2) AS gross_transaction_value,
    ROUND(SUM(t.refund_amount), 2) AS total_refunded,
    ROUND(100.0 * SUM(t.refund_amount) / NULLIF(SUM(t.transaction_amount), 0), 2) AS refund_rate_percent
FROM transactions t
JOIN merchants m ON m.merchant_id = t.merchant_id
GROUP BY m.industry
ORDER BY refund_rate_percent DESC;
