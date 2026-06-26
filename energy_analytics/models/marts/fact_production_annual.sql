-- Annual electricity production fact. Grain: one row per region per year.
-- Joins dim_region on region_code; year is the time key (annual grain, so it
-- does not use the daily dim_date).

with prod as (
    select * from {{ ref('stg_production_filiere') }}
)

select
    year,
    region_code,
    nuclear_gwh,
    thermal_gwh,
    hydro_gwh,
    wind_gwh,
    solar_gwh,
    bioenergy_gwh,
    coalesce(nuclear_gwh,0) + coalesce(thermal_gwh,0) + coalesce(hydro_gwh,0)
      + coalesce(wind_gwh,0) + coalesce(solar_gwh,0) + coalesce(bioenergy_gwh,0)
        as total_production_gwh
from prod
