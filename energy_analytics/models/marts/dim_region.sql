-- Conformed region dimension. Unioned across every source so it carries all
-- 13 metropolitan regions, even though the daily consumption source omits
-- Corsica (94). region_code (INSEE) is the join key for every fact.

with all_regions as (
    select region_code, region from {{ ref('stg_consumption_daily') }}
    union
    select region_code, region from {{ ref('stg_consumption_annual') }}
    union
    select region_code, region from {{ ref('stg_temperature') }}
    union
    select region_code, region from {{ ref('stg_production_filiere') }}
    union
    select region_code, region from {{ ref('stg_production_enr') }}
),

deduped as (
    select
        region_code,
        max(region) as region_name   -- collapse any label variants
    from all_regions
    where region_code is not null
    group by region_code
)

select * from deduped
