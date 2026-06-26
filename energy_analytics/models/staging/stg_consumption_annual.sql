with source as (
    select * from {{ source('raw', 'consumption_annual') }}
),

typed as (
    select
        nullif(year, '')::int               as year,
        nullif(region_code, '')::int        as region_code,
        region                               as region,
        nullif(consumption_gwh, '')::numeric as consumption_gwh
    from source
)

select * from typed
