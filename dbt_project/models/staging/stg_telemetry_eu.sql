SELECT
    event_id,
    user_id,
    account_id,
    session_id,
    event_ts,
    event_date,
    region,
    plan_tier,
    ingested_at
FROM {{ source('raw', 'telemetry_eu') }}
