with source as (
    select * from {{ source('raw', 'production_enr') }}
),

typed as (
    select
        nullif(year, '')::int                          as year,
        nullif(region_code, '')::int                   as region_code,
        region                                          as region,
        nullif(hydro_renewable_gwh, '')::numeric       as hydro_renewable_gwh,
        nullif(bioenergy_renewable_gwh, '')::numeric   as bioenergy_renewable_gwh,
        nullif(wind_renewable_gwh, '')::numeric        as wind_renewable_gwh,
        nullif(solar_renewable_gwh, '')::numeric       as solar_renewable_gwh,
        nullif(electricity_renewable_gwh, '')::numeric as electricity_renewable_gwh,
        nullif(gas_renewable_gwh, '')::numeric         as gas_renewable_gwh,
        nullif(total_renewable_gwh, '')::numeric       as total_renewable_gwh
    from source
)

select * from typed
