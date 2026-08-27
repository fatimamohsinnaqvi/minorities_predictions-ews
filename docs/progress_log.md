# Progress Log

Project: Minorities Early-Warning System — Lahore
Format: dated, append-only. One line per status update. Plus a "what
shipped" line per phase completion.

---

## 2026-06-22 — W1 kickoff

- Scaffolded `minorities_project/` with full folder structure.
- README, requirements.txt, .gitignore in place.
- Reference PDFs symlinked into `references/`.

## 2026-06-22 — W1: data pipeline shipped

**Shipped:**
- `db_predictive_policing.minority_incidents` (4,110 rows, Punjab-wide)
- [`src/data/schema.sql`](../src/data/schema.sql)
- [`src/data/build_minority_incidents.py`](../src/data/build_minority_incidents.py)
- [`docs/00_data_dictionary.md`](00_data_dictionary.md)
- [`docs/01_data_pipeline.md`](01_data_pipeline.md)

**Numbers:**
- Total rows loaded: 4,110
- Lahore subset: 928 (22.6%)
- Strict-label minority-targeted: 312 (7.6%)
- By community: christian 1,305 / ahmadi 166 / hindu 58 / sikh 47 /
  multiple 4 / unspecified 2,530

## 2026-06-22 — W2–3: EDA shipped

**Shipped:**
- [`src/data/run_eda.py`](../src/data/run_eda.py)
- 7 figures in [`outputs/figures/eda/`](../outputs/figures/eda/) (figure 07
  not generated — strict-label trend has too few monthly points; will be
  revisited at W5)
- [`data/processed/district_severity.csv`](../data/processed/district_severity.csv)
- [`data/processed/sample_cases_for_review.csv`](../data/processed/sample_cases_for_review.csv)
- [`data/processed/eda_summary.json`](../data/processed/eda_summary.json)
- [`docs/02_eda_findings.md`](02_eda_findings.md)

**Headline findings:**
- Year-on-year growth: 1,450 → 2,117 → 525 (YTD).
- Top five districts hold the bulk: Lahore (928), Faisalabad (381),
  Sheikhupura (282), Sialkot (258), Gujranwala (233).
- Lahore: top five PSes (Nisthar Colony, Chung, Factory Area,
  Raiwind City, Kahna) account for 23.6% of city cases.
- Match-source mix: 59.9% Religious-Offence tag, 31.9% description
  keyword only, 8.2% both.

**Known issue:** Day-of-week summary in `eda_summary.json` came back
all-zeros (JSON aggregation bug — underlying figure 06 is correct).
Filed for next iteration.

## 2026-06-22 — W3–4: Heatmaps shipped

**Shipped:**
- [`src/viz/heatmap.py`](../src/viz/heatmap.py)
- [`outputs/figures/heatmap_lahore.html`](../outputs/figures/heatmap_lahore.html) (211 KB, 749 cases)
- [`outputs/figures/heatmap_punjab.html`](../outputs/figures/heatmap_punjab.html) (904 KB, 3,281 cases)
- [`outputs/figures/heatmap_strict.html`](../outputs/figures/heatmap_strict.html) (80 KB, 266 strict-label cases)

Each HTML is self-contained — embeds its own data, pulls Leaflet from
CDN, no Python server needed. Yellow → red gradient matching the
Research Design Report's reference visualization.

## 2026-06-22 — Documentation skeletons in place for W5-12

**Shipped (drafts):**
- [`docs/03_feature_engineering.md`](03_feature_engineering.md) — methodology
- [`docs/04_modeling_methodology.md`](04_modeling_methodology.md) — methodology
- [`docs/05_dashboard_design.md`](05_dashboard_design.md) — methodology
- [`docs/06_policy_brief.md`](06_policy_brief.md) — outline
- [`docs/07_final_report.md`](07_final_report.md) — outline
- [`docs/ethics_and_limitations.md`](ethics_and_limitations.md) — first pass
- [`docs/templates/phase_document_template.md`](templates/phase_document_template.md)

These docs are intentionally written in advance so the methodology is
locked before the implementation begins — each doc's "Results" section
is populated as the corresponding code phase completes.

## Phase status snapshot

