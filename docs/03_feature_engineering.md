# 03 — Feature Engineering

**Phase:** W5–6
**Status:** ✅ All 6 feature families shipped (sentiment is a placeholder pending external data source)
**Last updated:** 2026-06-23

---

## Headline numbers

| Family | Status | Columns | DB table | Notes |
|---|---|---|---|---|
| Prior density | ✅ shipped | 11 | `minority_features_prior_density` | Self-contained from minority_incidents |
| Religious calendar | ✅ shipped | 12 | `minority_features_religious_calendar` | 51 events 2024-26 in CSV |
| Political calendar | ✅ shipped | 7 | `minority_features_political_calendar` | 19 events 2024-26 in CSV |
| Misinformation | ✅ shipped | 7 | `minority_features_misinformation` | 9 events (curated from Research Design + EDA) |
| Responsiveness | ✅ shipped | 6 | `minority_features_responsiveness` | 3-month prior PS-level avg from response_time |
| Social-media sentiment | 🟡 **placeholder** | 6 (NULL) | `minority_features_sentiment` | Awaiting X/Facebook feed |
| **Merged** | ✅ shipped | 62 | `minority_features_merged` | Training-ready, 4,110 rows |

Run all six + merge:
```bash
python3 minorities/minorities_project/src/features/prior_density.py
python3 minorities/minorities_project/src/features/religious_calendar.py
python3 minorities/minorities_project/src/features/political_calendar.py
python3 minorities/minorities_project/src/features/misinformation.py
python3 minorities/minorities_project/src/features/responsiveness.py
python3 minorities/minorities_project/src/features/sentiment.py        # placeholder
python3 minorities/minorities_project/src/features/build_features.py   # merge
```

Output goes to `db_predictive_policing.minority_features_merged` and
`data/processed/features_merged.csv`.

---

## Goal

Transform each row in `minority_incidents` into a feature vector that the
predictive model can consume in Phase 4. The Research Design Report
identifies six predictor families; this phase produces one feature
sub-module per family, all merged into a single training table:
`data/processed/features.parquet` (or .csv as fallback).

Each feature family lives in its own file in `src/features/` so it can be
re-run, version-controlled, and reviewed independently.

## Feature families (one module each)

### 1. Social media sentiment — `src/features/sentiment.py`

For each incident date + district, compute features from minority-mentioning
posts in a ±N-day window:

| Feature | Definition |
|---|---|
| `sm_post_count_7d` | Number of relevant minority-mentioning posts in the 7 days before the incident |
| `sm_negative_share_7d` | Share with negative VADER/Urdu-lexicon sentiment |
| `sm_post_count_30d` | Same, 30-day window |
| `sm_negative_share_30d` | Same, 30-day window |
| `sm_velocity` | `7d_count / 30d_count` — rate-of-acceleration |

Sources (in priority order):
1. X (Twitter) — if API access is set up
2. Facebook public posts — if a scraping pipeline is available
3. **Fallback for v1**: a static keyword-trend dataset from any existing
   sentiment API the institute has access to

If no social-media source is available, this module returns NULL for these
columns and the model treats them as missing — the system still runs.

### 2. Misinformation propagation — `src/features/misinformation.py`

| Feature | Definition |
|---|---|
| `misinfo_event_in_window` | 1 if a known misinformation event occurred in same district within 7 days |
| `misinfo_event_severity` | Manually-coded severity 1–3 per event |
| `days_since_last_misinfo_event` | Continuous, capped at 60 |

Source: a manually curated table `external/misinformation_events.csv` —
one row per known viral event with date, district, description, severity.
Bootstrap with publicly documented cases (Jaranwala 2023, etc.).

### 3. Political calendar — `src/features/political_calendar.py`

| Feature | Definition |
|---|---|
| `days_to_next_political_event` | Days until next election / by-election / major announcement |
| `days_since_last_political_event` | Symmetric backward window |
| `in_election_period` | 1 if within ±30 days of an election |
| `is_legislative_active_week` | 1 if Punjab Assembly was in session that week |

