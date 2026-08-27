# 00 — Data Dictionary: `minority_incidents`

**Project:** Minorities Early-Warning System — Lahore
**Database:** `db_predictive_policing`
**Table:** `minority_incidents`
**Source table:** `test_1124.response_time`
**Last updated:** 2026-06-22
**Status:** Final for W1 — to be expanded as new derived columns are added

---

## Purpose

`minority_incidents` is the working table for the Minorities Early-Warning
System. It holds every incident reported through PSCA Emergency-15 that is
likely to involve, target, or otherwise concern minority communities —
either because the case is officially categorised as a "Religious Offence"
or because its free-text description mentions a minority community,
religious site, or blasphemy-related term.

Every row is one incident. The table is the single input for all downstream
phases: EDA, feature engineering, the predictive model, the heatmap, and
the dashboard.

## Source and filtering rule

Rows are pulled from `test_1124.response_time` using the following filter:

```sql
WHERE level2_case_nature = 'Religious Offences'
   OR LOWER(description) ~ '(christian|ahmadi|hindu|sikh|qadia|church|gurdwara|temple|pastor|blasphem)'
```

This deliberately over-collects: it captures (a) officially-tagged religious
offences regardless of community, and (b) any case whose description mentions
a minority community even if the case is officially tagged as something else
(e.g. Theft, Public Disorder, Assault). The resulting set is wider than the
strict "minority-targeted" definition; a `is_minority_targeted` flag (see
below) is provided for the stricter subset.

Total rows on load: **4,110** (Punjab-wide). Lahore subset: **928**.

## Columns

### Identifiers

| Column | Type | Description | Source |
|---|---|---|---|
| `id` | SERIAL | Primary key, auto-assigned on load | local |
| `case_number` | TEXT | PSCA case number from Emergency-15 | `response_time.case_number` |
| `lead_id` | TEXT | Lead identifier (where applicable) | `response_time.lead_id` |

### Time

| Column | Type | Description | Source |
|---|---|---|---|
| `incident_date` | DATE | Date the incident was reported | `response_time.date` |
| `accepted_time` | TIMESTAMP | Timestamp when the call was accepted | `response_time.accepted_time` |
| `incident_year` | INTEGER | Year extracted from `incident_date` | derived |
| `incident_month` | INTEGER | Month (1–12) extracted from `incident_date` | derived |

### Location