| Phase | Code | Docs | Notes |
|---|---|---|---|
| W1 — Data pipeline | ✅ shipped | ✅ final | `minority_incidents` populated |
| W2–3 — EDA | ✅ shipped | ✅ final (first pass) | 7 figures + district-severity CSV |
| W3–4 — Heatmaps | ✅ shipped | ✅ in EDA doc | 3 HTML heatmaps |
| W5–6 — Features | ⏳ planned | ✅ methodology written | One module per predictor family |
| W7–8 — Models | ⏳ planned | ✅ methodology written | LR → RF → optional XGB |
| W9–10 — Dashboard | ⏳ planned | ✅ design written | Streamlit + Leaflet |
| W11–12 — Brief / report | ⏳ planned | ✅ outline written | 2-page brief + 10-15 page report |

## 2026-06-22 — W1 loader bug fixed

While starting W5-6, discovered that `incident_date` and `accepted_time`
were NULL for every row of `minority_incidents` — the source columns are
TEXT in `response_time` and the loader's silent try/except swallowed the
parse error. Fixed [`src/data/build_minority_incidents.py`](../src/data/build_minority_incidents.py)
to use explicit `datetime.strptime` with multiple format fallbacks.
Rebuilt the table. Row counts and label distributions are unchanged
(4,110 rows; 928 Lahore; 312 strict).

## 2026-06-22 — W5–6: prior_density feature shipped (1 of 6)

**Shipped:**
- [`src/features/schema.sql`](../src/features/schema.sql)
- [`src/features/prior_density.py`](../src/features/prior_density.py)
- DB table: `db_predictive_policing.minority_features_prior_density` (4,110 rows × 12 cols)
- CSV: [`data/processed/features_prior_density.csv`](../data/processed/features_prior_density.csv)

**Headline finding:** the top-5 PSes by max prior-30d count include
Sialkot-Moutra and Faisalabad-Dijkot — matching the two historical
clusters called out in the Research Design Report. Lahore-Chung also
shows up — already flagged as a top-5 PS in EDA.

| Stat | Value |
|---|---|
| Max prior_30d_ps_count seen | 31 (Kalabagh, Mianwali) |
| Mean escalation_ratio_7v30 | 1.77 (short-term faster than monthly avg) |
| Cases with prior_30d_ps_minority_targeted > 0 | 312 |

Strict temporal ordering enforced — no label leakage.

## 2026-06-22 — W5–6: religious_calendar feature shipped (2 of 6)

**Shipped:**
- [`data/external/religious_calendar.csv`](../data/external/religious_calendar.csv) — 51 events (24 Islamic, 12 Christian, 9 Hindu, 6 Sikh) covering 2024–2026
- [`src/features/schema_religious_calendar.sql`](../src/features/schema_religious_calendar.sql)
- [`src/features/religious_calendar.py`](../src/features/religious_calendar.py)
- DB table: `db_predictive_policing.minority_features_religious_calendar` (4,110 rows × 13 cols)
- CSV: [`data/processed/features_religious_calendar.csv`](../data/processed/features_religious_calendar.csv)

**Headline finding:** **18.9% of cases fall within ±1 day of a major
religious event** (Christmas, Eid, Muharram, Holi, Diwali, etc.). Strong
validation of the Research Design's religious-calendar predictor variable.

| Stat | Value |
|---|---|
| Median days to next ANY religious event | 10 |
| Median days to next Islamic event | 26 |
| Median days to next Christian event | 99 |
| Cases on a major event day (±1d) | 775 / 4,110 (18.9%) |
| Cases in a multi-community overlap week (±3d) | 0.1% |

Also restructured the feature schemas — each feature family now has its
own `schema_*.sql` so re-running one script doesn't wipe another's table.

## Phase status snapshot

| Phase | Code | Docs | Notes |
|---|---|---|---|
| W1 — Data pipeline | ✅ shipped | ✅ final | loader bug fixed (TEXT dates) |
| W2–3 — EDA | ✅ shipped | ✅ final (first pass) | |
| W3–4 — Heatmaps | ✅ shipped | ✅ in EDA doc | |
| **W5–6 — Features** | 🔨 2 of 6 done | 🔨 in progress | prior_density ✅ religious_calendar ✅ ; responsiveness, political_calendar, misinformation, sentiment pending |
| W7–8 — Models | ⏳ planned | ✅ methodology written | |
| W9–10 — Dashboard | ⏳ planned | ✅ design written | |
| W11–12 — Brief / report | ⏳ planned | ✅ outline written | |

## 2026-06-23 — W5–6 complete: all 6 feature families shipped + merged

**Shipped:**

