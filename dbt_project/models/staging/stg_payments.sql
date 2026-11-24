SELECT
    payment_id,
    order_id,
    payment_gateway,
    payment_status,
    ingested_at
FROM {{ source('raw', 'payments') }}
