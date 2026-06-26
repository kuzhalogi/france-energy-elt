# Data Catalog

Describes every dataset in the project: where it comes from, what's in it, and
its known quirks. Read this first before touching the data.

## Where the data comes from

All energy data is pulled from ODRE (Open Data Réseaux Énergies), France's open
energy data portal, through its OpenDataSoft API. `scripts/extract.py` fetches
each dataset and writes raw CSVs into `data/raw/`. The columns arrive with ODRE's
technical names (lowercase, like `code_insee_region`, `statut_rte`); they get
renamed to plain English during preprocessing.

Five datasets feed the pipeline. Three more (population/commune files) are present
but not used see "Excluded data" below.

| File (in `data/raw/`)                    | Grain              | Role in pipeline           |
| ---------------------------------------- | ------------------ | -------------------------- |
| `econsumption-daily-regionale.csv`       | half-hourly × region | daily consumption fact   |
| `econsumption-annual-regionale.csv`      | annual × region    | annual consumption (trend) |
| `temperature-quotidienne-regionale.csv`  | daily × region     | weather fact               |
| `prod-region-annuelle-filiere.csv`       | annual × region    | production fact            |
| `prod-region-annuelle-enr.csv`           | annual × region    | renewable detail (staged)  |

## The join key

`code_insee_region` (the INSEE region code) is the join key across every dataset.
The 13 metropolitan regions:

| Code | Region                       |
| ---- | ---------------------------- |
| 11   | Île-de-France                |
| 24   | Centre-Val de Loire          |
| 27   | Bourgogne-Franche-Comté      |
| 28   | Normandie                    |
| 32   | Hauts-de-France              |
| 44   | Grand Est                    |
| 52   | Pays de la Loire             |
| 53   | Bretagne                     |
| 75   | Nouvelle-Aquitaine           |
| 76   | Occitanie                    |
| 84   | Auvergne-Rhône-Alpes         |
| 93   | Provence-Alpes-Côte d'Azur   |
| 94   | Corse (missing from daily)   |

**Known quirk:** Corsica (94) is absent from the daily consumption dataset but
present in all others. So daily consumption covers 12 regions; everything else
covers 13. This is a source limitation, not a bug.

## Daily electricity consumption

The main dataset. Half-hourly electricity consumption per region.

- File: `econsumption-daily-regionale.csv`
- Source: ODRE (`consommation-quotidienne-brute-regionale`)
- Size: ~2.8M rows, 2013-01-01 → 2026-03-31, unit MW
- Grain: one row per region per half-hour

Kept columns (technical name → cleaned name): `date_heure` → datetime,
`date` → date, `heure` → hour, `code_insee_region` → region_code,
`region` → region, `consommation_brute_electricite_rte` → consumption_mw,
`statut_rte` → status, `consommation_brute_totale` → consumption_total_mw.

Cleaning applied in preprocessing:
- Keep only rows where `statut_rte` is Définitif or Consolidé (drops ~36k
  unvalidated rows, ~1.3%).
- Drop rows flagged by ODRE (`flag_ignore != 'non'`) and one impossible negative
  reading.
- Everything else (gas columns, geo shapes) is dropped.

After cleaning: ~2.75M rows.

## Annual electricity consumption

Yearly consumption per region. Used for trend context, not the daily fact.

- File: `econsumption-annual-regionale.csv`
- Source: ODRE (`consommation-annuelle-brute-regionale`), 2013 → 2025, unit GWh
- Grain: one row per region per year (~169 rows, includes Corsica)

Kept: `annee` → year, `code_insee_region` → region_code, `region` → region,
`consommation_brute_electricite_rte` → consumption_gwh. Gas and geo columns dropped.

## Daily temperature

Daily temperature per region, from Météo-France via ODRE.

- File: `temperature-quotidienne-regionale.csv`
- Coverage: 2016 onward, ~48k rows, 13 regions, unit °C
- Grain: one row per region per day

Kept: `date` → date, `code_insee_region` → region_code, `region` → region,
`tmin` → t_min_c, `tmax` → t_max_c, `tmoy` → t_mean_c. The `id` column is dropped.

**Coverage note:** temperature starts in 2016 but consumption starts in 2013, so
2013–2015 consumption has no matching temperature.

## Annual production by source (filière)

The full supply-side energy mix per region nuclear, thermal, hydro, wind, solar,
bioenergy.

- File: `prod-region-annuelle-filiere.csv`
- Source: ODRE, 2008 → 2025, ~234 rows, unit GWh
- Grain: one row per region per year

Kept: `annee` → year, `code_insee_region` → region_code, `region` → region, and
the six source columns (`production_nucleaire` → nuclear_gwh, etc.). Geo columns dropped.

**Nuclear nulls are structural zeros** most regions have no nuclear plants, so a
null means "none", not "missing". Preprocessing fills these (and the other source
columns) with 0.

## Annual renewable production (ENR)

Renewable detail per region, including renewable gas (biogas) which the filière
file doesn't have.

- File: `prod-region-annuelle-enr.csv`
- Source: ODRE, 2008 → 2025, ~234 rows, unit GWh

Kept: `annee` → year, `nom_insee_region` → region, `code_insee_region` →
region_code, and the renewable columns (`production_totale_renouvelable` →
total_renewable_gwh, etc.).

**Current status:** this dataset is extracted, cleaned, and built into a dbt
staging model (`stg_production_enr`), but it is **not yet folded into a mart**.
The production fact currently uses the filière file only. Combining the two into a
renewable-share metric is a planned extension.

## Excluded data

- **Gas consumption** (NaTran / Teréga columns in the consumption files): dropped.
  Half to most of the values are null, and the two providers cover different
  regions, so it's unreliable for region-level analysis.
- **Geo columns** (`geo_shape_region`, `geo_point_region`): dropped. GeoJSON
  geometry with no analytical use here.
- **Population / commune files** (`population_data.csv`, `population_metadata.csv`,
  `v_commune_2026.csv`): present in `data/raw/` but unused. They're at commune
  level (not region), end in 2023, and would need a commune→region rollup to join.
  Kept for a possible future per-capita metric.

## Open issues

- Corsica missing from daily consumption (12 regions vs 13 elsewhere).
- Temperature starts 2016; 2013–2015 consumption has no temperature match.
- Production is annual while consumption is daily one production row covers a
  whole year for a region.
- ENR renewable detail is staged but not yet in a mart.
