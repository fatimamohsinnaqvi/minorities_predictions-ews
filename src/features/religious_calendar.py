#!/usr/bin/env python3
"""
Compute religious-calendar features for each case in minority_incidents.

Reads:
  - db_predictive_policing.minority_incidents
  - data/external/religious_calendar.csv  (date, community, event_name, significance)

Writes:
  - db_predictive_policing.minority_features_religious_calendar
  - data/processed/features_religious_calendar.csv

Features per case (see schema_religious_calendar.sql for full definitions):
  days_to_next_<community>_event       — days until the next event (NULL if none)
  days_since_last_<community>_event    — days since the last event   (NULL if none)
  days_to_next_any_event               — closest upcoming any-community event
  is_multi_religion_overlap_week       — 2+ communities have an event within ±3 days
  religious_density_score              — weighted (major=2, observance=1) sum of
                                          events in ±7-day window
  on_major_event_day                   — 1 if incident is within ±1 day of any
                                          major event
"""
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, 'schema_religious_calendar.sql')
PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
CALENDAR_CSV = os.path.join(PROJECT, 'data', 'external', 'religious_calendar.csv')
CSV_OUT = os.path.join(PROJECT, 'data', 'processed',
                        'features_religious_calendar.csv')

COMMUNITIES = ['islamic', 'christian', 'hindu', 'sikh']
WEIGHT = {'major': 2.0, 'observance': 1.0}


def _td_days(td):
    """numpy timedelta64 → integer days."""
    return int(td / np.timedelta64(1, 'D'))


def _days_to_next(case_dt, sorted_dates):
    """For one case date, return days until the next date in sorted_dates
    (>=case_dt), or NaN if none."""
    if len(sorted_dates) == 0:
        return np.nan
    idx = np.searchsorted(sorted_dates, case_dt, side='left')
    if idx == len(sorted_dates):
        return np.nan
    return _td_days(sorted_dates[idx] - case_dt)


def _days_since_last(case_dt, sorted_dates):
    """Days since the most recent date strictly before case_dt."""
    if len(sorted_dates) == 0:
        return np.nan
    idx = np.searchsorted(sorted_dates, case_dt, side='left')
    if idx == 0:
        return np.nan
    return _td_days(case_dt - sorted_dates[idx - 1])


