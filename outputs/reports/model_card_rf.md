# Model Card — Random Forest

**Project:** Minorities Early-Warning System — Lahore
**Model file:** `outputs/models/rf.pkl`
**Trained at:** 2026-06-23
**Authors:** Internship project

---

## What this model does

Same classification task as the LR baseline ([model_card_lr.md](model_card_lr.md)):
given an incident's contextual features, output a probability that the
incident is minority-targeted in the strict sense (Religious Offence tag
AND minority community named in description).

Random Forest is run as the next rung of the model ladder per the
methodology doc (W7-8). It captures non-linear interactions between the
feature families and surfaces importance rankings useful for the
policy brief.

## Architecture

- `sklearn.ensemble.RandomForestClassifier`
- 300 trees, `min_samples_leaf=2`, `max_depth=None`,
  `class_weight='balanced'`, `random_state=42`
- Same 129-feature input as LR
- Same temporal train/test split (train 2024–2025, test 2026 YTD)

## Test-set metrics (2026 YTD, n=534)

| Metric | LR baseline | Random Forest |
|---|---|---|
| ROC AUC | 0.841 | **0.814** |
| PR AUC | 0.224 | 0.214 |
| Precision (@0.5) | 0.104 | 0.000 |
| Recall (@0.5) | 0.931 | 0.000 |
| F1 (@0.5) | 0.187 | 0.000 |
| TP / FP / FN / TN | 27 / 233 / 2 / 272 | 0 / 0 / 29 / 505 |
| **Precision@10** | 0.30 | 0.30 |
| **Recall@10** | 0.103 | 0.103 |
| **Precision@20** | 0.20 | **0.35** |
| **Recall@20** | 0.138 | **0.241** |
| **Precision@50** | 0.22 | **0.24** |
| **Recall@50** | 0.379 | **0.414** |

**Success threshold (per methodology): ROC AUC ≥ 0.75, Precision@20 ≥ 0.30 — passed.**

### Read this carefully

The RF model's `predict_proba` outputs are pushed toward 0.5 (typical for
RF), so a hard 0.5 threshold produces zero positive predictions. **This is
not a model failure — it's a calibration issue.** At the operationally
relevant top-K rankings, RF is **better than LR**:

- Top-20 ranking: RF gets 7 of 20 right (precision 0.35) vs LR's 4 of 20
  (0.20).
- Top-50 ranking: RF gets 12 of 50 right (0.24) vs LR's 11 (0.22).

For deployment, **use top-K ranking, not a 0.5 threshold.** The
recommended operational use is "show analysts the top-N highest-scored
incidents from yesterday."

## Per-community fairness (test set)

| Community | n | n_pos | ROC AUC | Precision@20 | Recall@20 |
|---|---|---|---|---|---|
| Ahmadi | 10 | 8 | 1.000 | 0.800 | 1.000 |
| Christian | 213 | 19 | 0.902 | 0.750 | 0.789 |
| Hindu | 11 | 2 | 1.000 | 0.182 | 1.000 |
| Multiple | 3 | 0 | n/a | 0.000 | 0.000 |
| Sikh | 5 | 0 | n/a | 0.000 | 0.000 |
| Unspecified | 292 | 0 | n/a | 0.000 | 0.000 |

**Fairness check passes** for the three evaluable communities (all
AUC ≥ 0.55). Cannot evaluate Sikh / Multiple due to zero positives in
the 2026 YTD test set.

## Top features by importance

| # | Feature | Importance |
|---|---|---|
| 1 | `level3_case_nature = Any Other Religious Issue` | 0.137 |
| 2 | `median_response_time_min_ps_90d` | 0.039 |
| 3 | `avg_response_time_min_ps_90d` | 0.036 |
| 4 | `n_cases_ps_90d` | 0.036 |
| 5 | `prior_60d_district_count` | 0.034 |
| 6 | `prior_90d_district_count` | 0.034 |
| 7 | `days_to_next_sikh_event` | 0.033 |
| 8 | `positive_feedback_rate_ps_90d` | 0.033 |
| 9 | `days_to_next_christian_event` | 0.032 |
| 10 | `prior_30d_district_count` | 0.031 |
| 11 | `days_to_next_hindu_event` | 0.030 |
| 12 | `days_to_next_political_event` | 0.030 |
| 13 | `days_to_next_major_political_event` | 0.030 |
| 14 | `days_since_last_political_event` | 0.030 |
| 15 | `days_since_last_major_political_event` | 0.030 |

The RF importance ranking is much more **spread out** than LR — no
single feature dominates beyond the level3 categorical. The responsiveness
family contributes meaningfully (positions 2, 3, 4, 8), reinforcing the
Research Design hypothesis that **PS-level structural responsiveness is
a real predictor**. Political and religious calendar features also pull
weight, supporting the cyclic-event predictor families.

## Pick a winner

| Criterion | LR | RF | Recommendation |
|---|---|---|---|
| AUC | 0.841 ✓ | 0.814 ✓ | LR slightly better |
| Top-K precision/recall | weaker | **stronger** | **RF** |
| Calibration at 0.5 threshold | better | poor | LR |
| Feature interpretability | direct (coef sign) | mean-decrease-impurity | LR easier for non-technical readers |
| Captures non-linear interactions | no | yes | RF |
| Fairness across communities | passes | passes | tie |

**Operational recommendation: deploy RF for top-K triage.** Report both
in the final report. The LR coefficients are useful for the policy brief
because they're directly interpretable ("misinformation proximity adds
+0.57 to the log-odds of a minority-targeted case").

## Limitations

Same as the LR baseline:

1. Per-case classification, not place×time forecast.
2. `level3_case_nature` carries the strongest signal — model is largely
   refining the operational tag.
3. Test set is small (n=534) with only 29 positives.
4. Sentiment features unused (placeholder).
5. Cannot evaluate fairness for Sikh / Multiple in 2026 YTD.

## Predictions stored at

`db_predictive_policing.minority_predictions` — one row per case with
both `lr_score` and `rf_score`, regenerated by
[`src/models/predict_batch.py`](../../src/models/predict_batch.py).

## References

- Methodology: [`docs/04_modeling_methodology.md`](../../docs/04_modeling_methodology.md)
- LR card: [`outputs/reports/model_card_lr.md`](model_card_lr.md)
- Ethics: [`docs/ethics_and_limitations.md`](../../docs/ethics_and_limitations.md)
