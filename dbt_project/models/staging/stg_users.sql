SELECT
    user_id,
    account_id,
    region,
    plan_tier,
    created_at,
    ingested_at
FROM {{ source('raw', 'users') }}
