SELECT
    checkout_session_id,
    user_id,
    event_date,
    region,
    device_os,
    payment_gateway,
    app_version,
    converted,
    timeout_ms
FROM {{ ref('stg_checkout_events') }}
