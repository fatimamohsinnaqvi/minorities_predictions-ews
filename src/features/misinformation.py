#!/usr/bin/env python3
"""
Compute misinformation-propagation features for each case in minority_incidents.

Reads:
  - data/external/misinformation_events.csv
      (date, district, community_target, description, severity)
  - db_predictive_policing.minority_incidents

Writes:
  - db_predictive_policing.minority_features_misinformation
  - data/processed/features_misinformation.csv

A "Punjab" district in the external CSV is treated as a wildcard — applies
to incidents in any district.
"""
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, 'schema_misinformation.sql')
PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
EV_CSV = os.path.join(PROJECT, 'data', 'external', 'misinformation_events.csv')
CSV_OUT = os.path.join(PROJECT, 'data', 'processed',
                        'features_misinformation.csv')

WINDOW_DAYS = 7
DAYS_SINCE_CAP = 60


def main():
    ev = pd.read_csv(EV_CSV, parse_dates=['date'])
    ev['date'] = ev['date'].dt.normalize()
    ev['district'] = ev['district'].astype(str).str.strip()
    ev['community_target'] = ev['community_target'].astype(str).str.strip().str.lower()
    ev['severity'] = ev['severity'].astype(int)
    print(f'[load] misinformation events: {len(ev)}  '
          f'(districts: {ev["district"].nunique()})')

    pre = get_db_postgres_predictive()
    df = pd.read_sql("""
        SELECT id, incident_date, district_name, minority_community
        FROM minority_incidents
    """, pre)
    df['incident_date'] = pd.to_datetime(df['incident_date'], errors='coerce')
    print(f'[load] cases: {len(df):,}  (missing date: {df["incident_date"].isna().sum()})')

    rows = []
    for _, r in df.iterrows():
        cid = int(r['id'])
        dt = r['incident_date']
        case_dist = (r['district_name'] or '').strip()
        case_comm = (r['minority_community'] or '').strip().lower()

        if pd.isna(dt):
            rows.append({
                'case_id': cid,
                'misinfo_event_in_window_district': None,
                'misinfo_event_severity_district': None,
                'days_since_last_misinfo_event_district': None,
                'misinfo_event_in_window_anywhere': None,
                'misinfo_event_severity_anywhere': None,
                'days_since_last_misinfo_event_anywhere': None,
                'misinfo_event_in_window_same_community': None,
            })
            continue

        cdt = pd.Timestamp(dt).normalize()
        lo = cdt - pd.Timedelta(days=WINDOW_DAYS)
        hi = cdt + pd.Timedelta(days=WINDOW_DAYS)

        # In-window events at any district (incl. Punjab wildcard)
        in_win_any = ev[(ev['date'] >= lo) & (ev['date'] <= hi)]
        # In-window events at same district OR Punjab wildcard
        in_win_dist = in_win_any[
            (in_win_any['district'] == case_dist)
            | (in_win_any['district'].str.lower() == 'punjab')
        ]
        # In-window same community
        in_win_comm = in_win_dist[in_win_dist['community_target'] == case_comm]

        # Days since last event (district, capped at 60)
        past_dist = ev[(ev['date'] < cdt) & (
            (ev['district'] == case_dist) | (ev['district'].str.lower() == 'punjab')
        )]
        if not past_dist.empty:
            d_since_dist = int((cdt - past_dist['date'].max()).days)
            d_since_dist = min(d_since_dist, DAYS_SINCE_CAP)
        else:
            d_since_dist = None

        past_any = ev[ev['date'] < cdt]
        if not past_any.empty:
            d_since_any = int((cdt - past_any['date'].max()).days)
            d_since_any = min(d_since_any, DAYS_SINCE_CAP)
        else:
            d_since_any = None

        rows.append({
            'case_id': cid,
            'misinfo_event_in_window_district': bool(len(in_win_dist) > 0),
            'misinfo_event_severity_district': int(in_win_dist['severity'].max()) if len(in_win_dist) > 0 else None,
            'days_since_last_misinfo_event_district': d_since_dist,
            'misinfo_event_in_window_anywhere': bool(len(in_win_any) > 0),
            'misinfo_event_severity_anywhere': int(in_win_any['severity'].max()) if len(in_win_any) > 0 else None,
            'days_since_last_misinfo_event_anywhere': d_since_any,
            'misinfo_event_in_window_same_community': bool(len(in_win_comm) > 0),
        })

    feats = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(CSV_OUT), exist_ok=True)
    feats.to_csv(CSV_OUT, index=False)
    print(f'[OK] CSV: {CSV_OUT}')

    cur = pre.cursor()
    with open(SCHEMA_PATH) as f:
        cur.execute(f.read())
    pre.commit()
    print('[ddl] minority_features_misinformation recreated')

    INSERT = """INSERT INTO minority_features_misinformation (
        case_id,
        misinfo_event_in_window_district, misinfo_event_severity_district,
        days_since_last_misinfo_event_district,
        misinfo_event_in_window_anywhere, misinfo_event_severity_anywhere,
        days_since_last_misinfo_event_anywhere,
        misinfo_event_in_window_same_community,
        generated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""

    def _i(v):
        if v is None: return None
        if isinstance(v, float) and np.isnan(v): return None
        return int(v)

    def _b(v):
        if v is None: return None
        if isinstance(v, float) and np.isnan(v): return None
        return bool(v)

    now = datetime.utcnow()
    for _, r in feats.iterrows():
        cur.execute(INSERT, (
            int(r['case_id']),
            _b(r['misinfo_event_in_window_district']),
            _i(r['misinfo_event_severity_district']),
            _i(r['days_since_last_misinfo_event_district']),
            _b(r['misinfo_event_in_window_anywhere']),
            _i(r['misinfo_event_severity_anywhere']),
            _i(r['days_since_last_misinfo_event_anywhere']),
            _b(r['misinfo_event_in_window_same_community']),
            now,
        ))
    pre.commit()

    print('\n=== Summary ===')
    for c in ['misinfo_event_in_window_district',
               'misinfo_event_in_window_anywhere',
               'misinfo_event_in_window_same_community']:
        share = feats[c].dropna().astype(bool).mean()
        n = int(feats[c].dropna().astype(bool).sum())
        print(f'  {c:<48} share={share:>5.3f}  (n={n})')

    cur.close(); pre.close()
    print('[done]')


if __name__ == '__main__':
    main()