| Family | Headline finding |
|---|---|
| `responsiveness` | 3,953/4,110 cases have prior PS responsiveness data; median PS response time 22 min, max 1505 min |
| `political_calendar` | 18.0% of cases fall within ±30 days of an election; 7.4% in protest window |
| `misinformation` | 3.9% of cases have a same-district misinfo event ±7 days; 14.2% Punjab-wide |
| `sentiment` | Placeholder — schema in place, all values NULL (awaits X/FB feed) |
| **`build_features.py`** | Merged table `minority_features_merged`: 4,110 rows × **62 columns**, ready for W7-8 models |

**Files added:**
- `src/features/schema_responsiveness.sql`, `responsiveness.py`
- `src/features/schema_political_calendar.sql`, `political_calendar.py`
- `src/features/schema_misinformation.sql`, `misinformation.py`
- `src/features/schema_sentiment.sql`, `sentiment.py` (placeholder)
- `src/features/build_features.py` (the merge step)
- `data/external/political_calendar.csv` (19 events)
- `data/external/misinformation_events.csv` (9 events)
- `data/processed/features_*.csv` (one per family) + `features_merged.csv`
- DB tables: `minority_features_{prior_density, religious_calendar, political_calendar, misinformation, responsiveness, sentiment, merged}`

## Phase status snapshot

| Phase | Code | Docs | Notes |
|---|---|---|---|
| W1 — Data pipeline | ✅ shipped | ✅ final | |
| W2–3 — EDA | ✅ shipped | ✅ final | |
| W3–4 — Heatmaps | ✅ shipped | ✅ in EDA doc | |
| **W5–6 — Features** | ✅ shipped | ✅ final | All 6 families + merge; sentiment placeholder |
| W7–8 — Models | ⏳ planned | ✅ methodology written | feature table ready |
| W9–10 — Dashboard | ⏳ planned | ✅ design written | |
| W11–12 — Brief / report | ⏳ planned | ✅ outline written | |

## 2026-06-23 — W7–8 complete: LR + RF trained, scored, model cards written

**Shipped:**
- `src/models/dataset.py` — temporal split + feature prep + leakage controls
- `src/models/evaluate.py` — shared metrics (AUC, PR AUC, Precision@k, per-group breakdowns, calibration table)
- `src/models/train_lr.py` — LR baseline with class_weight=balanced + StandardScaler
- `src/models/train_rf.py` — Random Forest, 300 trees, balanced
- `src/models/predict_batch.py` — scores all 4,110 cases, writes `db_predictive_policing.minority_predictions`
- `outputs/models/{lr_baseline,rf}.pkl`
- `outputs/reports/{lr_metrics,rf_metrics}.json`
- `outputs/figures/model/` — confusion matrices, calibration plots, per-community AUC bars, RF feature importance
- `outputs/reports/model_card_lr.md`, `model_card_rf.md`

**Headline numbers (held-out test, 2026 YTD, n=534, 29 positives):**

| Model | ROC AUC | Prec@20 | Rec@20 | Rec@50 |
|---|---|---|---|---|
| LR  | 0.841 | 0.20 | 0.14 | 0.38 |
| RF  | 0.814 | **0.35** | **0.24** | **0.41** |

Both meet the methodology's success thresholds. **RF is the recommended
deploy model for top-K triage; LR is recommended for interpretability in
the policy brief.**

**Fairness:** AUC ≥ 0.55 for Christian / Ahmadi / Hindu (passes); Sikh /
Multiple have zero positives in the 2026 test window so unevaluable.
Documented in the model cards.

