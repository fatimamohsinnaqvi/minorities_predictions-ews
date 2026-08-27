"""
Dataset preparation for the modeling phase.

Loads `minority_features_merged`, applies a strict temporal train/test
split, and produces X/y arrays + a `meta` DataFrame for per-group
evaluation.

CRITICAL — features that would leak the label are excluded:
  - minority_community  (the target is partly defined from this)
  - match_source        (essentially correlated with the target)
  - level2_case_nature  (the target is partly defined from this; not in
                         merged but documented for completeness)
  - is_minority_targeted itself (this IS the target)

What we keep:
  - All numeric features from the 5 active feature families
    (prior_density, religious_calendar, political_calendar, misinformation,
    responsiveness). Sentiment features are present but all NULL.
  - is_lahore (boolean)
  - incident_month, incident_year (numeric, captures temporal effects)
  - level3_case_nature (one-hot encoded; not a direct derivation of target)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

# Columns we never use as model input
LEAKAGE_COLS = {
    'is_minority_targeted',          # the target
    'minority_community',            # used to define the target
    'match_source',                  # near-perfect with target
}

# Columns that are identifiers / not features
IDENTITY_COLS = {
    'case_id', 'incident_date',
    'district_name', 'police_station', 'police_station_id', 'district_id',
}

# Categoricals we will one-hot encode
CATEGORICAL_COLS = {'level3_case_nature'}

# Sentiment columns are all NULL in v1 — drop them entirely (otherwise
# the imputer median is undefined and the column adds noise)
SENTIMENT_COLS = {
    'sm_post_count_7d', 'sm_negative_share_7d',
    'sm_post_count_30d', 'sm_negative_share_30d',
    'sm_velocity', 'has_sentiment_data',
}


def load_merged():
    """Return the merged feature DataFrame from the DB."""
    conn = get_db_postgres_predictive()
    df = pd.read_sql("SELECT * FROM minority_features_merged", conn)
    conn.close()
    return df


def temporal_split(df, train_years=(2024, 2025), test_years=(2026,)):
    """Strict temporal split on incident_year."""
    train_df = df[df['incident_year'].isin(train_years)].copy()
    test_df = df[df['incident_year'].isin(test_years)].copy()
    return train_df, test_df


def prepare(df, fitted_cats=None):
    """Convert df to (X, y, feature_names, meta).

    fitted_cats : dict[col] -> list of categorical values to use as columns.
        Pass None for the train set (categories are learned). Pass the
        learned dict for the test set so columns line up.

    Returns:
        X (np.array float64), y (np.array int8), feature_names (list[str]),
        meta (pd.DataFrame with case_id, minority_community, district_name,
              police_station, is_lahore, incident_date)
    """
    # Meta (kept for per-group eval, never fed to model)
    meta = df[['case_id', 'minority_community', 'district_name',
                'police_station', 'is_lahore', 'incident_date',
                'incident_year', 'incident_month']].copy()

    # Drop identity, leakage, sentiment columns
    drop_cols = (IDENTITY_COLS | LEAKAGE_COLS | SENTIMENT_COLS)
    use = df.drop(columns=[c for c in drop_cols if c in df.columns])

    # Separate target
    y = df['is_minority_targeted'].fillna(False).astype(int).values

    # One-hot encode categoricals; remember the categories from train
    new_cats = {}
    for c in CATEGORICAL_COLS:
        if c not in use.columns:
            continue
        # Lowercase + null-safe
        s = use[c].astype(str).fillna('NA').str.strip()
        if fitted_cats is not None and c in fitted_cats:
            cats = fitted_cats[c]
        else:
            cats = sorted(s.unique().tolist())
            new_cats[c] = cats
        for v in cats:
            colname = f'{c}={v}'
            use[colname] = (s == v).astype(int)
        use.drop(columns=[c], inplace=True)

    # Booleans → int
    for c in use.columns:
        if use[c].dtype == bool:
            use[c] = use[c].astype('Int8')

    # Drop any remaining non-numeric column we couldn't handle.
    # Use pd.api.types.is_numeric_dtype to handle Int8/Int64 nullable too.
    non_numeric = [c for c in use.columns if not pd.api.types.is_numeric_dtype(use[c])]
    if non_numeric:
        # Print so it's visible — these are the columns we silently drop
        print(f'  [prepare] dropping non-numeric cols: {non_numeric}')
        use = use.drop(columns=non_numeric)

    # Impute remaining NaN with median (or 0 for bool/Int cols)
    for c in use.columns:
        s = pd.to_numeric(use[c], errors='coerce')
        if s.isna().any():
            med = s.median()
            if pd.isna(med):
                med = 0
            s = s.fillna(med)
        use[c] = s.astype(float)

    feature_names = list(use.columns)
    X = use[feature_names].values.astype(float)

    return X, y, feature_names, meta, (new_cats if fitted_cats is None else fitted_cats)


def class_balance(y):
    pos = int(y.sum())
    neg = int(len(y) - pos)
    return pos, neg, (pos / max(1, len(y)))
