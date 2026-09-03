-- Day 2: Growth, funnel, retention and unit economics analysis
-- Synthetic neobank dataset
-- Analysis window ends 2026-08-31

-- 1. Overall funnel
SELECT
    COUNT(DISTINCT c.customer_id) AS signups,
    COUNT(DISTINCT CASE
        WHEN k.status = 'approved' THEN c.customer_id
    END) AS kyc_approved,
    COUNT(DISTINCT a.customer_id) AS accounts_opened,
    COUNT(DISTINCT CASE
        WHEN pe.event_name = 'first_funding' THEN c.customer_id
    END) AS first_funding,
    COUNT(DISTINCT CASE
        WHEN pe.event_name = 'first_transaction' THEN c.customer_id
    END) AS first_transaction
FROM customers c
LEFT JOIN kyc_cases k
    ON c.customer_id = k.customer_id
LEFT JOIN accounts a
    ON c.customer_id = a.customer_id
LEFT JOIN product_events pe
    ON c.customer_id = pe.customer_id;

-- 2. Funnel conversion rates
WITH funnel AS (
    SELECT
        COUNT(DISTINCT c.customer_id) AS signups,
        COUNT(DISTINCT CASE
            WHEN k.status = 'approved' THEN c.customer_id
        END) AS kyc_approved,
        COUNT(DISTINCT a.customer_id) AS accounts_opened,
        COUNT(DISTINCT CASE
            WHEN pe.event_name = 'first_funding' THEN c.customer_id
        END) AS first_funding,
        COUNT(DISTINCT CASE
            WHEN pe.event_name = 'first_transaction' THEN c.customer_id
        END) AS first_transaction
    FROM customers c
    LEFT JOIN kyc_cases k
        ON c.customer_id = k.customer_id
    LEFT JOIN accounts a
        ON c.customer_id = a.customer_id
    LEFT JOIN product_events pe
        ON c.customer_id = pe.customer_id
)
SELECT
    ROUND(100.0 * kyc_approved / signups, 2) AS signup_to_kyc_pct,
    ROUND(100.0 * accounts_opened / kyc_approved, 2) AS kyc_to_account_pct,
    ROUND(100.0 * first_funding / accounts_opened, 2) AS account_to_funding_pct,
    ROUND(100.0 * first_transaction / first_funding, 2) AS funding_to_transaction_pct
FROM funnel;

-- 3. KYC approval by acquisition channel
SELECT
    c.acquisition_channel,
    COUNT(*) AS signups,
    COUNT(*) FILTER (WHERE k.status = 'approved') AS kyc_approved,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE k.status = 'approved') / COUNT(*),
        2
    ) AS kyc_approval_pct
FROM customers c
JOIN kyc_cases k
    ON c.customer_id = k.customer_id
GROUP BY c.acquisition_channel
ORDER BY kyc_approval_pct DESC;

-- 4. Account to funding by acquisition channel
SELECT
    c.acquisition_channel,
    COUNT(DISTINCT a.customer_id) AS accounts_opened,
    COUNT(DISTINCT CASE
        WHEN pe.event_name = 'first_funding' THEN c.customer_id
    END) AS funded_customers,
    ROUND(
        100.0 * COUNT(DISTINCT CASE
            WHEN pe.event_name = 'first_funding' THEN c.customer_id
        END) / COUNT(DISTINCT a.customer_id),
        2
    ) AS account_to_funding_pct
FROM customers c
JOIN accounts a
    ON c.customer_id = a.customer_id
LEFT JOIN product_events pe
    ON c.customer_id = pe.customer_id
GROUP BY c.acquisition_channel
ORDER BY account_to_funding_pct DESC;

-- 5. Signup to funding by acquisition channel
-- EXISTS prevents product_event duplication from inflating signup counts.
SELECT
    c.acquisition_channel,
    COUNT(*) AS signups,
    COUNT(*) FILTER (
        WHERE EXISTS (
            SELECT 1
            FROM product_events pe
            WHERE pe.customer_id = c.customer_id
              AND pe.event_name = 'first_funding'
        )
    ) AS funded_customers,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE EXISTS (
                SELECT 1
                FROM product_events pe
                WHERE pe.customer_id = c.customer_id
                  AND pe.event_name = 'first_funding'
            )
        ) / COUNT(*),
        2
    ) AS signup_to_funding_pct
FROM customers c
GROUP BY c.acquisition_channel
ORDER BY signup_to_funding_pct DESC;

