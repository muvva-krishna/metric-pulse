SELECT
    event_date AS usage_date,
    user_id,
    account_id,
    region,
    plan_tier,
    COUNT(DISTINCT session_id) AS session_count
FROM {{ ref('stg_telemetry_eu') }}
WHERE session_id IS NOT NULL
GROUP BY event_date, user_id, account_id, region, plan_tier
