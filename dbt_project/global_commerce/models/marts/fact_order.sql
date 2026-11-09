{{
    config(
        materialized='incremental',
        unique_key='order_id'
    )
}}

select
    order_id,
    customer_id,
    order_ts,
    order_date,
    quantity,
    unit_price,
    currency,
    product_sku,
    gross_sales,
    recognized_revenue,
    current_timestamp as loaded_at
from {{ ref('stg_orders') }}
