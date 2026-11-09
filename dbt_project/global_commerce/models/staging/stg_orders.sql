with source as (
    select * from {{ source('silver', 'orders') }}
)

select
    order_id,
    customer_id,
    cast(order_ts as timestamp) as order_ts,
    cast(order_date as date) as order_date,
    quantity,
    unit_price,
    currency,
    product_sku,
    gross_sales,
    recognized_revenue
from source
