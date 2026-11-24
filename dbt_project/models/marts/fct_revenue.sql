SELECT
    order_id,
    account_id,
    user_id,
    order_date,
    net_revenue_usd,
    region,
    plan_tier,
    payment_gateway
FROM {{ ref('int_orders_enriched') }}
WHERE status = 'completed'
