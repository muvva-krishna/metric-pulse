SELECT
    usage_date,
    region,
    plan_tier,
    COUNT(DISTINCT user_id) AS active_users,
    SUM(session_count) AS total_sessions
FROM {{ ref('int_daily_active_usage') }}
WHERE plan_tier = 'Enterprise'
GROUP BY usage_date, region, plan_tier
