with source as (
    select * from {{ source('raw', 'consumption_daily') }}
),

typed as (
    select
        nullif(datetime, '')::timestamp          as measured_at,
        nullif("date", '')::date                 as date,
        nullif(hour, '')::time                    as hour,
        nullif(region_code, '')::int             as region_code,
        region                                    as region,
        nullif(consumption_mw, '')::numeric      as consumption_mw,
        status                                    as status,
        nullif(consumption_total_mw, '')::numeric as consumption_total_mw
    from source
)

select * from typed