-- 6. Customer acquisition cost by channel
WITH signups AS (
    SELECT
        acquisition_channel,
        COUNT(*) AS customers_acquired
    FROM customers
    GROUP BY acquisition_channel
),
spend AS (
    SELECT
        acquisition_channel,
        SUM(spend_gbp) AS total_spend_gbp
    FROM marketing_spend
    GROUP BY acquisition_channel
)
SELECT
    s.acquisition_channel,
    s.customers_acquired,
    ROUND(sp.total_spend_gbp, 2) AS total_spend_gbp,
    ROUND(sp.total_spend_gbp / s.customers_acquired, 2) AS cac_gbp
FROM signups s
JOIN spend sp
    ON s.acquisition_channel = sp.acquisition_channel
ORDER BY cac_gbp ASC;

-- 7. Cost per funded customer
WITH funded AS (
    SELECT
        c.acquisition_channel,
        COUNT(*) FILTER (
            WHERE EXISTS (
                SELECT 1
                FROM product_events pe
                WHERE pe.customer_id = c.customer_id
                  AND pe.event_name = 'first_funding'
            )
        ) AS funded_customers
    FROM customers c
    GROUP BY c.acquisition_channel
),
spend AS (
    SELECT
        acquisition_channel,
        SUM(spend_gbp) AS total_spend_gbp
    FROM marketing_spend
    GROUP BY acquisition_channel
)
SELECT
    f.acquisition_channel,
    f.funded_customers,
    ROUND(s.total_spend_gbp, 2) AS total_spend_gbp,
    ROUND(
        s.total_spend_gbp / f.funded_customers,
        2
    ) AS cost_per_funded_customer_gbp
FROM funded f
JOIN spend s
    ON f.acquisition_channel = s.acquisition_channel
ORDER BY cost_per_funded_customer_gbp ASC;

-- 8. D30 retention by acquisition channel
-- D30 retained = >=3 completed non-funding transactions during days 30-59.
WITH first_funding AS (
    SELECT
        a.customer_id,
        MIN(t.transaction_ts) AS first_funding_ts
    FROM accounts a
    JOIN transactions t
        ON a.account_id = t.account_id
    WHERE t.transaction_type = 'cash_in'
      AND t.status = 'completed'
    GROUP BY a.customer_id
),
eligible AS (
    SELECT
        ff.customer_id,
        ff.first_funding_ts,
        c.acquisition_channel
    FROM first_funding ff
    JOIN customers c
        ON ff.customer_id = c.customer_id
    WHERE ff.first_funding_ts <= TIMESTAMP '2026-07-02 23:59:59'
),
activity AS (
    SELECT
        e.customer_id,
        e.acquisition_channel,
        COUNT(t.transaction_id) AS d30_transactions
    FROM eligible e
    JOIN accounts a
        ON e.customer_id = a.customer_id
    LEFT JOIN transactions t
        ON a.account_id = t.account_id
       AND t.status = 'completed'
       AND t.transaction_type <> 'cash_in'
       AND t.transaction_ts >= e.first_funding_ts + INTERVAL '30 days'
       AND t.transaction_ts < e.first_funding_ts + INTERVAL '60 days'
    GROUP BY e.customer_id, e.acquisition_channel
)
SELECT
    acquisition_channel,
    COUNT(*) AS eligible_customers,
    COUNT(*) FILTER (WHERE d30_transactions >= 3) AS retained_d30,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE d30_transactions >= 3) / COUNT(*),
        2
    ) AS d30_retention_pct
FROM activity
GROUP BY acquisition_channel
ORDER BY d30_retention_pct DESC;

-- 9. Average completed transaction volume by channel
WITH customer_volume AS (
    SELECT
        a.customer_id,
        SUM(t.amount_gbp) AS transaction_volume_gbp
    FROM accounts a
    JOIN transactions t
        ON a.account_id = t.account_id
    WHERE t.status = 'completed'
    GROUP BY a.customer_id
)
SELECT
    c.acquisition_channel,
    COUNT(cv.customer_id) AS funded_customers,
    ROUND(AVG(cv.transaction_volume_gbp), 2) AS avg_transaction_volume_gbp
FROM customers c
JOIN customer_volume cv
    ON c.customer_id = cv.customer_id
GROUP BY c.acquisition_channel
ORDER BY avg_transaction_volume_gbp DESC;

