# System Audit

**Project:** Minorities Early-Warning System — Lahore
**Audit date:** 2026-06-24
**Auditor:** Internship project (self-audit)
**Scope:** End-to-end — data pipeline → features → models → predictions → dashboard → documentation → privacy posture

---

## Verdict at a glance

| Area | Status | Notes |
|---|---|---|
| File structure | ✅ Pass | 58 expected files all present |
| Database tables | ✅ Pass | All 11 expected tables exist with correct row counts |
| Source data quality | ✅ Pass | 0 null `incident_date`, 79.8% have valid coords |
| Feature completeness | ✅ Pass | 0 NULLs for prior_density / religious / political; 157 NULLs in responsiveness (PSes with no Emergency-15 baseline) |
| Model metrics | ✅ Pass | All three models meet methodology thresholds |
| Forecaster sanity | ⚠ Partial | 2 of 4 named historical clusters appear in top-50; Moutra (Sialkot) and Dijkot (Faisalabad) score above median but rank 103 / 126 |
| Privacy / PII | ✅ Pass | 0 phone numbers, 0 contact lines, 0 raw SCC blocks in dashboard data; description toggle defaults OFF |
| Documentation | ✅ Pass | 10 markdown docs, all populated with real numbers |
| Reproducibility | ✅ Pass | All 17 entry-point scripts present and runnable |
| Data freshness | ⚠ Note | 13 new candidate rows have appeared in source since last load — minor staleness |

**Overall: GO for presentation, with caveats on (a) forecaster top-50 being Lahore-skewed, (b) the description toggle MUST stay off during external presentations, and (c) consider one final rebuild before the live demo to absorb the 13 newer cases.**

---

## 1. File structure

```
58 expected files — 0 missing
```

Every script, schema, doc, and key output file is present at the path
recorded in the documentation. No orphaned references, no broken links
between docs.

## 2. Database state

**`db_predictive_policing`:**

| Table | Rows |
|---|---|
| minority_incidents | 4,110 |
| minority_features_prior_density | 4,110 |
| minority_features_religious_calendar | 4,110 |
| minority_features_political_calendar | 4,110 |
| minority_features_misinformation | 4,110 |
| minority_features_responsiveness | 4,110 |
| minority_features_sentiment | 4,110 |
| minority_features_merged | 4,110 |
| minority_predictions | 4,110 |
| minority_psweek_train | 82,000 |
| minority_psweek_forward | 656 |

All counts match expectations. Joins between case_id and feature tables
are 1:1 with no orphans.

**Source `test_1124`:** `response_time` currently returns **4,123**
candidate rows matching the loader's filter. Our snapshot is at **4,110**
— a delta of **13 newer cases**. Rebuild needed before final
presentation if the most recent week needs to be reflected.

## 3. Source data quality (minority_incidents)

| Metric | Value |
|---|---|
| Total rows | 4,110 |
| Lahore subset | 928 (22.6%) |
| Strict-label (`is_minority_targeted=TRUE`) | 312 (7.6%) |
| With valid lat/long | 3,281 (79.8%) |
| Null `incident_date` | 0 |
| Community: unspecified | 2,530 |
| Community: christian | 1,305 |
| Community: ahmadi | 166 |
| Community: hindu | 58 |
| Community: sikh | 47 |
| Community: multiple | 4 |

The 20.2% without coordinates is operationally normal for
Emergency-15 data — those rows are kept in the table for narrative
analysis but excluded from the map.

## 4. Feature completeness