def main():
    # ---- load calendar
    cal = pd.read_csv(CALENDAR_CSV, parse_dates=['date'])
    print(f'[load] calendar events: {len(cal)}')
    cal['community'] = cal['community'].str.strip().str.lower()
    cal['significance'] = cal['significance'].str.strip().str.lower()
    print(f'  by community: {cal["community"].value_counts().to_dict()}')

    # Per-community sorted-date arrays
    by_comm = {}
    for c in COMMUNITIES:
        dates = cal[cal['community'] == c]['date'].dt.normalize().sort_values().values
        by_comm[c] = dates.astype('datetime64[D]').astype('datetime64[ns]')
    all_dates_sorted = np.sort(cal['date'].dt.normalize().values).astype('datetime64[ns]')

    # Cal as sorted records for window scans
    cal_sorted = cal.sort_values('date').reset_index(drop=True)

    # ---- load incidents
    conn = get_db_postgres_predictive()
    df = pd.read_sql("""
        SELECT id, incident_date FROM minority_incidents
    """, conn)
    df['incident_date'] = pd.to_datetime(df['incident_date'], errors='coerce')
    n_no_date = int(df['incident_date'].isna().sum())
    print(f'[load] cases: {len(df):,}  (missing date: {n_no_date})')

    # ---- compute per-case features
    rows = []
    for _, r in df.iterrows():
        case_id = int(r['id'])
        dt = r['incident_date']
        if pd.isna(dt):
            rows.append({
                'case_id': case_id,
                **{f'days_to_next_{c}_event': None for c in COMMUNITIES},
                **{f'days_since_last_{c}_event': None for c in COMMUNITIES},
                'days_to_next_any_event': None,
                'is_multi_religion_overlap_week': None,
                'religious_density_score': None,
                'on_major_event_day': None,
            })
            continue
        case_dt = np.datetime64(dt.normalize(), 'ns')

        row = {'case_id': case_id}
        # per-community next + previous
        for c in COMMUNITIES:
            row[f'days_to_next_{c}_event']   = _days_to_next(case_dt, by_comm[c])
            row[f'days_since_last_{c}_event'] = _days_since_last(case_dt, by_comm[c])

        # any-community next
        row['days_to_next_any_event'] = _days_to_next(case_dt, all_dates_sorted)

        # multi-religion overlap within ±3 days
        lo = case_dt - np.timedelta64(3, 'D')
        hi = case_dt + np.timedelta64(3, 'D')
        in_win = cal_sorted[(cal_sorted['date'].values >= lo) &
                             (cal_sorted['date'].values <= hi)]
        row['is_multi_religion_overlap_week'] = (
            in_win['community'].nunique() >= 2)

        # weighted density in ±7 days
        lo7 = case_dt - np.timedelta64(7, 'D')
        hi7 = case_dt + np.timedelta64(7, 'D')
        in7 = cal_sorted[(cal_sorted['date'].values >= lo7) &
                          (cal_sorted['date'].values <= hi7)]
        row['religious_density_score'] = float(
            in7['significance'].map(WEIGHT).sum())

        # on major event day (±1 day) of any community
        lo1 = case_dt - np.timedelta64(1, 'D')
        hi1 = case_dt + np.timedelta64(1, 'D')
        in1 = cal_sorted[(cal_sorted['date'].values >= lo1) &
                          (cal_sorted['date'].values <= hi1)]
        row['on_major_event_day'] = bool((in1['significance'] == 'major').any())

        rows.append(row)

    feats = pd.DataFrame(rows)

    # ---- write CSV
    os.makedirs(os.path.dirname(CSV_OUT), exist_ok=True)
    feats.to_csv(CSV_OUT, index=False)
    print(f'\n[OK] CSV: {CSV_OUT}  ({len(feats):,} rows)')

    # ---- write DB
    cur = conn.cursor()
    with open(SCHEMA_PATH) as f:
        cur.execute(f.read())
    conn.commit()
    print('[ddl] minority_features_religious_calendar recreated')

    INSERT = """INSERT INTO minority_features_religious_calendar (
        case_id,
        days_to_next_islamic_event, days_to_next_christian_event,
        days_to_next_hindu_event, days_to_next_sikh_event,
        days_to_next_any_event,
        days_since_last_islamic_event, days_since_last_christian_event,
        days_since_last_hindu_event, days_since_last_sikh_event,
        is_multi_religion_overlap_week, religious_density_score,
        on_major_event_day, generated_at
    ) VALUES (
        %s,
        %s, %s, %s, %s,
        %s,
        %s, %s, %s, %s,
        %s, %s,
        %s, %s
    )"""

    def _opt_int(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return int(v)

    def _opt_float(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)

    def _opt_bool(v):
        if v is None:
            return None
        if isinstance(v, float) and np.isnan(v):
            return None
        return bool(v)

    now = datetime.utcnow()
    for _, r in feats.iterrows():
        cur.execute(INSERT, (
            int(r['case_id']),
            _opt_int(r['days_to_next_islamic_event']),
            _opt_int(r['days_to_next_christian_event']),
            _opt_int(r['days_to_next_hindu_event']),
            _opt_int(r['days_to_next_sikh_event']),
            _opt_int(r['days_to_next_any_event']),
            _opt_int(r['days_since_last_islamic_event']),
            _opt_int(r['days_since_last_christian_event']),
            _opt_int(r['days_since_last_hindu_event']),
            _opt_int(r['days_since_last_sikh_event']),
            _opt_bool(r['is_multi_religion_overlap_week']),
            _opt_float(r['religious_density_score']),
            _opt_bool(r['on_major_event_day']),
            now,
        ))
    conn.commit()

    # ---- summary
    print('\n=== Summary (Punjab-wide) ===')
    print(f'{"feature":<42} {"mean":>10} {"median":>8} {"min":>6} {"max":>6}')
    for c in feats.columns:
        if c == 'case_id': continue
        s = feats[c]
        # bool columns → show share
        if s.dtype == bool or s.dropna().isin([True, False]).all():
            share = pd.Series([1 if x else 0 for x in s.dropna()])
            mean = share.mean() if len(share) else float('nan')
            print(f'  {c:<42} share={mean:>5.3f}')
            continue
        s = pd.to_numeric(s, errors='coerce').dropna()
        if len(s) == 0:
            print(f'  {c:<42} (all NULL)')
            continue
        print(f'  {c:<42} {s.mean():>10.2f} {s.median():>8.0f} '
              f'{s.min():>6.0f} {s.max():>6.0f}')

    # Cases that fell on a major event day
    n_major = int(feats['on_major_event_day'].fillna(False).sum())
    print(f'\nCases within ±1 day of a major religious event: {n_major} '
          f'({100*n_major/max(1,len(feats)):.1f}% of all cases)')

    cur.close(); conn.close()
    print('[done]')


if __name__ == '__main__':
    main()
