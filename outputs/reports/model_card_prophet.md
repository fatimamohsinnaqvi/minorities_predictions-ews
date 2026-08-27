# Model Card — Prophet Time-Series Forecaster

**Project:** Minorities Early-Warning System — Lahore
**Model:** Facebook Prophet — flat growth (no trend extrapolation),
no yearly seasonality, holiday regressors (±3 day windows), additive
mode
**Trained on:** post-shift window only (2025-10-01 onwards)
**Created:** 2026-06-25

---

## What this model does

Predicts the **total monthly volume** of minority-related Emergency-15
cases for the next 3 months. Two
series are forecast independently:

1. **Punjab-wide** — sum across all districts
2. **Lahore-only** — the focal city

Major religious events (Christmas, Eid-ul-Fitr, Eid-ul-Adha, Muharram,
Ashura, Holi, Diwali, Easter, Eid-e-Milad-un-Nabi, Vaisakhi, Guru
Nanak Jayanti) are used as **holiday regressors with a ±3-day window**.
This lets the model explicitly learn the lift those events produce on
minority-related case counts.

## Important modeling decision — regime-shift handling

The full series shows a clear **regime shift around October 2025**:
case volume dropped from ~200/month to ~90/month and has stayed flat
since. On a 25-month series with a mid-series step, neither yearly
seasonality nor a linear trend can be estimated reliably (we have ~2
yearly cycles, and the step contaminates the average).

The honest choice: **train on the post-shift window only**, use **flat
growth** (no trend extrapolation), and turn off yearly seasonality
(can't be learned from 8 months of post-shift data). The model
effectively says *"future monthly volume = current level + holiday
effects."* That's a much more useful baseline than over-extrapolating
the early-2024 levels.

## Why this is complementary to the other models

The classifiers in this project answer questions like:
- *Per-case classifier:* "Given a case is reported, is it minority-targeted?"
- *PS-week forecaster:* "For each PS, will an incident occur in the next 30d?"

Prophet adds a third question:
- *Volume forecaster:* "How many total minority-related cases next month?"

That number drives **resource planning** at the provincial level — how
much call-center capacity, how many extra patrols to budget for, etc.

## Validation

The model is fit on the post-shift window minus the last 2 months,
then evaluated on those held-out months:

| Series | Full obs | Post-shift obs | Validation MAPE | RMSE | MAE | Last observed |
|---|---|---|---|---|---|---|
| Punjab-wide | 25 | 9 | **9.54%** | 9.61 | 8.49 | 2026-06-01 |
| Lahore-only | 25 | 9 | **26.31%** | 5.35 | 4.5 | 2026-06-01 |

MAPE = mean absolute percentage error. **<20% is good for sparse,
calendar-driven series; <30% acceptable for low-count series like
Lahore-only.**

## Forecast horizon

3 months past the most recent observation. Confidence intervals (80%)
are reported in the forecast CSV.

## Outputs

- `data/processed/prophet_forecast_punjab.csv` — `ds`, `yhat`, `yhat_lower`,
  `yhat_upper` for the full series + forecast horizon
- `data/processed/prophet_forecast_lahore.csv` — same for Lahore-only
- `outputs/figures/model/prophet_punjab.png` — fan-chart of actuals +
  forecast + 80% interval
- `outputs/figures/model/prophet_lahore.png` — same for Lahore
- `outputs/figures/model/prophet_components_punjab.png` — decomposition
  into trend + yearly seasonality + holidays (the *why* of the forecast)
- `outputs/figures/model/prophet_components_lahore.png` — same for Lahore
- `outputs/reports/prophet_metrics.json` — machine-readable metrics

## Limitations

1. **Short post-shift series.** Only 8-9 months of data after the
   October 2025 regime shift. We can estimate the mean level + holiday
   effects but not yearly seasonality (would need at least 2 full
   cycles).

2. **Regime shift cause is unknown.** Our forecast assumes the
   post-October-2025 level is the new steady state. If the cause was
   transient (e.g., a one-off reporting-system change), volumes could
   revert upward and our forecast will under-predict. If structural,
   our forecast is correct. **Action item for next iteration:**
   investigate what changed in October 2025.

3. **Sparse events for sub-series.** Lahore-only has 13-26 cases per
   month — low absolute count means MAPE is noisy. Per-district
   forecasts would be sparser still and weren't attempted. For
   per-district / per-PS predictions, use the classification model in
   `minority_psweek_forward`.

4. **Religious-holiday window is fixed at ±3 days.** Some events have
   longer effective windows (Muharram is 10 days). A future iteration
   could fit per-event windows.

5. **Reporting bias is irreducible.** Volume forecasts predict
   *reports*, not incidents. See `docs/ethics_and_limitations.md`.

## How to re-run

```bash
python3 src/models/timeseries_prophet.py
```

Reads from `data/csv_snapshot/minority_incidents.csv` if present, else
falls back to the live DB. Output paths are documented above.

## References

- Methodology doc: [`docs/04_modeling_methodology.md`](../../docs/04_modeling_methodology.md)
- Sister model cards: [`model_card_lr.md`](model_card_lr.md),
  [`model_card_rf.md`](model_card_rf.md)
- Prophet: Taylor & Letham (2018) — "Forecasting at scale"