Source: `external/political_calendar.csv` — manually populated from
Election Commission of Pakistan + Punjab Assembly schedules. Static lookup.

### 4. Religious calendar density — `src/features/religious_calendar.py` ✅ SHIPPED

**Source:** [`data/external/religious_calendar.csv`](../data/external/religious_calendar.csv)
— 51 events covering 2024–2026 across 4 communities (24 Islamic, 12
Christian, 9 Hindu, 6 Sikh). Islamic moon-based dates are best-effort
approximations; can be refined with verified moon-sighting data.

**Shipped columns** (in `db_predictive_policing.minority_features_religious_calendar`):

| Feature | Definition |
|---|---|
| `days_to_next_islamic_event` | Days until next Islamic event |
| `days_to_next_christian_event` | Days until next Christian event |
| `days_to_next_hindu_event` | Days until next Hindu event |
| `days_to_next_sikh_event` | Days until next Sikh event |
| `days_to_next_any_event` | Days until next event of any community |
| `days_since_last_<community>_event` | Symmetric backward windows |
| `is_multi_religion_overlap_week` | 1 if two or more communities have events within ±3 days |
| `religious_density_score` | Weighted count of events in ±7-day window (major=2, observance=1) |
| `on_major_event_day` | 1 if case is within ±1 day of any major event |

**Headline finding from this run (Punjab, 4,110 cases):**

> **18.9% of all minority-related cases fall within ±1 day of a major
> religious event.** This is the empirical basis for keeping the
> religious-calendar variable in the model — a fifth of all incidents
> cluster around named, predictable dates.

**Distribution highlights:**

| Feature | mean | median | max |
|---|---|---|---|
| `days_to_next_islamic_event` | 42.1 | 26 | 150 |
| `days_to_next_christian_event` | 106.3 | 99 | 263 |
| `days_to_next_hindu_event` | 64.3 | 55 | 184 |
| `days_to_next_any_event` | 13.9 | 10 | 49 |
| `religious_density_score` | 1.49 | 2 | 6 |
| `on_major_event_day` | — | — | 18.9% share |

Median time to ANY religious event is just **10 days** — religious
events are dense enough in the calendar that this is more an indicator
of "is the case near a peak" than "how isolated is it."

**How to (re)run:**
```bash
python3 minorities/minorities_project/src/features/religious_calendar.py
```

### 5. Prior incident density — `src/features/prior_density.py` ✅ SHIPPED

Rolling counts per police-station and per-district. Computed directly from
`minority_incidents` via per-group binary-search windows. Self-contained,
no external data needed. **Strict temporal ordering** — only rows with an
`accepted_time` strictly less than the current case's are counted (ties
broken by `id`), preventing label leakage.

**Shipped columns** (in `db_predictive_policing.minority_features_prior_density`):

| Feature | Definition |
|---|---|
| `prior_7d_ps_count` | Cases in same `police_station_id`, last 7 days |
| `prior_30d_ps_count` | Same, 30-day window |
| `prior_60d_ps_count` | Same, 60-day window |
| `prior_90d_ps_count` | Same, 90-day window |
| `prior_7d_district_count` | Cases in same `district_id`, last 7 days |
| `prior_30d_district_count` | Same, 30-day window |
| `prior_60d_district_count` | Same, 60-day window |
| `prior_90d_district_count` | Same, 90-day window |
| `prior_30d_ps_minority_targeted` | Strict-label cases in same PS, 30d |
| `prior_30d_district_minority_targeted` | Strict-label cases in same district, 30d |
| `escalation_ratio_7v30` | `prior_7d_ps / (prior_30d_ps / 4)` — short-term spike detector. NULL when 30d count is 0. |

**Run results (4,110 cases, Punjab-wide):**

