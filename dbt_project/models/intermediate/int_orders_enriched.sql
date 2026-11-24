WITH orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),
payments AS (
    SELECT
        order_id,
        MAX(payment_gateway) AS payment_gateway,
        MAX(payment_status) AS payment_status
    FROM {{ ref('stg_payments') }}
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.account_id,
    o.user_id,
    o.order_date,
    o.net_revenue_usd,
    o.region,
    o.plan_tier,
    o.status,
    p.payment_gateway,
    p.payment_status,
    o.ingested_at
FROM orders o
LEFT JOIN payments p ON o.order_id = p.order_id
