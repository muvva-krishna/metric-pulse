SELECT
    order_item_id,
    order_id,
    sku,
    quantity,
    unit_price_usd,
    ingested_at
FROM {{ source('raw', 'order_items') }}
