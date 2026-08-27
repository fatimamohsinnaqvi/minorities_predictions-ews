#!/usr/bin/env python3
"""
Time-series forecasting (Prophet) — companion to the classification models.

Predicts monthly minority-incident *volume* (count) for the next 3 months,
both for Punjab as a whole and for Lahore specifically. Uses major
religious events as holiday regressors so Prophet can learn — and the
final report can quote — the explicit lift from Christmas / Eid /
Muharram windows.

This complements (does NOT replace) the per-case and PS-week classifiers
documented elsewhere. Where those answer "is this likely minority-
targeted?" or "which PS for next 30 days?", Prophet answers "how many
total minority-related cases will there be?"

Reads (in order of preference):
  data/csv_snapshot/minority_incidents.csv      ← offline mode (default)
  db_predictive_policing.minority_incidents     ← when DB is reachable

Writes:
  data/processed/prophet_forecast_{punjab,lahore}.csv
  outputs/figures/model/prophet_{punjab,lahore}.png
  outputs/figures/model/prophet_components_{punjab,lahore}.png
  outputs/reports/prophet_metrics.json
  outputs/reports/model_card_prophet.md
"""
import json
import os
import re
import sys
import warnings
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, "..", ".."))
CSV_INC = os.path.join(PROJECT, "data", "csv_snapshot", "minority_incidents.csv")
CSV_REL = os.path.join(PROJECT, "data", "external", "religious_calendar.csv")
OUT_DATA = os.path.join(PROJECT, "data", "processed")
OUT_FIG  = os.path.join(PROJECT, "outputs", "figures", "model")
OUT_REP  = os.path.join(PROJECT, "outputs", "reports")
for d in (OUT_DATA, OUT_FIG, OUT_REP):
    os.makedirs(d, exist_ok=True)


def _import_prophet():
    """Import Prophet with a clear, actionable error if it's missing."""
    try:
        from prophet import Prophet  # noqa: F401
        return True
    except ImportError:
        print("[ERR] Prophet is not installed.")
        print("       Install with:  pip install prophet")
        print("       (Prophet has heavy deps — cmdstanpy compiles on first use.")
        print("        Allow ~5 minutes for the first install.)")
        return False


def load_incidents():
    """Try CSV snapshot first (works on the user's personal laptop),
    fall back to DB on the source machine."""
    if os.path.exists(CSV_INC):
        df = pd.read_csv(CSV_INC, parse_dates=["incident_date"])
        print(f"[load] {CSV_INC}  ({len(df):,} rows)")
        return df
    # Fallback: live DB
    sys.path.append(os.path.join("/home/rizwan.tahir/cpis-backend", "utilties"))
    from db_config import get_db_postgres_predictive  # noqa
    conn = get_db_postgres_predictive()
    df = pd.read_sql("SELECT * FROM minority_incidents", conn)
    conn.close()
    df["incident_date"] = pd.to_datetime(df["incident_date"], errors="coerce")
    print(f"[load] from DB ({len(df):,} rows)")
    return df


def normalize_event_name(name):
    """Collapse year suffixes so the same recurring event maps to a
    single Prophet 'holiday' name across years.
    'Eid-ul-Fitr (approx)' → 'Eid-ul-Fitr'
    '1 Muharram 1447' → '1 Muharram'
    'Ashura (10 Muharram) 1447' → 'Ashura (10 Muharram)'
    """
    s = str(name).strip()
    s = re.sub(r"\s*\(approx\)\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+\d{4}\b\s*$", "", s)             # trailing 4-digit year
    s = re.sub(r"\s+1\d{3}\b\s*$", "", s)             # trailing AH-year
    return s.strip()


def load_holidays():
    """Build a Prophet-compatible holidays DataFrame from
    religious_calendar.csv. We keep MAJOR events only (annual repeats)
    and group by normalized name so each event gets one coefficient
    across all years."""
    cal = pd.read_csv(CSV_REL, parse_dates=["date"])
    cal["significance"] = cal["significance"].astype(str).str.lower().str.strip()
    major = cal[cal["significance"] == "major"].copy()
    major["holiday"] = major["event_name"].apply(normalize_event_name)
    major = major.rename(columns={"date": "ds"})[["holiday", "ds"]]
    # Window: incidents may cluster ±3 days around the event
    major["lower_window"] = -3
    major["upper_window"] = 3
    return major


def aggregate_monthly(df, lahore_only=False):
    if lahore_only:
        df = df[df["is_lahore"] == True].copy()  # noqa: E712
    df = df.dropna(subset=["incident_date"]).copy()
    df["month_start"] = df["incident_date"].dt.to_period("M").dt.to_timestamp()
    monthly = df.groupby("month_start").size().reset_index(name="y")
    monthly = monthly.rename(columns={"month_start": "ds"})
    return monthly.sort_values("ds").reset_index(drop=True)


