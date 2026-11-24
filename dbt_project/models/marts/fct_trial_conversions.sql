SELECT
    trial_id,
    user_id,
    trial_date,
    plan_tier,
    acquisition_channel,
    converted
FROM {{ ref('stg_trials') }}
