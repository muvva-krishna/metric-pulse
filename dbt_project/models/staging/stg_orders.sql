SELECT
    order_id,
    account_id,
    user_id,
    order_date,
    net_revenue_usd,
    region,
    plan_tier,
    status,
    ingested_at
FROM {{ source('raw', 'orders') }}
