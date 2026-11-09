{{
    config(
        materialized='incremental',
        unique_key='customer_id'
    )
}}

select
    customer_id,
    email,
    country,
    created_at,
    full_name,
    current_timestamp as loaded_at
from {{ ref('stg_customers') }}

{% if is_incremental() %}
    -- Only load rows that were updated since last run if we had a watermark
    -- However, since stg_customers is from a full silver file, we rely on unique_key for upsert
{% endif %}