| Column | Type | Description | Source |
|---|---|---|---|
| `district_id` | TEXT | Emergency-15 district id | `response_time.district_id` |
| `district_name` | TEXT | Resolved name (joined against `police_station_boundaries_v2`) | derived |
| `police_station_id` | TEXT | Police station id | `response_time.police_station_id` |
| `police_station` | TEXT | Police station name | `response_time.police_station` |
| `lat` | DOUBLE PRECISION | Latitude (decimal degrees) | `response_time.lat` |
| `long` | DOUBLE PRECISION | Longitude (decimal degrees) | `response_time.long` |
| `is_lahore` | BOOLEAN | `district_id = '40'` (project's focal scope) | derived |

### Case-nature taxonomy

| Column | Type | Description | Source |
|---|---|---|---|
| `level1_case_nature` | TEXT | Broad bucket (e.g. "Crime Against Person", "Law & Order") | `response_time.level1_case_nature` |
| `level2_case_nature` | TEXT | Mid-level (e.g. "Religious Offences") | `response_time.level2_case_nature` |
| `level3_case_nature` | TEXT | Specific category (e.g. "Defiling of Holy Book") | `response_time.level3_case_nature` |

The six `level3_case_nature` values that fall under "Religious Offences" are:

1. Any Other Religious Issue
2. Defiling of Holy Book
3. Derogation of Holy Persons
4. Distribution / Display of hateful sectarian material
5. Hate Speech
6. Attack/Damage of Religious Places (Church/Mosque/Gurdwara/Mundar/Imambargah/Mazzar)

### Free text and derived signals

| Column | Type | Description |
|---|---|---|
| `description` | TEXT | Caller's verbatim description of the incident |
| `match_source` | TEXT | How this row qualified: `religious_offence`, `desc_keyword`, or `both` |
| `matched_keywords` | TEXT[] | All keywords that hit in the description (lowercased) |
| `minority_community` | TEXT | Inferred from description: `christian`, `ahmadi`, `hindu`, `sikh`, `multiple`, or `unspecified` |
| `is_minority_targeted` | BOOLEAN | **Strict label**: `level2_case_nature = 'Religious Offences'` AND `minority_community` ∈ {christian, ahmadi, hindu, sikh, multiple} |

#### How `minority_community` is inferred

A case-insensitive regex pass over `description`:

| Pattern (regex word boundary) | Maps to |
|---|---|
| `christian`, `christians`, `church`, `churches`, `pastor`, `masihi`, `maseehi` | `christian` |
| `ahmadi`, `ahmedi`, `qadiani`, `qadiyani`, `qadian` | `ahmadi` |
| `hindu`, `hindus`, `mandir`, `mundir`, `temple` | `hindu` |
| `sikh`, `sikhs`, `gurdwara`, `gurudwara` | `sikh` |
| Two or more of the above patterns hit | `multiple` |
| None of the above patterns hit | `unspecified` |

Blasphemy/`gustakhi`/`tauhin*` terms are recorded in `matched_keywords` but
do not by themselves change `minority_community` from `unspecified`.

### Metadata

| Column | Type | Description |
|---|---|---|
| `loaded_at` | TIMESTAMP | When this row was loaded into the working table |

## Distributions (as of last load)

| Slice | Count |
|---|---|
| All rows | 4,110 |
| `is_lahore = TRUE` | 928 |
| `is_minority_targeted = TRUE` (strict) | 312 |
| `match_source = 'both'` | 335 |
| `match_source = 'religious_offence'` | 2,463 |
| `match_source = 'desc_keyword'` | 1,312 |

By community:

| `minority_community` | Count |
|---|---|
| unspecified | 2,530 |
| christian | 1,305 |
| ahmadi | 166 |
| hindu | 58 |
| sikh | 47 |
| multiple | 4 |

By year (`incident_date`):

| Year | Count |
|---|---|
| 2024 | 1,450 |
| 2025 | 2,117 |
| 2026 (YTD) | 525 |

## Known data-quality issues

1. **Free-text descriptions are operational, not analytical.** Spelling is
   inconsistent, language switches between English / Urdu / Roman Urdu
   within rows. Keyword detection is best-effort, not exact.

2. **`unspecified` ≠ "not minority-related".** Many Religious Offences rows
   have no community-naming keyword in the description because the caller
   referred to "they", "those people", a location, or used vernacular terms
   our regex misses. These cases are still in the table; downstream
   classification should not equate `unspecified` with "majority-victim".

3. **Latitude/longitude can be missing or imputed.** Roughly 20% of rows
   have no coordinates; some others may have police-station-centroid
   coordinates rather than the true incident location (a known issue in
   the upstream `response_time` table for older records).

4. **Reporting bias.** This is a reports-based dataset. Communities with
   lower trust in police may be under-represented; do not interpret zero
   reports as zero incidents.

5. **Severity is not pre-classified here.** The District Dataset Dictionary
   defines bands (Low 0–50, Medium 51–150, High 151–300, Critical 300+)
   based on aggregated *counts per district / category*. That severity
   metric is produced in a separate processed CSV (`data/processed/
   district_severity.csv`), not on this row-level table.

## How to query

```sql
\c db_predictive_policing

-- All Lahore minority incidents in 2026 so far
SELECT incident_date, level3_case_nature, police_station, minority_community,
       LEFT(description, 80) AS desc_preview
FROM minority_incidents
WHERE is_lahore AND incident_year = 2026
ORDER BY incident_date DESC;

-- High-confidence cases (strict label)
SELECT COUNT(*) FROM minority_incidents WHERE is_minority_targeted;

-- Christian-targeted cases by district
SELECT district_name, COUNT(*) AS n
FROM minority_incidents
WHERE minority_community = 'christian'
GROUP BY district_name ORDER BY n DESC;
```

## How to rebuild

```bash
python3 minorities/minorities_project/src/data/build_minority_incidents.py
```

The script reads from `test_1124.response_time`, applies the filter above,
derives the inferred columns, drops and recreates the table, and inserts
the resulting rows. Idempotent — every run produces the same `minority_
incidents` from a fixed source.

## References

- Source schema: `test_1124.response_time` (columns referenced above)
- Boundaries lookup: `db_predictive_policing.police_station_boundaries_v2`
- Reference design: [`../references/Research Design Report.pdf`](../references/Research%20Design%20Report.pdf)
- Reference dictionary (district-aggregate form): [`../references/District Dataset and Data Dictionary Report.pdf`](../references/District%20Dataset%20and%20Data%20Dictionary%20Report.pdf)
- Build script: [`../src/data/build_minority_incidents.py`](../src/data/build_minority_incidents.py)
- Schema DDL: [`../src/data/schema.sql`](../src/data/schema.sql)
