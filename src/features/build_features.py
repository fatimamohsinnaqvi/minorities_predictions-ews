#!/usr/bin/env python3
"""
Merge all six feature tables into a single training-ready table.

Reads:
  - db_predictive_policing.minority_incidents                       (target + IDs)
  - db_predictive_policing.minority_features_prior_density
  - db_predictive_policing.minority_features_religious_calendar
  - db_predictive_policing.minority_features_political_calendar
  - db_predictive_policing.minority_features_misinformation
  - db_predictive_policing.minority_features_responsiveness
  - db_predictive_policing.minority_features_sentiment

Writes:
  - db_predictive_policing.minority_features_merged
  - data/processed/features_merged.csv

This is the table the W7-8 models consume.
"""
import os
import sys
from datetime import datetime

import pandas as pd

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
CSV_OUT = os.path.join(PROJECT, 'data', 'processed', 'features_merged.csv')


def main():
    conn = get_db_postgres_predictive()

    # Pull base + each feature table
    print('[load] base (minority_incidents) ...')
    base = pd.read_sql("""
        SELECT id AS case_id, incident_date, incident_year, incident_month,
               district_id, district_name, police_station_id, police_station,
               is_lahore, minority_community, level3_case_nature,
               match_source, is_minority_targeted
        FROM minority_incidents
    """, conn)

    def _load(table, name):
        print(f'[load] {name} ...')
        return pd.read_sql(f"SELECT * FROM {table}", conn)

    pdens = _load('minority_features_prior_density', 'prior_density')
    relcal = _load('minority_features_religious_calendar', 'religious_calendar')
    polcal = _load('minority_features_political_calendar', 'political_calendar')
    misinfo = _load('minority_features_misinformation', 'misinformation')
    resp = _load('minority_features_responsiveness', 'responsiveness')
    sent = _load('minority_features_sentiment', 'sentiment')

    # Drop generated_at from each
    for d in [pdens, relcal, polcal, misinfo, resp, sent]:
        if 'generated_at' in d.columns:
            d.drop(columns=['generated_at'], inplace=True)

    # Merge on case_id
    merged = base
    for d in [pdens, relcal, polcal, misinfo, resp, sent]:
        merged = merged.merge(d, on='case_id', how='left')

    print(f'\n[merge] result: {len(merged):,} rows × {len(merged.columns)} columns')

    # Write CSV
    os.makedirs(os.path.dirname(CSV_OUT), exist_ok=True)
    merged.to_csv(CSV_OUT, index=False)
    print(f'[OK] CSV: {CSV_OUT}')

    # Write DB — re-create table dynamically from pandas dtypes
    print('[ddl] minority_features_merged recreating ...')
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS minority_features_merged")

    type_map = {
        'int64': 'BIGINT',
        'Int64': 'BIGINT',
        'float64': 'DOUBLE PRECISION',
        'bool':   'BOOLEAN',
        'object': 'TEXT',
        'datetime64[ns]': 'TIMESTAMP',
    }
    cols_sql = []
    for c in merged.columns:
        dt = str(merged[c].dtype)
        pg = type_map.get(dt, 'TEXT')
        cols_sql.append(f'    "{c}" {pg}')
    ddl = (
        'CREATE TABLE minority_features_merged (\n'
        + ',\n'.join(cols_sql)
        + '\n)'
    )
    cur.execute(ddl)
    cur.execute('CREATE INDEX idx_mfm_case ON minority_features_merged(case_id)')
    cur.execute('CREATE INDEX idx_mfm_target ON minority_features_merged(is_minority_targeted)')
    conn.commit()

    # Bulk insert via tuples
    cols = list(merged.columns)
    placeholders = ', '.join(['%s'] * len(cols))
    quoted_cols = ', '.join(f'"{c}"' for c in cols)
    INSERT = f"INSERT INTO minority_features_merged ({quoted_cols}) VALUES ({placeholders})"

    rows = []
    for _, r in merged.iterrows():
        row = []
        for c in cols:
            v = r[c]
            # pandas NaN → None
            if isinstance(v, float) and pd.isna(v):
                v = None
            elif v is pd.NaT:
                v = None
            row.append(v)
        rows.append(tuple(row))
    cur.executemany(INSERT, rows)
    conn.commit()

    print(f'[OK] inserted {len(rows):,} rows into minority_features_merged')

    # Quick summary
    print('\n=== Feature column families in merged ===')
    families = {
        'base/identity': ['case_id','incident_date','incident_year','incident_month',
                           'district_id','district_name','police_station_id',
                           'police_station','is_lahore','minority_community',
                           'level3_case_nature','match_source','is_minority_targeted'],
        'prior_density': [c for c in pdens.columns if c != 'case_id'],
        'religious_calendar': [c for c in relcal.columns if c != 'case_id'],
        'political_calendar': [c for c in polcal.columns if c != 'case_id'],
        'misinformation': [c for c in misinfo.columns if c != 'case_id'],
        'responsiveness': [c for c in resp.columns if c != 'case_id'],
        'sentiment (placeholder)': [c for c in sent.columns if c != 'case_id'],
    }
    for fam, cols_f in families.items():
        present = [c for c in cols_f if c in merged.columns]
        print(f'  {fam:<28} {len(present)} cols')

    cur.close(); conn.close()
    print('\n[done]')


if __name__ == '__main__':
    main()
