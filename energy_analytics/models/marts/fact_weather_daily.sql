-- Daily weather fact. Grain: one row per region per day. Shares the conformed
-- dim_date and dim_region with consumption, so the two can be analyzed together
-- (e.g. consumption vs temperature) by joining on (date, region_code).

with temp as (
    select * from {{ ref('stg_temperature') }}
)

select
    date,
    region_code,
    t_min_c,
    t_max_c,
    t_mean_c
from temp
