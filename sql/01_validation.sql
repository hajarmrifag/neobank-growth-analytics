SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL
SELECT 'kyc_cases', COUNT(*) FROM kyc_cases
UNION ALL
SELECT 'accounts', COUNT(*) FROM accounts
UNION ALL
SELECT 'marketing_spend', COUNT(*) FROM marketing_spend
UNION ALL
SELECT 'experiment_assignments', COUNT(*) FROM experiment_assignments
UNION ALL
SELECT 'product_events', COUNT(*) FROM product_events
ORDER BY table_name;

SELECT status, COUNT(*) AS customers
FROM kyc_cases
GROUP BY status
ORDER BY customers DESC;

SELECT event_name, COUNT(*) AS events
FROM product_events
GROUP BY event_name
ORDER BY events DESC;

SELECT acquisition_channel, COUNT(*) AS signups
FROM customers
GROUP BY acquisition_channel
ORDER BY signups DESC;

SELECT variant, COUNT(*) AS assigned_customers
FROM experiment_assignments
GROUP BY variant
ORDER BY variant;
