-- Half-hourly load (MW) rolled up to one row per region per day.
-- Each 30-min interval at P MW carries P * 0.5 MWh of energy, so daily energy
-- is sum(consumption_mw) * 0.5. We also keep load shape stats (peak/avg/min).

with half_hourly as (
    select * from {{ ref('stg_consumption_daily') }}
),

daily as (
    select
        date,
        region_code,
        sum(consumption_mw) * 0.5   as consumption_mwh,
        avg(consumption_mw)         as avg_load_mw,
        max(consumption_mw)         as peak_load_mw,
        min(consumption_mw)         as min_load_mw,
        count(*)                    as n_intervals
    from half_hourly
    group by date, region_code
)

select * from daily
