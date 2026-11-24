SELECT
    ticket_id,
    account_id,
    created_date,
    priority,
    category,
    ingested_at
FROM {{ source('raw', 'support_tickets') }}
