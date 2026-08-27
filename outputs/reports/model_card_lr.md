# Model Card — Logistic Regression Baseline

**Project:** Minorities Early-Warning System — Lahore
**Model file:** `outputs/models/lr_baseline.pkl`
**Trained at:** 2026-06-23
**Authors:** Internship project

---

## What this model does

Given the contextual features of a reported incident in
`db_predictive_policing.minority_features_merged`, the model outputs a
probability that the incident is **minority-targeted** in the strict
sense: tagged as a Religious Offence AND mentioning a specific minority
community (Christian, Ahmadi, Hindu, Sikh, or multiple) in the caller's
free-text description.

**This is a per-case classifier, not a future-event predictor.** It runs
when an incident is already reported and provides a context-aware score
for triage. A separate place×time-forecast model (W7-8 v2) would be
required for true "next 7 days at PS X" early warning — see Limitations.

## Intended use

- Triage decision support for the Virtual Center for Minorities (VCM)
  team. When a new minority-related case is logged, the score helps
  rank attention.
- Analytical use in the policy brief — "of all minority-related
  incidents in Lahore in Q1 2026, the model flagged X% as
  high-confidence strict-label cases."

## NOT intended for

- Identifying individuals or specific suspects.
- Predicting future incidents at locations without a current report.
- Operational decisions without analyst review.
- Any deployment that would treat a high score as evidence rather than
  as a triage signal.

## Training data

| Field | Value |
|---|---|
| Source | `db_predictive_policing.minority_features_merged` |
| Rows | 4,110 (3,576 train + 534 test) |
| Train period | 2024–2025 |
| Test period | 2026 YTD (strict temporal holdout, no shuffle) |
| Target | `is_minority_targeted` (boolean) |
| Train class balance | 283 positives / 3,293 negatives (7.91% positive) |
| Test class balance | 29 positives / 505 negatives (5.43% positive) |

## Features

129 features after preprocessing, drawn from 5 active families
(sentiment was placeholder-only and is dropped):

- **Prior incident density** (11 cols) — rolling 7/30/60/90-day counts
  at PS and district level, strict-label variants, escalation ratio.
- **Religious calendar** (12 cols) — days-to-next + days-since-last per
  community, multi-religion overlap flag, density score, major-event-day
  flag.
- **Political calendar** (7 cols) — same shape over political events;
  in-election-period flag.
- **Misinformation** (7 cols) — flags + severity for documented
  misinformation events in same-district / Punjab-wide / same-community.
- **Responsiveness** (6 cols) — 90-day prior PS-level mean/median
  response time, positive feedback rate, decile rank.
- **`level3_case_nature`** (one-hot) — the granular operational
  category (e.g. "Defiling of Holy Book", "Theft").
- **`is_lahore`** (boolean).
- **`incident_year`, `incident_month`** (numeric).

### Features deliberately excluded as label leakage

- `minority_community` — used to define the target.
- `match_source` — near-deterministic from level2 + community.
- `level2_case_nature` — the target's primary tag.
- `is_minority_targeted` — the target itself.

## Architecture

- `sklearn.linear_model.LogisticRegression`, wrapped in a `Pipeline`
  with `StandardScaler`.
- `class_weight='balanced'` to handle the 1:11 imbalance.
- `solver='lbfgs'`, `max_iter=5000`.
- No hyperparameter tuning (v1 — default).

## Test-set metrics (2026 YTD, n=534)

| Metric | Value |
|---|---|
| ROC AUC | **0.841** |
| PR AUC | 0.224 |
| Precision (@0.5) | 0.104 |
| Recall (@0.5) | 0.931 |
| F1 (@0.5) | 0.187 |
| TP / FP / FN / TN | 27 / 233 / 2 / 272 |
| **Precision@10** | 0.30 |
| **Recall@10** | 0.103 |
| **Precision@20** | 0.20 |
| **Recall@20** | 0.138 |
| **Precision@50** | 0.22 |
| **Recall@50** | 0.379 |

**Success threshold (per methodology doc): ROC AUC ≥ 0.65 — passed.**

