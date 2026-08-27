# 08 — Honest Temporal Validation of the PS-week Forecaster

This document reports four robustness upgrades to the PS-week forecaster,
run offline on `data/csv_snapshot/minority_psweek_train.csv` (82,000
PS-weeks, 656 police stations, Jan 2024 – May 2026). The point of the
exercise is to replace best-case headline numbers with numbers you could
honestly promise an operational user.

- Script: [`src/models/psweek_temporal_eval.py`](../src/models/psweek_temporal_eval.py)
- Metrics: [`outputs/reports/psweek_temporal_eval.json`](../outputs/reports/psweek_temporal_eval.json)
- Figures: `outputs/figures/model/psweek_rolling_origin.png`,
  `outputs/figures/model/psweek_calibration.png`

Target throughout: `target_30d` (a strict-labelled minority incident at
this PS within the 30 days *after* the week starts). Overall positive
rate is **1.35%** — a rare event — and it is **non-stationary**: it peaks
at 2.8% in 2025Q1 and falls to 0.69% by 2025Q4.

---

## TL;DR — what changed

| Claim (before) | Honest finding (after) |
|---|---|
| "LR AUC 0.72" (single 2026 cutoff) | **0.70 averaged over 6 rolling folds**, range 0.62–0.75. The 0.72 was representative but on the optimistic side. |
| "Precision@20 ≈ 0.20–0.35" | **Mean Precision@20 = 0.092**, and it is **0.0 in two of six folds**. The 0.20–0.35 figures are best-case quarters, not typical. |
| "18.5× lift" | **Mean lift@20 = 8.1×** (lift@10 = 10.6×). Still well above random, but less than half the headline. |
| Risk scores read as probabilities (threshold slider) | **Raw scores are badly miscalibrated** — mean predicted prob 0.58 vs true rate 0.0075. Useful for *ranking only* until calibrated. |
| Calendar interaction features would help | **They did not** improve out-of-time accuracy. Honest negative result. |

---

## 1. Rolling-origin validation with a 30-day embargo

**Why.** The original code uses one split (train < 2026-01-01, test
2026+). A single cutoff lands in one regime (2026 is a low-rate period)
and rests on just 99 test positives — too few to trust. Also, because
`target_30d` looks 30 days forward, the label window of the last training
weeks overlaps the first test weeks, leaking the future into the past.

**What I did.** Expanding-window walk-forward across six quarterly test
folds (2025Q1 → 2026Q2). Each fold trains on everything up to
`(test_start − 30 days)`; the 30-day **embargo** removes the label
overlap. Train medians are used to impute the test set (no test-set
leakage in imputation either).

**Result (LR, the chosen forecaster):**

| Fold | Test pos | Base rate | ROC AUC | Precision@20 | Lift@20 |
|---|---|---|---|---|---|
| 2025Q1 | 240 | 2.81% | 0.617 | 0.20 | 7.1× |
| 2025Q2 | 213 | 2.50% | 0.679 | 0.05 | 2.0× |
| 2025Q3 | 93 | 1.09% | 0.745 | 0.00 | 0.0× |
| 2025Q4 | 59 | 0.69% | 0.731 | 0.00 | 0.0× |
| 2026Q1 | 63 | 0.74% | 0.736 | 0.15 | 20.3× |
| 2026Q2 | 36 | 0.78% | 0.664 | 0.15 | 19.1× |
| **Mean** | — | — | **0.695** | **0.092** | **8.1×** |

**Reading it honestly.** The ranking ability (AUC ~0.70) is real and
reasonably stable. The *operational* metric — did the top-20 flagged
stations actually have incidents — is **volatile and often weak**: two
quarters caught nothing in the top 20. Lift looks huge in low-rate
quarters (20× in 2026Q1) precisely *because* the base rate is tiny;
that is why every lift figure in this project should be quoted next to
its absolute precision.

---

## 2. Precision@K and lift, stated honestly

Lift@K = precision@K ÷ test base rate. It is a ratio, so it inflates when
incidents are rare. Mean over folds (LR):

| K | Precision@K | Recall@K | Lift@K |
|---|---|---|---|
| 10 | 0.117 | — | 10.6× |
| 20 | 0.092 | — | 8.1× |
| 50 | 0.077 | — | 6.8× |

