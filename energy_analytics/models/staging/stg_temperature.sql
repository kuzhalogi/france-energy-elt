with source as (
    select * from {{ source('raw', 'temperature') }}
),

typed as (
    select
        nullif("date", '')::date        as date,
        nullif(region_code, '')::int    as region_code,
        region                           as region,
        nullif(t_min_c, '')::numeric    as t_min_c,
        nullif(t_max_c, '')::numeric    as t_max_c,
        nullif(t_mean_c, '')::numeric   as t_mean_c
    from source
)

select * from typed
