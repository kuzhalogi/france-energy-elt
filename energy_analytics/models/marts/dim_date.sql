-- Conformed date dimension covering the full daily range. Built with a native
-- Postgres generate_series spine (no dbt_utils dependency). One row per calendar
-- day; daily facts join on `date`.

with spine as (
    select generate_series(
        '2013-01-01'::date,
        '2026-12-31'::date,
        '1 day'::interval
    )::date as date
)

select
    date,
    to_char(date, 'YYYYMMDD')::int      as date_key,
    extract(year    from date)::int     as year,
    extract(quarter from date)::int     as quarter,
    extract(month   from date)::int     as month,
    extract(day     from date)::int     as day_of_month,
    extract(isodow  from date)::int     as day_of_week,   -- 1=Mon .. 7=Sun
    trim(to_char(date, 'Day'))          as day_name,
    trim(to_char(date, 'Month'))        as month_name,
    extract(isodow from date) in (6, 7) as is_weekend
from spine
