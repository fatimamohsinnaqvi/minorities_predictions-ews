`Minority Early Warning System: Code and Analysis`
A predictive early warning system for minority targeted crime in Punjab, Pakistan, with a focus on Lahore. Built using PSCA Emergency 15 case data, this project combines data processing, spatiotemporal analysis, predictive modelling, and interactive visualisation to investigate patterns in reported incidents and assess their potential use in early warning analysis.

This repository contains the analysis pipeline, trained model artefacts where available, aggregated datasets, evaluation results, figures, and methodological documentation. It is designed to support independent review, reproduction of the documented analyses, and local execution of the dashboard.

## Quick Start

### A. Run the Dashboard Locally

The dashboard is designed to run locally using the included sanitised application and its bundled visualisation data.

```bash
cd dashboard
python3 -m venv venv

# macOS/Linux
source venv/bin/activate

# Windows PowerShell
# .\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Configure authentication using the example secrets file:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` to configure the username and password, then launch the application:

```bash
streamlit run app.py
```

The dashboard will be available locally at `http://localhost:8501`.

Keep your actual secrets file private and never commit credentials to GitHub.

A live deployment may also be available from the project maintainer.

### B. Reproduce the Temporal Validation Analysis

Run the analysis pipeline:

```bash
bash run.sh
```

The script creates a virtual environment, installs the required analysis dependencies, and executes the temporal validation pipeline in `src/models/psweek_temporal_eval.py`.

The analysis regenerates the temporal evaluation report at `outputs/reports/psweek_temporal_eval.json`, together with the rolling origin evaluation and calibration figures.

See `docs/08_temporal_validation.md` for the evaluation methodology, results, and interpretation.

Reproduction depends on the availability of the required aggregated data and software dependencies.

## Repository Structure

```text
minorities_code/
├── src/                 # Data processing, features, and models
├── dashboard/           # Local Streamlit dashboard
├── data/
│   ├── csv_snapshot/    # Aggregated police station by week tables
│   ├── processed/       # District severity, forecasts, and EDA summaries
│   └── external/        # Public event calendars
├── outputs/
│   ├── models/          # Available trained model artefacts
│   ├── reports/         # Evaluation metrics and model cards
│   └── figures/         # Exploratory analysis and model evaluation figures
├── docs/                # Methodology, validation, ethics, and audit documentation
├── PAPER_GUIDE.md       # Research sections, evidence, and figures
├── run.sh               # Analysis reproduction script
└── requirements.txt     # Analysis dependencies
```

## Data and Privacy

This project concerns reported incidents involving religious minorities and therefore requires careful handling of sensitive operational data.

Raw case level records are intentionally excluded from this repository.

The repository does not include individual incident records, caller descriptions, telephone numbers, or unredacted map exports containing potentially identifying information. It includes aggregated police station by week tables, district level severity summaries, monthly forecasts, and public event calendar data.

The operational database configuration, `db_config`, is not included. Scripts that depend on direct access to the raw operational database therefore require separately authorised access to that source. The included aggregated datasets support the documented forecasting analysis where the required inputs are available.

Aggregated data and derived outputs can still carry privacy risks, particularly when geographic or temporal categories are narrow. Their suitability for public release should be assessed before redistribution.

## Model Evaluation and Limitations

Model performance should be assessed using temporal validation results rather than relying solely on a single train test split or cutoff.

The rolling origin evaluation and calibration analysis are documented in `docs/08_temporal_validation.md`. These results should be used when describing model performance, alongside appropriate baseline comparisons, uncertainty, and limitations in the available data.

Predictions based on reported incident data should not be interpreted as definitive measures of the underlying prevalence of crime. Reporting patterns, data coverage, and other sources of bias may affect the results. The system is intended to support further analysis and inform the allocation of protective resources, not to establish individual culpability or justify discriminatory treatment of communities.

## Where to Start

1. `PAPER_GUIDE.md` provides an overview of the research, figures, and supporting evidence.
2. `docs/04_modeling_methodology.md` explains the model design and methodology.
3. `docs/08_temporal_validation.md` documents temporal evaluation, calibration, and performance assessment.
4. `docs/ethics_and_limitations.md` discusses ethical considerations, limitations, and responsible interpretation.

## Model Artefacts

Large Random Forest (`.pkl`) model files are omitted to keep the repository lightweight. Random Forest is not the deployed forecasting model; the current implementation uses Logistic Regression for forecasting.

The Random Forest and PS week models can be retrained using the following scripts:

```bash
python src/models/train_rf.py
python src/models/train_psweek.py
```

These scripts require access to the operational database and may not run in an offline environment.

This repository documents a data driven research project. Its findings and predictive outputs should be interpreted in light of the validation results, data limitations, and ethical considerations described in the accompanying documentation.