| Feature | mean | median | max |
|---|---|---|---|
| `prior_7d_ps_count` | 0.53 | 0 | 31 |
| `prior_30d_ps_count` | 0.97 | 0 | 31 |
| `prior_60d_ps_count` | 1.50 | 1 | 31 |
| `prior_90d_ps_count` | 1.97 | 1 | 31 |
| `prior_7d_district_count` | 4.15 | 2 | 39 |
| `prior_30d_district_count` | 15.21 | 8 | 78 |
| `prior_60d_district_count` | 29.00 | 16 | 142 |
| `prior_90d_district_count` | 42.42 | 22 | 194 |
| `prior_30d_ps_minority_targeted` | 0.10 | 0 | 6 |
| `prior_30d_district_minority_targeted` | 1.45 | 0 | 18 |
| `escalation_ratio_7v30` | 1.77 | 1 | 4 |

**Top-5 police stations by max prior_30d_ps_count** (places where the most
prior minority-related cases stacked up in any 30-day window):

| Prior cases | Police Station | District |
|---|---|---|
| 31 | Kalabagh | Mianwali |
| 19 | Chung | Lahore |
| 16 | Moutra | Sialkot |
| 14 | Dijkot | Faisalabad |
| 10 | Quaid-e-Azam Industrial Estate | Lahore |

The Sialkot-Moutra and Faisalabad-Dijkot entries match exactly with the
historical clusters identified in the Research Design Report §4.

**How to (re)run:**
```bash
python3 minorities/minorities_project/src/features/prior_density.py
```

Outputs both the DB table and a CSV at
`data/processed/features_prior_density.csv`.

### 6. Police responsiveness — `src/features/responsiveness.py`

| Feature | Definition |
|---|---|
| `avg_response_time_min_ps_90d` | Mean first-responder time per PS, last 90 days |
| `case_resolution_rate_ps_90d` | Share resolved within target window |
| `responsiveness_decile_ps` | Decile rank of PS among all Punjab PSes |

Source: PSCA `response_time` table (we have it). Compute once, cache per PS.

## Output table

```
data/processed/features.parquet     (or features.csv)

columns:
  case_id                                          (FK → minority_incidents.id)
  + all six feature families above
  + target columns: is_minority_targeted (label),
                    is_escalation_event (label for the model)
```

## Decisions and trade-offs

- **Missingness is treated as a signal, not an error.** If sentiment data
  is unavailable for a date, NULL is preserved; tree-based models handle
  this natively, and we'll use a sentinel for the linear baseline.

- **Features are computed at the row (incident) level, not the
  district-day level.** Reason: the eventual prediction unit will be
  "incident likelihood at a place × time", and the row-level features
  give that. Aggregated forms can be derived later for the heatmap.

- **External data tables are first-class.** Religious / political /
  misinformation calendars live in `data/external/` as small CSVs that
  can be hand-corrected when wrong dates are found. They're committed
  to git (small, non-sensitive).

## Limitations

- The Urdu/Punjabi sentiment lexicon is the weakest link — VADER is
  English-only; libraries like `multilingual-sentiment` are available
  but unevaluated on Pakistani Urdu specifically. The policy brief
  will explicitly flag low-confidence sentiment scores.

- Religious-calendar dates that depend on moon sighting (Eid, Muharram)
  may shift ±1 day from our pre-populated estimate.

- Prior-density features create a leakage risk: a case is partially
  predicted by counting prior cases in the same area. We will enforce
  strict time-ordering at train time — `prior_*` features computed using
  rows *strictly before* the incident's `accepted_time`.

## Next steps

- Implement modules in priority order: prior_density → religious_calendar
  → responsiveness → political_calendar → misinformation → sentiment
  (most reliable signals first, hardest external dependencies last).
- Run `make features` (or `python -m src.features.build_features`) to
  produce the merged `features.parquet`.
- Hand off to [04_modeling_methodology.md](04_modeling_methodology.md).

## References

- Source table: `db_predictive_policing.minority_incidents` ([dictionary](00_data_dictionary.md))
- Source for responsiveness: `test_1124.response_time`
- External tables: `data/external/*.csv` (planned)
- Research Design Report §3 (predictor framework)
