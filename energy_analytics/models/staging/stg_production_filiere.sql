with source as (
    select * from {{ source('raw', 'production_filiere') }}
),

typed as (
    select
        nullif(year, '')::int           as year,
        nullif(region_code, '')::int    as region_code,
        region                           as region,
        nullif(nuclear_gwh, '')::numeric   as nuclear_gwh,
        nullif(thermal_gwh, '')::numeric   as thermal_gwh,
        nullif(hydro_gwh, '')::numeric     as hydro_gwh,
        nullif(wind_gwh, '')::numeric      as wind_gwh,
        nullif(solar_gwh, '')::numeric     as solar_gwh,
        nullif(bioenergy_gwh, '')::numeric as bioenergy_gwh
    from source
)

select * from typed