def fit_and_forecast(monthly, holidays, label, periods_ahead=3,
                      holdout_months=2):
    """Train Prophet, validate on a holdout, then forecast `periods_ahead`
    months past the latest observation.  Returns (forecast_df, metrics)."""
    from prophet import Prophet

    if len(monthly) <= holdout_months + 6:
        print(f"  [warn] short series ({len(monthly)} months). "
              f"Holdout reduced to 1 month.")
        holdout_months = 1
    train = monthly.iloc[:-holdout_months].copy()
    test  = monthly.iloc[-holdout_months:].copy()

    # 25 months with a regime shift around Oct 2025 (case volume
    # dropped from ~200/mo to ~90/mo). On a series this short with a
    # mid-series step, neither yearly seasonality nor a linear trend
    # can be estimated reliably. We:
    #   - Train on the POST-shift window only (2025-10 onwards)
    #   - Use flat growth (no trend extrapolation)
    #   - Keep holiday regressors (those repeat annually so still useful)
    # The pre-shift data is shown on the plot for context but not used
    # for forecasting. This is the honest choice and is documented in
    # the model card.
    POST_SHIFT_START = pd.Timestamp("2025-10-01")
    train_post = train[train["ds"] >= POST_SHIFT_START].copy()
    if len(train_post) >= 5:
        train_for_fit = train_post
        regime_used = "post-shift (2025-10 onwards)"
    else:
        # Not enough post-shift data — fall back to full series
        train_for_fit = train
        regime_used = "full series (post-shift too short)"
    m = Prophet(
        holidays=holidays,
        yearly_seasonality=False,           # short series, regime shift — yearly not learnable
        weekly_seasonality=False,
        daily_seasonality=False,
        interval_width=0.80,
        seasonality_mode="additive",
        holidays_prior_scale=3.0,
        growth="flat",                      # no trend extrapolation
    )
    m.fit(train_for_fit)

    # Validate on holdout
    test_forecast = m.predict(test[["ds"]])
    yhat_test = test_forecast["yhat"].values
    y_test    = test["y"].values
    mape  = float(np.mean(np.abs((y_test - yhat_test) / np.maximum(1, y_test))) * 100)
    rmse  = float(np.sqrt(np.mean((y_test - yhat_test) ** 2)))
    mae   = float(np.mean(np.abs(y_test - yhat_test)))

    # Refit on the FULL post-shift window (train + holdout) + extend forecast
    monthly_post = monthly[monthly["ds"] >= POST_SHIFT_START].copy()
    m_full = Prophet(
        holidays=holidays,
        yearly_seasonality=False,
        weekly_seasonality=False,
        daily_seasonality=False,
        interval_width=0.80,
        seasonality_mode="additive",
        holidays_prior_scale=3.0,
        growth="flat",
    )
    m_full.fit(monthly_post)
    future = m_full.make_future_dataframe(periods=periods_ahead, freq="MS")
    full_forecast = m_full.predict(future)
    # Clip negatives — case counts can't go below 0
    for c in ("yhat", "yhat_lower", "yhat_upper"):
        full_forecast[c] = full_forecast[c].clip(lower=0)

    return m_full, full_forecast, {
        "label": label,
        "n_observations": int(len(monthly)),
        "n_post_shift_observations": int(len(monthly_post)),
        "regime_used": regime_used,
        "train_months": int(len(train_for_fit)),
        "holdout_months": int(holdout_months),
        "validation_MAPE_pct": round(mape, 2),
        "validation_RMSE":     round(rmse, 2),
        "validation_MAE":      round(mae, 2),
        "forecast_horizon_months": periods_ahead,
        "last_observed_month":  str(monthly["ds"].iloc[-1].date()),
        "regime_shift_date_assumed": str(POST_SHIFT_START.date()),
    }


def plot_forecast(m, forecast, monthly, label, out_path):
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(monthly["ds"], monthly["y"], "o-", color="#2c3e50", label="actual",
            markersize=5, linewidth=1.4)
    ax.plot(forecast["ds"], forecast["yhat"], color="#c0392b",
            label="prophet forecast", linewidth=1.6)
    ax.fill_between(forecast["ds"], forecast["yhat_lower"], forecast["yhat_upper"],
                     color="#c0392b", alpha=0.18, label="80% CI")
    # Mark the boundary where actuals stop
    last_actual = monthly["ds"].iloc[-1]
    ax.axvline(last_actual, color="#7f8c8d", linestyle="--", alpha=0.6,
                label="forecast horizon →")
    ax.set_title(f"Monthly minority-incident volume — {label}",
                 fontweight="bold")
    ax.set_xlabel("Month"); ax.set_ylabel("Cases")
    ax.legend(loc="upper left", frameon=False)
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {out_path}")


