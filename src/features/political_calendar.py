#!/usr/bin/env python3
"""
Compute political-calendar features for each case in minority_incidents.

Reads:
  - data/external/political_calendar.csv  (date, event_type, description, severity)
  - db_predictive_policing.minority_incidents

Writes:
  - db_predictive_policing.minority_features_political_calendar
  - data/processed/features_political_calendar.csv
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
SCHEMA_PATH = os.path.join(HERE, 'schema_political_calendar.sql')
PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
CAL_CSV = os.path.join(PROJECT, 'data', 'external', 'political_calendar.csv')
CSV_OUT = os.path.join(PROJECT, 'data', 'processed',
                        'features_political_calendar.csv')


def _td_days(td):
    return int(td / np.timedelta64(1, 'D'))


def _days_to_next(case_dt, sorted_dates):
    if len(sorted_dates) == 0:
        return None
    idx = np.searchsorted(sorted_dates, case_dt, side='left')
    if idx == len(sorted_dates):
        return None
    return _td_days(sorted_dates[idx] - case_dt)


def _days_since_last(case_dt, sorted_dates):
    if len(sorted_dates) == 0:
        return None
    idx = np.searchsorted(sorted_dates, case_dt, side='left')
    if idx == 0:
        return None
    return _td_days(case_dt - sorted_dates[idx - 1])


def main():
    cal = pd.read_csv(CAL_CSV, parse_dates=['date'])
    print(f'[load] political events: {len(cal)}')
    cal['date'] = cal['date'].dt.normalize()
    cal['severity'] = cal['severity'].astype(str).str.lower()

    all_dates = np.sort(cal['date'].values).astype('datetime64[ns]')
    major_dates = np.sort(
        cal[cal['severity'] == 'major']['date'].values
    ).astype('datetime64[ns]')
    election_dates = np.sort(
        cal[cal['event_type'].isin(['national_election', 'by_election'])]['date'].values
    ).astype('datetime64[ns]')
    protest_dates = np.sort(
        cal[cal['event_type'] == 'protest']['date'].values
    ).astype('datetime64[ns]')

    pre = get_db_postgres_predictive()
    df = pd.read_sql("SELECT id, incident_date FROM minority_incidents", pre)
    df['incident_date'] = pd.to_datetime(df['incident_date'], errors='coerce')
    print(f'[load] cases: {len(df):,}  (missing date: {df["incident_date"].isna().sum()})')

    rows = []
    for _, r in df.iterrows():
        cid = int(r['id'])
        dt = r['incident_date']
        if pd.isna(dt):
            rows.append({
                'case_id': cid,
                'days_to_next_political_event': None,
                'days_since_last_political_event': None,
                'days_to_next_major_political_event': None,
                'days_since_last_major_political_event': None,
                'in_election_period': None,
                'is_protest_window': None,
                'political_event_density_30d': None,
            })
            continue
        cdt = np.datetime64(dt.normalize(), 'ns')

        # Density in ±15 days
        lo = cdt - np.timedelta64(15, 'D')
        hi = cdt + np.timedelta64(15, 'D')
        density = int(((all_dates >= lo) & (all_dates <= hi)).sum())

        # Election period (±30 days from any election)
        in_elec = False
        if len(election_dates) > 0:
            diffs = np.abs((election_dates - cdt) / np.timedelta64(1, 'D'))
            in_elec = bool((diffs <= 30).any())

        # Protest window (±7 days from any protest)
        in_protest = False
        if len(protest_dates) > 0:
            diffs = np.abs((protest_dates - cdt) / np.timedelta64(1, 'D'))
            in_protest = bool((diffs <= 7).any())

        rows.append({
            'case_id': cid,
            'days_to_next_political_event': _days_to_next(cdt, all_dates),
            'days_since_last_political_event': _days_since_last(cdt, all_dates),
            'days_to_next_major_political_event': _days_to_next(cdt, major_dates),
            'days_since_last_major_political_event': _days_since_last(cdt, major_dates),
            'in_election_period': in_elec,
            'is_protest_window': in_protest,
            'political_event_density_30d': density,
        })

    feats = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(CSV_OUT), exist_ok=True)
    feats.to_csv(CSV_OUT, index=False)
    print(f'[OK] CSV: {CSV_OUT}')

    cur = pre.cursor()
    with open(SCHEMA_PATH) as f:
        cur.execute(f.read())
    pre.commit()
    print('[ddl] minority_features_political_calendar recreated')

    INSERT = """INSERT INTO minority_features_political_calendar (
        case_id,
        days_to_next_political_event, days_since_last_political_event,
        days_to_next_major_political_event, days_since_last_major_political_event,
        in_election_period, is_protest_window, political_event_density_30d,
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
            _i(r['days_to_next_political_event']),
            _i(r['days_since_last_political_event']),
            _i(r['days_to_next_major_political_event']),
            _i(r['days_since_last_major_political_event']),
            _b(r['in_election_period']),
            _b(r['is_protest_window']),
            _i(r['political_event_density_30d']),
            now,
        ))
    pre.commit()

    print('\n=== Summary ===')
    print(f'in_election_period share:    {feats["in_election_period"].mean():.3f}')
    print(f'is_protest_window share:     {feats["is_protest_window"].mean():.3f}')
    for c in ['days_to_next_political_event',
               'days_since_last_political_event',
               'political_event_density_30d']:
        s = pd.to_numeric(feats[c], errors='coerce').dropna()
        if len(s):
            print(f'  {c:<42} mean={s.mean():>6.2f} median={s.median():>5.0f} max={s.max():>5.0f}')

    cur.close(); pre.close()
    print('[done]')


if __name__ == '__main__':
    main()
