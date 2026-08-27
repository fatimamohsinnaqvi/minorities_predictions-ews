# 01 — Data Pipeline

**Phase:** W1
**Status:** Final
**Last updated:** 2026-06-22

---

## Goal

Convert the operational `test_1124.response_time` table — 5.7 million
incident records — into a focused, project-scoped working table that
contains every incident relevant to the early-warning system for minority-
targeted crime in Lahore (and, for comparative context, the rest of Punjab).

The Research Design Report (Section 4) calls out a primary input dataset of
4,508 VCM cases. That dataset was not available on this machine; the
equivalent operational source — Emergency-15's `response_time` — was used
instead. The pipeline produces the same kind of structured input the
Research Design assumes.

## Method

### 1. Source

| Field | Value |
|---|---|
| Database | `test_1124` |
| Table | `response_time` |
| Total rows in source | ~5,697,000 |
| Years covered | 2024, 2025, 2026 (YTD) |

The source carries every Emergency-15 case across Punjab — `case_number`,
`lead_id`, `date`, `accepted_time`, `district_id`, `police_station`,
`lat`/`long`, three-level `case_nature` taxonomy, and the caller's
free-text `description`.

### 2. Filter rule

A union filter:

```sql
WHERE level2_case_nature = 'Religious Offences'
   OR LOWER(description) ~ '(christian|ahmadi|hindu|sikh|qadia|church|gurdwara|temple|pastor|blasphem)'
```

- The first clause captures the formally tagged subset (6 sub-categories
  under "Religious Offences": Defiling of Holy Book, Derogation of Holy
  Persons, Distribution / Display of Hateful Sectarian Material, Hate
  Speech, Attack/Damage of Religious Places, Any Other Religious Issue).
- The second clause picks up cases that mention a minority community by
  name but were tagged under a different category — Theft of church
  property, Assault on a pastor, harassment of an Ahmadi family, etc.
- The two clauses are intentionally OR'd: an early-warning system must
  err on the side of inclusion at the data-collection layer. Filtering
  to a stricter label is done later via the `is_minority_targeted` flag.

### 3. Per-row derivations

For each row pulled, the loader computes:

| Derived column | Logic |
|---|---|
| `district_name` | Lookup against `police_station_boundaries_v2.district_id`. |
| `is_lahore` | `district_id = '40'`. |
| `incident_year`, `incident_month` | Extracted from `incident_date`. |
| `match_source` | `'both'` if Religious-Offence AND keyword match, `'religious_offence'` or `'desc_keyword'` otherwise. |
| `matched_keywords` | `TEXT[]` — every minority/blasphemy keyword found in the description (lowercased). |
| `minority_community` | Inferred from description: `christian` / `ahmadi` / `hindu` / `sikh` / `multiple` / `unspecified`. See [00_data_dictionary.md](00_data_dictionary.md) for the exact regex. |
| `is_minority_targeted` | Strict label — `level2_case_nature = 'Religious Offences'` AND `minority_community` ∈ {christian, ahmadi, hindu, sikh, multiple}. |

### 4. Destination

| Field | Value |
|---|---|
| Database | `db_predictive_policing` |
| Table | `minority_incidents` |
| DDL | [`src/data/schema.sql`](../src/data/schema.sql) |
| Loader | [`src/data/build_minority_incidents.py`](../src/data/build_minority_incidents.py) |

The destination table is dropped and rebuilt on every loader run; there is
no partial / incremental load logic. The full source is small enough that
a full rebuild takes < 1 minute.

## Results

### Row counts

| Slice | Count |
|---|---|
| Total rows loaded | **4,110** |
| `is_lahore = TRUE` | **928** |
| `is_minority_targeted = TRUE` (strict) | **312** |

### Match-source distribution

| Source | Count | Share |
|---|---|---|
| `religious_offence` only | 2,463 | 59.9% |
| `desc_keyword` only | 1,312 | 31.9% |
| `both` | 335 | 8.2% |

### Inferred community

| Community | Count | Share |
|---|---|---|
| unspecified | 2,530 | 61.6% |
| christian | 1,305 | 31.8% |
| ahmadi | 166 | 4.0% |
| hindu | 58 | 1.4% |
| sikh | 47 | 1.1% |
| multiple | 4 | 0.1% |

### Year coverage

| Year | Count |
|---|---|
| 2024 | 1,450 |
| 2025 | 2,117 |
| 2026 (YTD) | 525 |

## Decisions and trade-offs

- **`response_time` over VCM**: We chose to use Emergency-15's master case
  table rather than the VCM (Virtual Center for Minorities) export
  referenced in the Research Design Report. Reason: the VCM file is not
  on this machine and obtaining it would block the pipeline. Trade-off:
  `response_time` lacks VCM-specific outcome and feedback fields, but it
  has lat/long, more cases, and the same free-text `description`. A
  follow-up phase can supplement once VCM data arrives.

- **Union filter, not intersection**: We deliberately over-collect at this
  layer so no minority-related incident is silently dropped. The strict
  label (`is_minority_targeted`) gives the model a clean positive class
  later; the broader set powers the dashboard and the policy analysis.

- **Regex-based community inference**: Quick, transparent, reproducible.
  Limitation: it can't catch incidents that don't name a community
  (e.g. "those people", local nicknames). Acceptable for v1; replaceable
  with an NER step in W5–6 (Feature Engineering).

## Limitations and known issues

1. ~20% of rows have NULL or invalid lat/long. These remain in the table
   for narrative analysis but are excluded from any map output.

2. Free-text quality is variable. English / Urdu / Roman Urdu mix.
   Spelling is operational, not edited. The regex misses many transliter-
   ation variants.

3. The strict label is conservative. 312 high-confidence Punjab rows is
   small; consider stratified sampling or class-weighted loss in models.

4. Severity bands defined in the District Data Dictionary are **count-
   based** (Low 0–50, Medium 51–150, High 151–300, Critical 300+). They
   conflate volume and intensity — a finding worth surfacing in the
   policy brief.

## Next steps

- Phase 2: EDA on `minority_incidents` — see [02_eda_findings.md](02_eda_findings.md).
- Production of `data/processed/district_severity.csv` (count-based bands)
  for the dashboard summary cards.

## References

- Build script: [`src/data/build_minority_incidents.py`](../src/data/build_minority_incidents.py)
- Schema DDL: [`src/data/schema.sql`](../src/data/schema.sql)
- Source: `test_1124.response_time`
- Destination: `db_predictive_policing.minority_incidents`
- Dictionary: [`00_data_dictionary.md`](00_data_dictionary.md)
- Research Design (parent folder): `../references/Research Design Report.pdf`
