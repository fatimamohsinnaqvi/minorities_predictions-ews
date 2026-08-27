#!/usr/bin/env python3
"""
Score every row in minority_features_merged with both trained models
and write predictions back to the database for downstream use.

Output:
  db_predictive_policing.minority_predictions
    one row per case_id with: lr_score, rf_score, lr_class, rf_class
    (at threshold 0.5)
"""
import os
import sys
from datetime import datetime

import joblib
import numpy as np
import pandas as pd

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
from dataset import load_merged, prepare  # noqa

PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
MODEL_DIR = os.path.join(PROJECT, 'outputs', 'models')


SCHEMA = """
DROP TABLE IF EXISTS minority_predictions;
CREATE TABLE minority_predictions (
    case_id           INTEGER PRIMARY KEY,
    lr_score          DOUBLE PRECISION,
    rf_score          DOUBLE PRECISION,
    lr_class          INTEGER,      -- 0/1 at threshold 0.5
    rf_class          INTEGER,
    is_minority_targeted BOOLEAN,   -- ground truth (for QA only)
    incident_year     INTEGER,
    district_name     TEXT,
    police_station    TEXT,
    is_lahore         BOOLEAN,
    generated_at      TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_mp_lahore ON minority_predictions(is_lahore);
CREATE INDEX idx_mp_rf     ON minority_predictions(rf_score);
"""


def main():
    print('[load] data + models ...')
    df = load_merged()

    lr_pkg = joblib.load(os.path.join(MODEL_DIR, 'lr_baseline.pkl'))
    rf_pkg = joblib.load(os.path.join(MODEL_DIR, 'rf.pkl'))

    lr_pipe = lr_pkg['pipeline']
    rf_model = rf_pkg['model']
    train_feats_lr = lr_pkg['feature_names']
    train_feats_rf = rf_pkg['feature_names']
    fitted_cats = lr_pkg['fitted_cats']

    # Prepare full dataset using train-set categoricals
    X, y, feat_names, meta, _ = prepare(df, fitted_cats=fitted_cats)
    X_df = pd.DataFrame(X, columns=feat_names)

    # Align columns to LR's training set
    X_lr = X_df.reindex(columns=train_feats_lr, fill_value=0.0).values
    X_rf = X_df.reindex(columns=train_feats_rf, fill_value=0.0).values

    print('[predict] LR ...')
    lr_scores = lr_pipe.predict_proba(X_lr)[:, 1]
    print('[predict] RF ...')
    rf_scores = rf_model.predict_proba(X_rf)[:, 1]

    out = pd.DataFrame({
        'case_id': meta['case_id'],
        'lr_score': lr_scores,
        'rf_score': rf_scores,
        'lr_class': (lr_scores >= 0.5).astype(int),
        'rf_class': (rf_scores >= 0.5).astype(int),
        'is_minority_targeted': y.astype(bool),
        'incident_year': meta['incident_year'],
        'district_name': meta['district_name'],
        'police_station': meta['police_station'],
        'is_lahore': meta['is_lahore'],
    })

    csv_out = os.path.join(PROJECT, 'data', 'processed', 'predictions.csv')
    out.to_csv(csv_out, index=False)
    print(f'[OK] CSV: {csv_out}')

    conn = get_db_postgres_predictive()
    cur = conn.cursor()
    cur.execute(SCHEMA)
    conn.commit()
    print('[ddl] minority_predictions recreated')

    INSERT = """INSERT INTO minority_predictions (
        case_id, lr_score, rf_score, lr_class, rf_class,
        is_minority_targeted, incident_year, district_name,
        police_station, is_lahore, generated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

    now = datetime.utcnow()
    for _, r in out.iterrows():
        cur.execute(INSERT, (
            int(r['case_id']),
            float(r['lr_score']), float(r['rf_score']),
            int(r['lr_class']), int(r['rf_class']),
            bool(r['is_minority_targeted']),
            int(r['incident_year']) if not pd.isna(r['incident_year']) else None,
            r['district_name'],
            r['police_station'],
            bool(r['is_lahore']),
            now,
        ))
    conn.commit()
    cur.close(); conn.close()
    print(f'[OK] inserted {len(out):,} predictions into minority_predictions')


if __name__ == '__main__':
    main()