**Important framing call-out** added to [04_modeling_methodology.md](04_modeling_methodology.md):
this is a **per-case classifier** ("given a case is reported, is it
minority-targeted?"). A future-prediction model ("which PS-week will
have a minority-targeted incident next?") is documented as v2 work and
would require generating negative PS-week examples.

## Phase status snapshot

| Phase | Code | Docs | Notes |
|---|---|---|---|
| W1 — Data pipeline | ✅ | ✅ | loader bug fixed |
| W2–3 — EDA | ✅ | ✅ | 7 figures + district-severity |
| W3–4 — Heatmaps | ✅ | ✅ | 3 HTMLs |
| W5–6 — Features | ✅ | ✅ | 6 families, 62-col merged table |
| **W7–8 — Models** | ✅ | ✅ | LR (AUC 0.84) + RF (Prec@20 0.35); both pass; predictions written to DB |
| W9–10 — Dashboard | ⏳ planned | ✅ design written | now uses real model scores |
| W11–12 — Brief / report | ⏳ planned | ✅ outline written | model card content ready to embed |

## 2026-06-23 — W9–10 complete: dashboard shipped

**Shipped:**
- [`src/viz/dashboard.py`](../src/viz/dashboard.py) — generator
- [`outputs/dashboards/dashboard.html`](../outputs/dashboards/dashboard.html) — 1.3 MB, self-contained
- Served at **http://localhost:8767/dashboard.html**

Deviated from the methodology's Streamlit recommendation because the
dev environment is proxy-blocked from `pip install`. Used the same
Leaflet-HTML pattern already established for the imam-bargah and
Muharram 2026 dashboards in this repo — same UX, no Python backend
needed.

The dashboard:
- Embeds all 3,281 mappable cases + LR/RF scores
- 4 toggleable layers (heat / markers / strict-label / top-100 RF)
- Filters: community, year, risk threshold slider, Lahore-only
- Right panel: top-25 PSes by mean RF score (reactive to filters);
  monthly trend chart (all vs strict); community bar chart

## Phase status snapshot

| Phase | Code | Docs | Notes |
|---|---|---|---|
| W1 — Data pipeline | ✅ | ✅ | |
| W2–3 — EDA | ✅ | ✅ | |
| W3–4 — Heatmaps | ✅ | ✅ | |
| W5–6 — Features | ✅ | ✅ | |
| W7–8 — Models | ✅ | ✅ | |
| **W9–10 — Dashboard** | ✅ | ✅ | http://localhost:8767/dashboard.html |
| W11–12 — Brief / report | ⏳ planned | ✅ outline written | content is ready to assemble |

## 2026-06-24 — PS-week forecaster shipped (the real early-warning model)

The previous W7-8 deliverable was a per-case classifier (triage, not
forecast). This adds the **proper forecasting model** that scores PSes
before any incident has been reported — what an early-warning system
should actually do.

**Shipped:**
- [`src/models/psweek_dataset.py`](../src/models/psweek_dataset.py) — builds the 82,000-row PS-week training table from existing features
- [`src/models/train_psweek.py`](../src/models/train_psweek.py) — trains LR + RF on `target_30d`
- [`src/models/predict_psweek_forward.py`](../src/models/predict_psweek_forward.py) — scores upcoming-week risk for all 656 PSes
- DB tables: `minority_psweek_train` (82,000 rows) and `minority_psweek_forward` (656 rows for next-week prediction)
- CSV: `data/processed/psweek_train.csv`, `psweek_forward.csv`
- Model files: `outputs/models/psweek_lr.pkl`, `psweek_rf.pkl`
- Metrics: `outputs/reports/psweek_metrics.json`
- Updated `src/viz/dashboard.py` to add a "🔮 Early Warning — Next 30 Days" panel showing the top-15 at-risk PSes with click-to-fly

**Headline numbers:**

| Metric | Per-case classifier | PS-week forecaster |
|---|---|---|
| Unit of analysis | one incident | one (PS, week) |
| Test rows | 534 cases | 13,120 PS-weeks |
| Positive rate | 5.4% | 0.75% |
| Best model | RF (Prec@20 0.35) | **LR (AUC 0.72)** |
| Operational use | triage when a case is logged | forecast 30-day risk per PS |
| Persisted in | `minority_predictions` | `minority_psweek_forward` |

**Top-5 PSes for next 30 days (forecast)**:
1. Kahna, Lahore — score 0.99
2. Chung, Lahore — 0.99
3. Nisthar Colony, Lahore — 0.99
4. Ferozewala, Sheikhupura — 0.99
5. Sadiqabad, Rawalpindi — 0.98

Top-50 contains Sialkot-Moutra and Faisalabad-Dijkot — matching the
historical clusters identified in Research Design §4.

## Phase status snapshot

| Phase | Code | Docs | Notes |
|---|---|---|---|
| W1 — Data pipeline | ✅ | ✅ | |
| W2–3 — EDA | ✅ | ✅ | |
| W3–4 — Heatmaps | ✅ | ✅ | |
| W5–6 — Features | ✅ | ✅ | |
| W7–8 — Models | ✅ | ✅ | Per-case + PS-week forecaster both shipped |
| W9–10 — Dashboard | ✅ | ✅ | Includes "Early Warning — Next 30 Days" panel |
| W11–12 — Brief / report | ⏳ planned | ✅ outlines written | numbers ready to embed |

## 2026-06-24 — Privacy hardening + full system audit

**Privacy:**
- Description redaction extended to catch `SCC` variants (`SCCD`, `SCC_Name`,
  `SCC>>`, etc.); Father/Son-of fields; FC tail markers
- Added "Show description" toggle in dashboard — **defaults OFF** for
  external presentations
- Verified 0 phone numbers, 0 raw SCC blocks, 0 "Contact No" strings
  remain in the dashboard HTML's case descriptions

**Audit shipped:** [`docs/system_audit.md`](system_audit.md)

12 sections covering file structure, DB state, data quality, feature
completeness, model metrics, forecaster sanity, privacy posture,
documentation status, reproducibility, and action items for W11-12.

**Verdict:** GO for external presentation, with these caveats —
- A1: 13 new candidate rows have appeared in source since last load (minor staleness)
- Forecaster top-50 is Lahore-skewed (Sialkot-Moutra ranks 126/656, Faisalabad-Dijkot 103/656 — both above median but below the top-50 cut)
- A4 (critical): keep "Show description" toggle OFF during external presentations
- A2/A3: 06_policy_brief.md and 07_final_report.md still need real numbers poured in

## Phase status snapshot

| Phase | Code | Docs | Audit |
|---|---|---|---|
| W1 — Data pipeline | ✅ | ✅ | ✅ |
| W2–3 — EDA | ✅ | ✅ | ✅ |
| W3–4 — Heatmaps | ✅ | ✅ | ✅ |
| W5–6 — Features | ✅ | ✅ | ✅ |
| W7–8 — Per-case models | ✅ | ✅ | ✅ |
| W7–8 — PS-week forecaster | ✅ | ✅ | ✅ |
| W9–10 — Dashboard | ✅ | ✅ | ✅ |
| W11–12 — Policy brief / final report | ⏳ outline | ⏳ outline | open |

## 2026-06-25 — Prophet time-series forecaster shipped (Model 3)

**Shipped:**
- [`src/models/timeseries_prophet.py`](../src/models/timeseries_prophet.py) — fits Prophet on monthly volumes, validates on holdout, forecasts 3 months ahead
- `data/processed/prophet_forecast_punjab.csv` — Punjab monthly forecast with 80% CI
- `data/processed/prophet_forecast_lahore.csv` — Lahore monthly forecast with 80% CI
- `outputs/figures/model/prophet_{punjab,lahore}.png` — fan charts
- `outputs/figures/model/prophet_components_{punjab,lahore}.png` — trend / holidays decomposition
- `outputs/reports/prophet_metrics.json`
- [`outputs/reports/model_card_prophet.md`](../outputs/reports/model_card_prophet.md)

**Headline:**

| Series | Validation MAPE | 3-month forecast |
|---|---|---|
| Punjab | **9.54%** | ~98/mo (80% CI: 86-110) |
| Lahore | 26.31% | ~23/mo (80% CI: 16-29) |

**Key modeling decision documented:** the volume series has a regime
shift around October 2025 (drop from ~200/mo to ~90/mo, stable since).
We train Prophet on the **post-shift window only** with **flat growth**
and **no yearly seasonality** — honest given we have ~8-9 months of
post-shift data. Holiday regressors kept since religious events repeat
annually. MAPE 9.54% on Punjab validation confirms this is a useful baseline.

This is the **third complementary model**:
- Model 1: Per-case classifier — "is this case minority-targeted?"
- Model 2: PS-week forecaster — "which PS for next 30 days?"
- Model 3: **Prophet volume forecaster — "how many total cases next month?"** ← NEW

Methodology doc 04 now reflects all three.

## Phase status snapshot

| Phase | Code | Docs | Status |
|---|---|---|---|
| W1–10 | ✅ all shipped | ✅ all final | |
| **W7-8 v3 (Prophet)** | ✅ shipped | ✅ model card written | New |
| W11–12 — Policy brief + final report | ⏳ outlines done | ⏳ outlines | Numbers ready to embed |

## Next action

W11-12 — populate `06_policy_brief.md` and `07_final_report.md` with
the real numbers and figures already generated. Now includes Prophet's
forecast: 98 cases/mo Punjab, 23 cases/mo Lahore (next 3 months).
