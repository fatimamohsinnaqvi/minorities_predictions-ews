#!/usr/bin/env python3
"""
Export every DB table this project owns to CSV, into data/csv_snapshot/.

After running this, the folder `minorities_project/` is fully self-
contained — you can ZIP it, copy it to any machine, and:

  - Open `outputs/dashboards/dashboard.html` in a browser (no setup needed)
  - Open any CSV in Excel
  - Re-load the data into another Postgres or SQLite if you want to keep
    running the analytical pipeline

CSVs are versioned by inclusion of `loaded_at` / `generated_at` columns
where the tables have them.
"""
import os
import sys
from datetime import datetime

import pandas as pd

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
OUT_DIR = os.path.join(PROJECT, 'data', 'csv_snapshot')
os.makedirs(OUT_DIR, exist_ok=True)


TABLES = [
    # name                                      , description
    ('minority_incidents',                       '4,110 case records (Punjab-wide working set)'),
    ('minority_features_prior_density',          '11-column feature family — rolling case counts'),
    ('minority_features_religious_calendar',     '12-column feature family — days to next religious events'),
    ('minority_features_political_calendar',     '7-column feature family — political event proximity'),
    ('minority_features_misinformation',         '7-column feature family — misinfo event flags'),
    ('minority_features_responsiveness',         '6-column feature family — per-PS Emergency-15 baseline'),
    ('minority_features_sentiment',              '6-column placeholder — all NULL (no data source)'),
    ('minority_features_merged',                 '62 columns × 4,110 rows — training-ready table'),
    ('minority_predictions',                     'Per-case LR + RF scores'),
    ('minority_psweek_train',                    'Per-(PS, week) training table for the forecaster (82,000 rows)'),
    ('minority_psweek_forward',                  'Per-PS forecast for next 30 days (656 rows)'),
]


def main():
    conn = get_db_postgres_predictive()
    manifest = [
        ['table_name', 'row_count', 'columns', 'file', 'description', 'exported_at']
    ]
    now = datetime.utcnow().isoformat()
    for tname, desc in TABLES:
        try:
            df = pd.read_sql(f'SELECT * FROM {tname}', conn)
        except Exception as e:
            print(f'  ✗ {tname}: {e}')
            continue
        path = os.path.join(OUT_DIR, f'{tname}.csv')
        df.to_csv(path, index=False)
        n_rows = len(df)
        n_cols = len(df.columns)
        sz = os.path.getsize(path)
        print(f'  ✓ {tname:<42} {n_rows:>7,} rows × {n_cols:>2} cols → {sz/1024:>6.0f} KB')
        manifest.append([tname, n_rows, n_cols, f'{tname}.csv', desc, now])
    conn.close()

    # Write manifest
    manifest_df = pd.DataFrame(manifest[1:], columns=manifest[0])
    manifest_path = os.path.join(OUT_DIR, '_manifest.csv')
    manifest_df.to_csv(manifest_path, index=False)
    print(f'\n[OK] CSV snapshot at: {OUT_DIR}')
    print(f'[OK] Manifest:         {manifest_path}')
    print(f'\nTotal: {len(manifest_df)} tables exported.')


if __name__ == '__main__':
    main()
