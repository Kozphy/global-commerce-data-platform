select
    f.customer_id,
    c.country,
    count(*) as order_count,
    sum(f.quantity) as units_sold,
    sum(f.gross_sales) as gross_sales,
    sum(f.recognized_revenue) as recognized_revenue,
    case when count(*) = 0 then 0 else sum(f.gross_sales) / count(*) end as avg_order_value
from {{ ref('fact_order') }} f
left join {{ ref('dim_customer') }} c on f.customer_id = c.customer_id
group by 1, 2
order by 1