-- 10. Average completed transaction frequency by channel
WITH customer_activity AS (
    SELECT
        a.customer_id,
        COUNT(*) AS completed_transactions
    FROM accounts a
    JOIN transactions t
        ON a.account_id = t.account_id
    WHERE t.status = 'completed'
    GROUP BY a.customer_id
)
SELECT
    c.acquisition_channel,
    COUNT(ca.customer_id) AS funded_customers,
    ROUND(AVG(ca.completed_transactions), 2) AS avg_completed_transactions
FROM customers c
JOIN customer_activity ca
    ON c.customer_id = ca.customer_id
GROUP BY c.acquisition_channel
ORDER BY avg_completed_transactions DESC;

-- 11. Revenue by transaction type
SELECT
    transaction_type,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed_transactions,
    ROUND(
        SUM(
            fee_revenue_gbp
            + interchange_revenue_gbp
            + fx_spread_revenue_gbp
        ) FILTER (WHERE status = 'completed'),
        2
    ) AS total_revenue_gbp
FROM transactions
GROUP BY transaction_type
ORDER BY total_revenue_gbp DESC;

-- 12. Contribution margin by transaction type
SELECT
    transaction_type,
    ROUND(
        SUM(
            fee_revenue_gbp
            + interchange_revenue_gbp
            + fx_spread_revenue_gbp
            - processing_cost_gbp
        ) FILTER (WHERE status = 'completed'),
        2
    ) AS contribution_margin_gbp
FROM transactions
GROUP BY transaction_type
ORDER BY contribution_margin_gbp DESC;

-- 13. Margin per completed transaction
SELECT
    transaction_type,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed_transactions,
    ROUND(
        AVG(
            fee_revenue_gbp
            + interchange_revenue_gbp
            + fx_spread_revenue_gbp
            - processing_cost_gbp
        ) FILTER (WHERE status = 'completed'),
        4
    ) AS avg_margin_per_transaction_gbp
FROM transactions
GROUP BY transaction_type
ORDER BY avg_margin_per_transaction_gbp DESC;

-- 14. FX users vs non-FX users
WITH customer_metrics AS (
    SELECT
        a.customer_id,
        BOOL_OR(
            t.transaction_type = 'fx_exchange'
            AND t.status = 'completed'
        ) AS used_fx,
        COUNT(*) FILTER (
            WHERE t.status = 'completed'
        ) AS completed_transactions,
        SUM(t.amount_gbp) FILTER (
            WHERE t.status = 'completed'
        ) AS transaction_volume_gbp,
        SUM(
            t.fee_revenue_gbp
            + t.interchange_revenue_gbp
            + t.fx_spread_revenue_gbp
            - t.processing_cost_gbp
        ) FILTER (
            WHERE t.status = 'completed'
        ) AS contribution_margin_gbp
    FROM accounts a
    JOIN transactions t
        ON a.account_id = t.account_id
    GROUP BY a.customer_id
)
SELECT
    CASE
        WHEN used_fx THEN 'FX user'
        ELSE 'Non-FX user'
    END AS customer_segment,
    COUNT(*) AS customers,
    ROUND(AVG(completed_transactions), 2) AS avg_completed_transactions,
    ROUND(AVG(transaction_volume_gbp), 2) AS avg_transaction_volume_gbp,
    ROUND(AVG(contribution_margin_gbp), 2) AS avg_contribution_margin_gbp
FROM customer_metrics
GROUP BY used_fx
ORDER BY avg_contribution_margin_gbp DESC;

-- 15. D30 retention: FX users vs non-FX users
WITH first_funding AS (
    SELECT
        a.customer_id,
        MIN(t.transaction_ts) AS first_funding_ts
    FROM accounts a
    JOIN transactions t
        ON a.account_id = t.account_id
    WHERE t.transaction_type = 'cash_in'
      AND t.status = 'completed'
    GROUP BY a.customer_id
),
eligible AS (
    SELECT
        ff.customer_id,
        ff.first_funding_ts
    FROM first_funding ff
    WHERE ff.first_funding_ts <= TIMESTAMP '2026-07-02 23:59:59'
),
customer_activity AS (
    SELECT
        e.customer_id,
        BOOL_OR(
            t.transaction_type = 'fx_exchange'
            AND t.status = 'completed'
        ) AS used_fx,
        COUNT(*) FILTER (
            WHERE t.status = 'completed'
              AND t.transaction_type <> 'cash_in'
              AND t.transaction_ts >= e.first_funding_ts + INTERVAL '30 days'
              AND t.transaction_ts < e.first_funding_ts + INTERVAL '60 days'
        ) AS d30_transactions
    FROM eligible e
    JOIN accounts a
        ON e.customer_id = a.customer_id
    JOIN transactions t
        ON a.account_id = t.account_id
    GROUP BY e.customer_id
)
SELECT
    CASE
        WHEN used_fx THEN 'FX user'
        ELSE 'Non-FX user'
    END AS customer_segment,
    COUNT(*) AS eligible_customers,
    COUNT(*) FILTER (WHERE d30_transactions >= 3) AS retained_d30,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE d30_transactions >= 3) / COUNT(*),
        2
    ) AS d30_retention_pct
