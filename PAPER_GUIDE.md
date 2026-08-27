# Paper Guide — writing the research paper from this repo

Everything you need to write the paper is already here. This maps each
section to the exact file, figure, and number to use. You do **not** need
to run any code to write the paper — the figures and numbers are
pre-generated. (If a reviewer wants reproduction, `bash run.sh` does it.)

Use the **honest, validated numbers** below — not the older single-cutoff
headline figures.

---

## Suggested structure and where each part comes from

| Section | Source in this repo |
|---|---|
| Introduction / problem | `docs/03_research_design_report.md` (question, hypotheses) |
| Related work / framing | `docs/03_research_design_report.md`, `docs/ethics_and_limitations.md` |
| Data | `docs/00_data_dictionary.md`, `docs/01_data_pipeline.md`; EDA in `docs/02_eda_findings.md` + `data/processed/eda_summary.json` |
| Features | `docs/03_feature_engineering.md` |
| Methods (models) | `docs/04_modeling_methodology.md` |
| Methods (validation) | `docs/08_temporal_validation.md` — rolling-origin + calibration |
| Results | `outputs/reports/*.json`, model cards, figures (below) |
| Limitations | `docs/ethics_and_limitations.md`, `docs/08_temporal_validation.md` |
| Ethics statement | `docs/ethics_and_limitations.md` |
| Data availability | see statement below |
| Reproducibility | `README.md` + `run.sh` |

---

## Figures (paper-ready PNGs in `outputs/figures/`)

**EDA (`outputs/figures/eda/`)**
- `01_cases_per_month.png` — temporal trend
- `02_top_districts.png` — geographic concentration
- `03_top_level3_categories.png` — incident types
- `04_minority_community_pie.png` — community breakdown
- `05_lahore_top_ps.png` — Lahore police-station hotspots
- `08_match_source.png` — how cases were identified

**Model (`outputs/figures/model/`)**
- `psweek_rolling_origin.png` — **key validation figure** (AUC + Precision@20 across six quarters)
- `psweek_calibration.png` — **key figure** (raw scores are miscalibrated; isotonic fixes it)
- `psweek_rf_importance.png` — forecaster feature importance
- `rf_feature_importance.png`, `lr_calibration.png`, `rf_cm_test.png`, `lr_per_community.png` — per-case model
- `prophet_punjab.png`, `prophet_lahore.png` — volume forecast

---

## Numbers to cite (honest, validated)

**Dataset:** 4,110 minority-related Emergency-15 cases (Punjab, Jan 2024–),
928 (22.6%) in Lahore, 312 (7.6%) strict-label minority-targeted.

**Per-case classifier (held-out 2026 test):**
- Logistic Regression: ROC AUC **0.84**, recall **0.93**, Precision@20 **0.20**
- Random Forest: ROC AUC **0.81**, Precision@20 **0.35**

**PS-week forecaster (rolling-origin, six quarters 2025Q1–2026Q2, 30-day embargo):**
- Mean ROC AUC **≈ 0.70** (range 0.62–0.75)
- Mean lift **≈ 10× at top-10, ≈ 7× at top-50**
- Precision@20 is **volatile: 0.20 down to 0.0** (two quarters caught nothing in top-20)
- Raw scores are **not calibrated** (mean predicted ≈ 0.58 for a 0.75%-rate event);
  treat as a ranking. Isotonic re-fit cuts calibration error ~30×.
- Source: `outputs/reports/psweek_temporal_eval.json`, `docs/08_temporal_validation.md`

**Volume forecaster (Prophet, Punjab):** validation MAPE **9.54%**.

> Do **not** cite "18.5× lift" or "89.5% precision" as headline results —
> the first is a single best-case quarter, the second is not reproducible
> from any split. Both are discussed honestly in `docs/08_temporal_validation.md`.

---

## Limitations to state explicitly (they strengthen the paper)

1. **Reporting bias.** The system predicts *reported* incidents. Communities
   with lower trust in police under-report and are under-flagged.
2. **Geographic skew.** Training data is Lahore-heavy, so top-ranked
   forecasts concentrate there.
3. **Calibration.** Raw risk scores rank well but are not probabilities
   without calibration.
4. **Small-sample fairness.** Per-community AUC is only reliably evaluable
   for the Christian subgroup (n=213); Ahmadi (n=10) / Hindu (n=11) are too
   small to trust.
5. **Placeholder features.** The social-media sentiment family is not
   connected to a live source.

---

## Data availability statement (suggested wording)

> The raw incident-level data used in this study are held by the Punjab
> Safe Cities Authority and contain personal information (caller
> descriptions, contact details); they cannot be shared publicly. Aggregated
> data (police-station × week counts, district severity, and event
> calendars) sufficient to reproduce the forecasting analysis are included
> in the project repository, along with all code and trained models.