**Takeaway for the brief:** "On average the model's top-10 stations are
~10× more likely than a random station to see an incident in the next 30
days" is defensible. "18.5× lift / 89.5% precision" is not — that was a
favorable slice and/or whole-dataset numbers.

---

## 3. Calibration — the most important finding

**Why.** The dashboard exposes a risk-score threshold slider, which only
makes sense if a "0.8" really means ~80% likelihood. It does not.

**What I found (2026 out-of-time fold).** The deployed-style LR uses
`class_weight='balanced'`, which pushes scores up to separate the rare
positive class. The consequence:

| | Raw LR | After isotonic |
|---|---|---|
| Mean predicted probability | **0.577** | 0.026 |
| (True base rate) | 0.0075 | 0.0075 |
| Brier score (lower better) | 0.357 | **0.0079** |
| ECE (lower better) | 0.569 | **0.018** |

The raw model predicts a **0.58 average probability for events that occur
0.75% of the time** — a ~77× over-statement. On the reliability diagram
the raw curve is flat along the bottom: scores from 0.2 to 0.95 all map to
observed rates near zero. See `psweek_calibration.png`.

**Fix.** An isotonic re-fit (base model fit on the earliest 80% of train,
calibrator fit on the latest 20%, evaluated on 2026) cuts Brier ~45× and
ECE ~30×. After calibration the scores mean roughly what they say.

**Practical implication.** Until scores are calibrated, the model should
be used for **ranking** (Precision@K), and the dashboard's numeric
threshold should be read as a rank cutoff, not a probability. If we want
the slider to be honest, ship the isotonic calibrator with the model.

---

## 4. Calendar interaction features — a negative result

**Hypothesis (from the Research Design report).** Risk rises when multiple
communities' festivals overlap and when a religious date coincides with a
political event. I engineered six features from the existing
`days_to_next_*` columns: imminence of a major religious event (≤7, ≤14
days), a multi-community **overlap count** (how many communities have an
event within 14 days), an overlap≥2 flag, a religious×political
coincidence flag, and a post-event aftermath flag.

**Result (mean over the same six folds, LR):**

| Metric | Base features | + Interactions |
|---|---|---|
| ROC AUC | 0.695 | 0.688 |
| PR AUC | 0.045 | 0.044 |
| Precision@20 | 0.092 | 0.083 |
| Lift@20 | 8.1× | 8.6× |

**Reading it honestly.** The interactions did **not** help out-of-time —
AUC and Precision@20 are flat-to-slightly-worse. They helped in one fold
(2026Q1: Precision@20 0.15 → 0.20) and hurt in another (2025Q1: 0.20 →
0.10). The festival-overlap / coincidence hypothesis is **not supported**
by this validation. That is a legitimate finding, not a failure: it says
the prior-incident-density features already carry most of the signal, and
hand-built calendar interactions add noise more than signal at this data
volume.

---

## What this means for the project's claims

1. **Quote the rolling-origin numbers**, not the single-cutoff ones:
   AUC ≈ 0.70 (range 0.62–0.75), mean Precision@20 ≈ 0.09, lift@10 ≈ 10×.
2. **Drop "18.5× lift / 89.5% precision"** from the brief, or footnote
   them explicitly as best-case / whole-dataset.
3. **State the calibration caveat**: raw scores rank well but are not
   probabilities; ship a calibrator if the threshold slider is to be
   trusted.
4. **Report the calendar negative result** — it strengthens credibility
   and matches the project's honest-about-limits posture.

For the *AI-and-minorities* framing, this rigor is also part of the safety
case: an over-confident risk model pointed at a vulnerable community does
real harm. Calibrated, honestly-validated scores are an ethical
requirement, not just good ML hygiene. This sits alongside the existing
reporting-bias caveat (the model predicts *reports*, not incidents) in
[`docs/ethics_and_limitations.md`](ethics_and_limitations.md).

---

*Reproduce:* `python src/models/psweek_temporal_eval.py` (needs only
pandas, numpy, scikit-learn, matplotlib; reads the CSV snapshot, no DB).