FROM customer_activity
GROUP BY used_fx
ORDER BY d30_retention_pct DESC;

-- 16. FX user share by acquisition channel
WITH customer_fx AS (
    SELECT
        a.customer_id,
        BOOL_OR(
            t.transaction_type = 'fx_exchange'
            AND t.status = 'completed'
        ) AS used_fx
    FROM accounts a
    JOIN transactions t
        ON a.account_id = t.account_id
    GROUP BY a.customer_id
)
SELECT
    c.acquisition_channel,
    COUNT(*) AS funded_customers,
    COUNT(*) FILTER (WHERE cf.used_fx) AS fx_users,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE cf.used_fx) / COUNT(*),
        2
    ) AS fx_user_pct
FROM customers c
JOIN customer_fx cf
    ON c.customer_id = cf.customer_id
GROUP BY c.acquisition_channel
ORDER BY fx_user_pct DESC;

-- 17. Average contribution margin per funded customer by channel
WITH customer_margin AS (
    SELECT
        a.customer_id,
        SUM(
            t.fee_revenue_gbp
            + t.interchange_revenue_gbp
            + t.fx_spread_revenue_gbp
            - t.processing_cost_gbp
        ) AS contribution_margin_gbp
    FROM accounts a
    JOIN transactions t
        ON a.account_id = t.account_id
    GROUP BY a.customer_id
)
SELECT
    c.acquisition_channel,
    COUNT(cm.customer_id) AS funded_customers,
    ROUND(AVG(cm.contribution_margin_gbp), 2) AS avg_contribution_margin_gbp
FROM customers c
JOIN customer_margin cm
    ON c.customer_id = cm.customer_id
GROUP BY c.acquisition_channel
ORDER BY avg_contribution_margin_gbp DESC;

-- 18. Total contribution margin by acquisition channel
WITH customer_margin AS (
    SELECT
        a.customer_id,
        SUM(
            t.fee_revenue_gbp
            + t.interchange_revenue_gbp
            + t.fx_spread_revenue_gbp
            - t.processing_cost_gbp
        ) AS contribution_margin_gbp
    FROM accounts a
    JOIN transactions t
        ON a.account_id = t.account_id
    GROUP BY a.customer_id
)
SELECT
    c.acquisition_channel,
    ROUND(SUM(cm.contribution_margin_gbp), 2) AS total_contribution_margin_gbp
FROM customers c
JOIN customer_margin cm
    ON c.customer_id = cm.customer_id
GROUP BY c.acquisition_channel
ORDER BY total_contribution_margin_gbp DESC;

-- 19. Net contribution after acquisition spend
WITH customer_margin AS (
    SELECT
        a.customer_id,
        SUM(
            t.fee_revenue_gbp
            + t.interchange_revenue_gbp
            + t.fx_spread_revenue_gbp
            - t.processing_cost_gbp
        ) AS contribution_margin_gbp
    FROM accounts a
    JOIN transactions t
        ON a.account_id = t.account_id
    GROUP BY a.customer_id
),
margin_by_channel AS (
    SELECT
        c.acquisition_channel,
        SUM(cm.contribution_margin_gbp) AS total_margin_gbp
    FROM customers c
    JOIN customer_margin cm
        ON c.customer_id = cm.customer_id
    GROUP BY c.acquisition_channel
),
spend_by_channel AS (
    SELECT
        acquisition_channel,
        SUM(spend_gbp) AS acquisition_spend_gbp
    FROM marketing_spend
    GROUP BY acquisition_channel
)
SELECT
    m.acquisition_channel,
    ROUND(m.total_margin_gbp, 2) AS total_margin_gbp,
    ROUND(s.acquisition_spend_gbp, 2) AS acquisition_spend_gbp,
    ROUND(
        m.total_margin_gbp - s.acquisition_spend_gbp,
        2
    ) AS net_contribution_after_acquisition_gbp
FROM margin_by_channel m
JOIN spend_by_channel s
    ON m.acquisition_channel = s.acquisition_channel
ORDER BY net_contribution_after_acquisition_gbp DESC;
