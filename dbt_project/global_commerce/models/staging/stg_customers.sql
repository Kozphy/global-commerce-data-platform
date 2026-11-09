with source as (
    select * from {{ source('silver', 'customers') }}
)

select
    customer_id,
    email,
    country,
    cast(created_at as timestamp) as created_at,
    full_name
from source
