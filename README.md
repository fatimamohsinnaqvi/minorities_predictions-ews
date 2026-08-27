# Minorities Early-Warning System — Code & Analysis

Predictive early-warning system for minority-targeted crime in Punjab
(focused on Lahore), built on PSCA Emergency-15 case data. This repository
contains the **code, trained models, aggregated data, figures, and full
methodology** — enough to review the work, reproduce the headline analysis,
and run the dashboard locally.

> **Private repository.** Share only with collaborators. See the privacy
> note below before redistributing anything.

---

## Quick start

### A) Run the dashboard locally (no data files needed)

The dashboard is self-contained — the map, forecasts, and all data are
baked into `dashboard/dashboard.html` (with caller details redacted).

```bash
cd dashboard
python3 -m venv venv
source venv/bin/activate            # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt     # just streamlit

# set a login password
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml → username = "admin", password = "..."

streamlit run app.py                # opens http://localhost:8501
```

(The same dashboard is also deployed live — ask the maintainer for the URL.)

### B) Reproduce the headline analysis

```bash
bash run.sh
```

This creates a virtual environment, installs the analysis dependencies,
and runs the honest temporal validation
([`src/models/psweek_temporal_eval.py`](src/models/psweek_temporal_eval.py)),
regenerating `outputs/reports/psweek_temporal_eval.json` and the
`psweek_rolling_origin.png` / `psweek_calibration.png` figures.

---

## What's in here

```
minorities_code/
├── src/                 # all pipeline + feature + model code
├── dashboard/           # runnable, self-contained Streamlit dashboard (sanitised)
├── data/
│   ├── csv_snapshot/    # aggregated PS-week tables (no per-case, no PII)
│   ├── processed/       # district severity, Prophet forecasts, EDA summary
│   └── external/        # public event calendars (religious/political/misinfo)
├── outputs/
│   ├── models/          # trained .pkl models
│   ├── reports/         # metrics JSON + model cards
│   └── figures/         # EDA (7) + model (15) figures — paper-ready PNGs
├── docs/                # full methodology (00–08 + ethics, audit)
├── PAPER_GUIDE.md       # map of paper sections → evidence/figures/numbers
├── run.sh               # one-command reproduce
└── requirements.txt
```

## Data & privacy — read before redistributing

This project handles reports about religious minorities, so raw data is
**deliberately excluded**:

- **Not included:** per-case incident records, caller descriptions, phone
  numbers, and the unredacted map exports. These contain personal data.
- **Included:** only aggregated tables (police-station × week counts,
  district severity, monthly forecasts) and public event calendars — none
  of which contain per-person or contact information.

The scripts under `src/` that read the raw operational database
(`db_config`, not included) will not run offline; the aggregated tables
provided are enough to reproduce the forecasting analysis in `run.sh`.

For the honest, validated performance numbers (rolling-origin, calibration),
see [`docs/08_temporal_validation.md`](docs/08_temporal_validation.md) —
cite those, not the single-cutoff headline figures.

## Where to start reading

1. [`PAPER_GUIDE.md`](PAPER_GUIDE.md) — if you're writing the paper.
2. [`docs/04_modeling_methodology.md`](docs/04_modeling_methodology.md) — how the models work.
3. [`docs/08_temporal_validation.md`](docs/08_temporal_validation.md) — the rigorous validation.
4. [`docs/ethics_and_limitations.md`](docs/ethics_and_limitations.md) — the ethical framing.

---

*Note: the large Random Forest `.pkl` files are omitted to keep the repo
lean (RF is not the deployed forecaster — LR is). Regenerate them with
`python src/models/train_rf.py` and `python src/models/train_psweek.py`
if needed (requires the operational database).*
