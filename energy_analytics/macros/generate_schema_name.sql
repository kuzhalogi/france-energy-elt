{#
  By default dbt-postgres builds models into "<target_schema>_<custom_schema>"
  (e.g. public_staging). This override makes a model with +schema: staging land
  in exactly "staging", and one with no custom schema fall back to the target
  schema. That gives clean raw / staging / marts schemas in the database.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
