SELECT
    trial_id,
    user_id,
    trial_date,
    plan_tier,
    acquisition_channel,
    converted,
    ingested_at
FROM {{ source('raw', 'trials') }}
