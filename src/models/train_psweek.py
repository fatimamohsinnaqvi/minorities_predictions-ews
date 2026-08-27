#!/usr/bin/env python3
"""
Train PS-week forecasting model.

  Source: db_predictive_policing.minority_psweek_train
  Target: target_30d (any strict-targeted minority incident at this PS
                       in the 30 days AFTER week_start)
  Split:  temporal — train weeks ending 2025-12-31, test weeks 2026+

Trains LR + RF and writes:
  outputs/models/psweek_lr.pkl
  outputs/models/psweek_rf.pkl
  outputs/reports/psweek_metrics.json
  outputs/figures/model/psweek_*.png
"""
import json
import os
import sys
from datetime import datetime

import joblib
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
from evaluate import overall_metrics, per_group_breakdown  # noqa

PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
MODEL_DIR = os.path.join(PROJECT, 'outputs', 'models')
REPORTS_DIR = os.path.join(PROJECT, 'outputs', 'reports')
FIG_DIR = os.path.join(PROJECT, 'outputs', 'figures', 'model')
for d in (MODEL_DIR, REPORTS_DIR, FIG_DIR):
    os.makedirs(d, exist_ok=True)


# Columns that are identifiers / metadata, NOT features
NON_FEATURE = {
    'police_station_id', 'police_station',
    'district_id', 'district_name',
    'week_start_date',
    'target_7d', 'target_30d',
}


def prep(df, fitted_cats=None):
    use = df.drop(columns=[c for c in NON_FEATURE if c in df.columns])
    # Booleans → int
    for c in list(use.columns):
        if use[c].dtype == bool:
            use[c] = use[c].astype(int)
    # Numeric only
    use = use.apply(pd.to_numeric, errors='coerce')
    # Impute with column median (or 0 if undefined)
    for c in use.columns:
        if use[c].isna().any():
            med = use[c].median()
            if pd.isna(med):
                med = 0
            use[c] = use[c].fillna(med)
    feat_names = list(use.columns)
    X = use[feat_names].values.astype(float)
    return X, feat_names


def main():
    conn = get_db_postgres_predictive()
    df = pd.read_sql("SELECT * FROM minority_psweek_train", conn)
    conn.close()
    df['week_start_date'] = pd.to_datetime(df['week_start_date'])
    print(f'[load] {len(df):,} PS-weeks')

    # Temporal split
    train_df = df[df['week_start_date'] < '2026-01-01'].copy()
    test_df  = df[df['week_start_date'] >= '2026-01-01'].copy()
    print(f'  train (<2026): {len(train_df):,}  pos_rate={train_df["target_30d"].mean():.4f}')
    print(f'  test  (2026+): {len(test_df):,}  pos_rate={test_df["target_30d"].mean():.4f}')

    X_train, feat_names = prep(train_df)
    y_train = train_df['target_30d'].astype(int).values
    X_test,  _          = prep(test_df)
    y_test  = test_df['target_30d'].astype(int).values

    print(f'\n[train] LR …')
    lr_pipe = Pipeline([
        ('scaler', StandardScaler()),
        ('lr', LogisticRegression(class_weight='balanced',
                                  max_iter=5000, solver='lbfgs', n_jobs=-1)),
    ])
    lr_pipe.fit(X_train, y_train)
    lr_train = lr_pipe.predict_proba(X_train)[:, 1]
    lr_test  = lr_pipe.predict_proba(X_test)[:, 1]

    print('[train] RF …')
    rf = RandomForestClassifier(
        n_estimators=300, max_depth=None, min_samples_leaf=4,
        class_weight='balanced', n_jobs=-1, random_state=42)
    rf.fit(X_train, y_train)
    rf_train = rf.predict_proba(X_train)[:, 1]
    rf_test  = rf.predict_proba(X_test)[:, 1]

    # Metrics
    print('\n=== LR test (target_30d) ===')
    lr_m = overall_metrics(y_test, lr_test)
    for k, v in lr_m.items(): print(f'  {k:<25} {v}')
    print('\n=== RF test (target_30d) ===')
    rf_m = overall_metrics(y_test, rf_test)
    for k, v in rf_m.items(): print(f'  {k:<25} {v}')

    # Per-Lahore breakdown (small, but illustrative)
    lah = per_group_breakdown(y_test, rf_test,
                               test_df['is_lahore'].fillna(False).astype(bool),
                               group_name='is_lahore')

    # Top RF features
    imp = pd.DataFrame({'feature': feat_names,
                        'importance': rf.feature_importances_})\
            .sort_values('importance', ascending=False).head(20)

    # Save
    joblib.dump({'pipeline': lr_pipe, 'feature_names': feat_names,
                  'trained_at': datetime.utcnow().isoformat()},
                 os.path.join(MODEL_DIR, 'psweek_lr.pkl'))
    joblib.dump({'model': rf, 'feature_names': feat_names,
                  'trained_at': datetime.utcnow().isoformat()},
                 os.path.join(MODEL_DIR, 'psweek_rf.pkl'))
    print(f'\n[OK] models saved.')

    # Feature importance plot
    fig, ax = plt.subplots(figsize=(8, 6))
    imp.iloc[::-1].plot(kind='barh', x='feature', y='importance',
                         ax=ax, color='#16a085', legend=False)
    ax.set_title('PS-week forecaster — RF top features', fontweight='bold')
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, 'psweek_rf_importance.png'),
                dpi=130, bbox_inches='tight')
    plt.close(fig)

    summary = {
        'target': 'target_30d',
        'train_rows': len(train_df),
        'test_rows':  len(test_df),
        'train_pos_rate': float(train_df['target_30d'].mean()),
        'test_pos_rate':  float(test_df['target_30d'].mean()),
        'features_count': len(feat_names),
        'lr_test_metrics': lr_m,
        'rf_test_metrics': rf_m,
        'lahore_breakdown_rf': lah.to_dict('records'),
        'rf_top_features': imp.to_dict('records'),
    }
    with open(os.path.join(REPORTS_DIR, 'psweek_metrics.json'), 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f'[OK] metrics: {os.path.join(REPORTS_DIR, "psweek_metrics.json")}')

    print('\n[top RF features]')
    print(imp.to_string(index=False))


if __name__ == '__main__':
    main()