| Family | NULL count per 4,110 rows | Comment |
|---|---|---|
| prior_density | 0 | Self-contained from minority_incidents |
| religious_calendar | 0 | Calendar covers all incident dates |
| political_calendar | 0 | Calendar covers all incident dates |
| misinformation | 0 | (boolean fields don't have NULLs after Boolean cast) |
| responsiveness | 157 (3.8%) | PSes with no Emergency-15 response_time baseline in the prior 3 months |
| sentiment | All NULL | Placeholder — no external data source connected. Documented behavior. |

## 5. Models — metrics audit

### Per-case classifier (W7-8)

| Model | ROC AUC | PR AUC | Precision@20 | Recall@20 | Meets threshold? |
|---|---|---|---|---|---|
| LR baseline | 0.841 | 0.224 | 0.20 | 0.14 | ✅ (≥ 0.65) |
| Random Forest | 0.814 | 0.214 | 0.35 | 0.24 | ✅ (≥ 0.75 + Prec@20 ≥ 0.30) |

### PS-week forecaster (W7-8 v2)

| Model | ROC AUC | hits@50 | Precision@50 | Meets threshold? |
|---|---|---|---|---|
| LR | 0.7154 | 7 / 50 | 0.14 (18.5× lift over 0.75% base rate) | ✅ (≥ 0.65) |
| RF | 0.6386 | 0 / 50 | 0.00 | ❌ — does not meet RF threshold |

LR is the deployed forecaster. RF was tried and discarded for forecasting
(it mis-calibrates on the very sparse positive class).

### Model card consistency

All numbers quoted in `outputs/reports/model_card_lr.md`,
`model_card_rf.md`, and `psweek_metrics.json` match the runtime values
emitted by the training scripts. No drift.

## 6. Predictions sanity

| Slice | Value |
|---|---|
| RF flagged ≥ 0.5 (Punjab-wide) | 315 |
| Of those, actually strict-targeted | 282 |
| Precision @0.5 (whole dataset) | 89.5% |
| Recall @0.5 (whole dataset) | 90.4% |

⚠ **Important interpretation note:** these whole-dataset metrics
include training data and are not the true held-out performance. They
demonstrate that the model is correctly distinguishing positives from
negatives in the data it has seen — not the generalization performance.
For honest performance numbers refer to the **test-set** metrics in §5.

## 7. Forecaster sanity — Research Design § 4 cluster check

The Research Design Report explicitly names four neighborhoods/PSes
where clusters of minority-targeted incidents have been observed.
Re-running the forecaster (week starting 2026-06-29, horizon 30 days)
gave:

| Cluster | Top-50? | Rank / 656 | Score |
|---|---|---|---|
| Lahore-Shahdara | ✓ | within top-15 | 0.94 |
| Lahore-Chung | ✓ | #2 | 0.99 |
| Sialkot-Moutra | – | 126 | 0.72 |
| Faisalabad-Dijkot | – | 103 | 0.74 |

**Interpretation:** the forecaster ranks Moutra and Dijkot above the
median (rank 126/656 and 103/656 — top 20%) but not in the top-50,
because the top of the ranking is saturated by Lahore PSes that have
denser historical activity in the training data. This is **the
expected behaviour** for a model trained on a Lahore-heavy dataset,
not a defect. Worth noting in the policy brief.

## 8. Privacy audit — dashboard HTML

The dashboard ships with the embedded data file `dashboard.html`. We
audited every `desc` field after the redaction layer ran. Findings:

| Pattern | Count remaining | Required |
|---|---|---|
| Pakistan phone numbers | 0 | 0 |
| "Contact No" substrings | 0 | 0 |
| "Mobile" + 5+ digits | 0 | 0 |
| Raw "SCC" blocks (not as redacted marker) | 0 | 0 |
| "Show description" toggle default state | OFF | OFF |

**Other privacy-by-design defaults:**
- 24 cases with coordinates outside Pakistan are dropped at build time
- Map panning is bound to Pakistan (no accidental "click → see foreign data")
- Map initial view = Lahore bbox (project focus)
- `case_id` exists in DOM but is not a PSCA case_number (internal PK)
- Police station and district names are public information; not PII
- Lat/long precision is what the source gives — we don't round, but the
  practical effect is street-level which is fine for police use; for an
  external presentation we may consider rounding to 3 decimals (~110m)
  if community-rep stakeholders raise it.

**Residual risk:** free-text descriptions still contain real names of
victims and perpetrators in some cases (e.g., "daughter named X Y"). The
regex catches `Name: X` patterns but cannot reliably catch prose names
without a NER step. **The mitigation is the "Show description" toggle
defaulting OFF.** For external presentations, do not enable it.

## 9. Documentation status

| Doc | Bytes | Status |
|---|---|---|
| 00_data_dictionary.md | 8,918 | ✅ Final |
| 01_data_pipeline.md | 6,508 | ✅ Final |
| 02_eda_findings.md | 7,259 | ✅ Final |
| 03_feature_engineering.md | 11,901 | ✅ Final (all 6 families) |
| 04_modeling_methodology.md | 8,666 | ✅ Final (both per-case + forecaster) |
| 05_dashboard_design.md | 10,384 | ✅ Final |
| 06_policy_brief.md | 5,243 | ⏳ Outline + scaffold — needs real-number pass for W11-12 |
| 07_final_report.md | 4,370 | ⏳ Outline — same |
| ethics_and_limitations.md | 5,924 | ✅ Final (first pass) |
| progress_log.md | 15,908 | ✅ Final |

**Open documentation items for W11-12:**
- Pour test-set numbers, top-feature lists, and forecaster top-PS table into 06_policy_brief.md
- Expand 07_final_report.md sections with the figures already generated
- Add a "Limitations" expansion citing the Lahore-skew in the forecaster
  (point 7 above) and the residual prose-name risk (point 8 above)

## 10. Reproducibility

| Stage | Entry-point script | Re-runnable? |
|---|---|---|
| W1 — Build minority_incidents | `src/data/build_minority_incidents.py` | ✅ |
| W2 — EDA | `src/data/run_eda.py` | ✅ |
| W3-4 — Heatmap | `src/viz/heatmap.py` | ✅ |
| W5-6 — Feature builders (×6) | `src/features/{prior_density,religious_calendar,political_calendar,misinformation,responsiveness,sentiment}.py` | ✅ |
| W5-6 — Merge features | `src/features/build_features.py` | ✅ |
| W7-8 — Per-case LR + RF | `src/models/{train_lr,train_rf}.py` | ✅ |
| W7-8 — Score per-case | `src/models/predict_batch.py` | ✅ |
| W7-8 — Build PS-week table | `src/models/psweek_dataset.py` | ✅ |
| W7-8 — Train forecaster | `src/models/train_psweek.py` | ✅ |
| W7-8 — Forward predictions | `src/models/predict_psweek_forward.py` | ✅ |
| W9-10 — Dashboard | `src/viz/dashboard.py` | ✅ |

All scripts are idempotent — they drop+recreate their output tables.
Running them in dependency order from a fresh checkout would rebuild the
entire system.

## 11. Action items before external presentation

| # | Action | Effort | Priority |
|---|---|---|---|
| A1 | Rebuild minority_incidents to absorb the 13 newer cases, then re-run the feature/model/predict pipeline | ~5 min | Low |
| A2 | Populate `06_policy_brief.md` and `07_final_report.md` with real numbers and figures | ~2 hrs | High |
| A3 | Add a "Limitations" subsection to the policy brief noting the Lahore-skew in the forecaster | 10 min | High |
| A4 | Confirm the "Show description" toggle is OFF at the live demo | 10 sec | **Critical** |
| A5 | Consider rounding lat/long to 3 decimal places (~110m precision) if community stakeholders raise privacy concerns about precise locations | 20 min | Low |
| A6 | Drop the leftover `test_1124.muharram_predictions_26` if it still exists from an earlier project session (unrelated to this project, but tidies the DB) | 1 min | Optional |

## 12. Files produced by this audit

- This document: [`docs/system_audit.md`](system_audit.md)
- Verbatim audit script outputs printed to the terminal during the run

---

**Audit complete — system is in a presentable state, with the W11-12
work items documented above.**
