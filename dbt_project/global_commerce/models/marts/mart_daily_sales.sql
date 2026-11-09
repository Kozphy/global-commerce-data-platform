select
    order_date,
    count(*) as order_count,
    sum(quantity) as units_sold,
    sum(gross_sales) as gross_sales,
    sum(recognized_revenue) as recognized_revenue,
    case when count(*) = 0 then 0 else sum(gross_sales) / count(*) end as avg_order_value
from {{ ref('fact_order') }}
group by 1
order by 1
