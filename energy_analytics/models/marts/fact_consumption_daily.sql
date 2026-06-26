-- Daily electricity consumption fact. Grain: one row per region per day.
-- FKs: date -> dim_date.date, region_code -> dim_region.region_code.

with daily as (
    select * from {{ ref('int_consumption_daily') }}
)

select
    date,
    region_code,
    consumption_mwh,
    avg_load_mw,
    peak_load_mw,
    min_load_mw,
    n_intervals
from daily