The default 0.5-threshold metrics show the model is biased toward
predicting positive (high recall, low precision). Operational deployment
should use a higher threshold (≥ 0.7) or top-N ranking instead of a
binary decision.

## Per-community fairness (test set)

| Community | n | n_pos | ROC AUC | Precision@20 | Recall@20 |
|---|---|---|---|---|---|
| Ahmadi | 10 | 8 | 1.000 | 0.800 | 1.000 |
| Christian | 213 | 19 | 0.999 | 0.900 | 0.947 |
| Hindu | 11 | 2 | 1.000 | 0.182 | 1.000 |
| Multiple | 3 | 0 | n/a | 0.000 | 0.000 |
| Sikh | 5 | 0 | n/a | 0.000 | 0.000 |
| Unspecified | 292 | 0 | n/a | 0.000 | 0.000 |

**Fairness check** (no community has AUC < 0.55 where evaluable): **passes**
for Christian, Ahmadi, Hindu. **Cannot evaluate** Sikh and Multiple in
the 2026 YTD test set because they have zero positives. This is a known
limitation flagged in the final report — re-evaluate when more 2026
data accumulates.

## Top features by |coefficient|

| Feature | Coefficient | Direction |
|---|---|---|
| level3 = Any Other Religious Issue | +1.91 | Strongly positive |
| days_since_last_sikh_event | −0.91 | Strongly negative |
| level3 = Other Disputes & Public Nuisances | −0.84 | Strongly negative |
| prior_30d_district_count | +0.80 | Positive |
| level3 = Other Assault | −0.75 | Negative |
| days_to_next_sikh_event | −0.65 | Negative |
| level3 = Loudspeaker / Loud Music | −0.65 | Negative |
| level3 = Street Fight | −0.64 | Negative |
| level3 = Drunk Behaviour/Fighting | −0.60 | Negative |
| misinfo_event_in_window_same_community | +0.57 | Positive |
| level3 = Attack/Damage of Religious Places | +0.48 | Positive |

The pattern matches expectations: cases tagged in the 6 Religious-Offence
sub-categories of level3 are positive signals; cases tagged as
Public-Disorder / Assault / Theft variants are negative. **Misinformation
proximity (same-community) is one of the top predictors above pure
case-nature signals.**

## Calibration

See `outputs/figures/model/lr_calibration.png`. The decile-binned
predicted-vs-observed plot shows the model is reasonably calibrated in
the mid-range but overestimates probability in the high-score deciles
(common for class-weighted LR). Operational thresholds should be tuned
per use case rather than reading scores as direct probabilities.

## Limitations

1. **Per-case, not place×time.** This model classifies already-reported
   cases. It does not forecast future incidents at PSes without a current
   report. A v2 PS-week forecaster requires generating negative PS-week
   examples and additional feature engineering.

2. **`level3_case_nature` carries most of the predictive signal.** The
   model is largely refining the operational tag with contextual
   information. Useful for triage; not magical.

3. **Test set is small (n=534) with low positive count (n=29).** AUC
   confidence intervals are wide. Re-validate when 2026 has more data.

4. **Sentiment features are placeholders.** When social-media sentiment
   data is connected, model performance may improve materially.

5. **Reporting bias is irreducible.** A model trained on reports
   under-flags communities with low trust in police. See
   [docs/ethics_and_limitations.md](../../docs/ethics_and_limitations.md).

## How to (re)run

```bash
# 1. Make sure features are built
python3 minorities/minorities_project/src/features/build_features.py

# 2. Train
python3 minorities/minorities_project/src/models/train_lr.py

# 3. Score all cases + write to DB
python3 minorities/minorities_project/src/models/predict_batch.py
```

## References

- Methodology: [`docs/04_modeling_methodology.md`](../../docs/04_modeling_methodology.md)
- Data dictionary: [`docs/00_data_dictionary.md`](../../docs/00_data_dictionary.md)
- Ethics: [`docs/ethics_and_limitations.md`](../../docs/ethics_and_limitations.md)
- Source: Mitchell et al., "Model Cards for Model Reporting" (2019)