def plot_components(m, forecast, label, out_path):
    fig = m.plot_components(forecast, figsize=(11, 8))
    fig.suptitle(f"Decomposition — {label}", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {out_path}")


def write_model_card(metrics_pj, metrics_lah):
    card = f"""# Model Card — Prophet Time-Series Forecaster

**Project:** Minorities Early-Warning System — Lahore
**Model:** Facebook Prophet — flat growth (no trend extrapolation),
no yearly seasonality, holiday regressors (±3 day windows), additive
mode
**Trained on:** post-shift window only ({metrics_pj['regime_shift_date_assumed']} onwards)
**Created:** {datetime.utcnow().strftime('%Y-%m-%d')}

---

## What this model does

Predicts the **total monthly volume** of minority-related Emergency-15
cases for the next {metrics_pj['forecast_horizon_months']} months. Two
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
| Punjab-wide | {metrics_pj['n_observations']} | {metrics_pj['n_post_shift_observations']} | **{metrics_pj['validation_MAPE_pct']}%** | {metrics_pj['validation_RMSE']} | {metrics_pj['validation_MAE']} | {metrics_pj['last_observed_month']} |
| Lahore-only | {metrics_lah['n_observations']} | {metrics_lah['n_post_shift_observations']} | **{metrics_lah['validation_MAPE_pct']}%** | {metrics_lah['validation_RMSE']} | {metrics_lah['validation_MAE']} | {metrics_lah['last_observed_month']} |

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
"""
    path = os.path.join(OUT_REP, "model_card_prophet.md")
    with open(path, "w") as f:
        f.write(card)
    print(f"  → {path}")


def main():
    if not _import_prophet():
        sys.exit(1)

    df = load_incidents()
    holidays = load_holidays()
    print(f"[load] holidays (normalized, MAJOR only): "
          f"{holidays['holiday'].nunique()} distinct events, "
          f"{len(holidays)} occurrences across years")

    pj  = aggregate_monthly(df, lahore_only=False)
    lah = aggregate_monthly(df, lahore_only=True)
    print(f"[agg]  Punjab months: {len(pj)}, "
          f"Lahore months: {len(lah)}")

    print("\n[fit] Punjab-wide ...")
    m_pj, fc_pj, met_pj = fit_and_forecast(pj, holidays, "Punjab")
    print(f"  Validation MAPE = {met_pj['validation_MAPE_pct']}%  "
          f"RMSE = {met_pj['validation_RMSE']}")

    print("[fit] Lahore-only ...")
    m_lah, fc_lah, met_lah = fit_and_forecast(lah, holidays, "Lahore")
    print(f"  Validation MAPE = {met_lah['validation_MAPE_pct']}%  "
          f"RMSE = {met_lah['validation_RMSE']}")

    # Save forecast CSVs
    fc_pj[["ds", "yhat", "yhat_lower", "yhat_upper"]].to_csv(
        os.path.join(OUT_DATA, "prophet_forecast_punjab.csv"), index=False)
    fc_lah[["ds", "yhat", "yhat_lower", "yhat_upper"]].to_csv(
        os.path.join(OUT_DATA, "prophet_forecast_lahore.csv"), index=False)

    # Plots
    print("\n[plot] ...")
    plot_forecast(m_pj,  fc_pj,  pj,  "Punjab-wide",
                  os.path.join(OUT_FIG, "prophet_punjab.png"))
    plot_forecast(m_lah, fc_lah, lah, "Lahore-only",
                  os.path.join(OUT_FIG, "prophet_lahore.png"))
    plot_components(m_pj,  fc_pj,  "Punjab-wide",
                     os.path.join(OUT_FIG, "prophet_components_punjab.png"))
    plot_components(m_lah, fc_lah, "Lahore-only",
                     os.path.join(OUT_FIG, "prophet_components_lahore.png"))

    # Metrics + model card
    metrics = {
        "generated_at": datetime.utcnow().isoformat(),
        "punjab": met_pj,
        "lahore": met_lah,
    }
    with open(os.path.join(OUT_REP, "prophet_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"  → {os.path.join(OUT_REP, 'prophet_metrics.json')}")

    write_model_card(met_pj, met_lah)

    # Print summary
    print("\n=== FORECAST SUMMARY ===")
    for label, fc, met in [("Punjab", fc_pj, met_pj), ("Lahore", fc_lah, met_lah)]:
        last_actual = met["last_observed_month"]
        print(f"\n  {label}  (data up to {last_actual},  validation MAPE = "
              f"{met['validation_MAPE_pct']}%)")
        upcoming = fc.iloc[-3:][["ds", "yhat", "yhat_lower", "yhat_upper"]]
        for _, r in upcoming.iterrows():
            month = pd.to_datetime(r["ds"]).strftime("%Y-%m")
            print(f"    {month}:  forecast={r['yhat']:.0f}   "
                  f"(80% CI: {r['yhat_lower']:.0f}–{r['yhat_upper']:.0f})")

    print("\n[done]")


if __name__ == "__main__":
    main()
