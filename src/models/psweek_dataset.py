#!/usr/bin/env python3
"""
Build the PS-week training table for the forecasting model.

Unit of analysis: (police_station, week_start_date)

For each such row:
  - All features are computed as of `week_start_date - 1 day`
    (strict temporal ordering — no peeking at the future).
  - Targets:
      target_7d  = 1 if any strict-targeted minority_incidents case occurs
                   at this PS in (week_start, week_start+7d]
      target_30d = same with a 30-day horizon

PS universe: every PS that has ≥ 1 minority-related case ever (about 700+).
Weeks: 2024-01-01 through (today - 30d), so the 30-day horizon target is
       fully observed.

Writes:
  - db_predictive_policing.minority_psweek_train
  - data/processed/psweek_train.csv
"""
import os
import sys
from datetime import date, datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive, get_db_postgres_1124  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
CSV_OUT = os.path.join(PROJECT, 'data', 'processed', 'psweek_train.csv')

# Look-ahead windows for the target
HORIZONS = [7, 30]
# Look-back windows for features
LOOKBACK_DAYS = [30, 60, 90]

# Earliest week start; pick a date that gives enough lookback for the
# first row's prior_90d to be defined (or we just accept that the early
# rows have NULL priors)
WEEK_START_FROM = date(2024, 1, 1)


def fetch_minority_incidents():
    conn = get_db_postgres_predictive()
    df = pd.read_sql("""
        SELECT id, incident_date, police_station_id, police_station,
               district_id, district_name, is_lahore,
               is_minority_targeted
        FROM minority_incidents
        WHERE incident_date IS NOT NULL
    """, conn)
    conn.close()
    df['incident_date'] = pd.to_datetime(df['incident_date'])
    df['police_station_id'] = df['police_station_id'].astype('Int64')
    df['district_id'] = df['district_id'].astype(str)
    return df


def fetch_response_time_responsiveness():
    """Return per-PS, per-year-month mean response time + n_cases.
    Used to attach the responsiveness feature to any (PS, ref_date)."""
    conn = get_db_postgres_1124()
    cur = conn.cursor()
    cur.execute("""
        SELECT police_station_id,
               substring(date FROM 1 FOR 7) AS ym,
               AVG(NULLIF(response_time, 0)::float) AS avg_rt_sec,
               COUNT(*) AS n_cases
        FROM response_time
        WHERE police_station_id IS NOT NULL
          AND date IS NOT NULL
          AND date ~ '^[0-9]{4}-[0-9]{2}'
        GROUP BY police_station_id, ym
    """)
    out = {}
    for ps, ym, avg_rt, n in cur.fetchall():
        try:
            y, m = int(ym[:4]), int(ym[5:7])
        except Exception:
            continue
        out[(int(ps), y, m)] = {
            'avg_rt': float(avg_rt) if avg_rt is not None else None,
            'n_cases': int(n),
        }
    cur.close(); conn.close()
    return out


def load_calendar(path, parse_severity=False):
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.normalize()
    return df


def days_to_next(ref_dt, sorted_dates):
    if len(sorted_dates) == 0:
        return None
    idx = np.searchsorted(sorted_dates, ref_dt, side='left')
    if idx == len(sorted_dates):
        return None
    delta = sorted_dates[idx] - ref_dt
    return int(delta / np.timedelta64(1, 'D'))


def days_since_last(ref_dt, sorted_dates):
    if len(sorted_dates) == 0:
        return None
    idx = np.searchsorted(sorted_dates, ref_dt, side='left')
    if idx == 0:
        return None
    delta = ref_dt - sorted_dates[idx - 1]
    return int(delta / np.timedelta64(1, 'D'))


def main():
    print('[load] minority_incidents …')
    inc = fetch_minority_incidents()
    print(f'  {len(inc):,} rows with date')

    # PS universe: every PS with ≥ 1 case
    ps_universe = inc.dropna(subset=['police_station_id']).groupby(
        'police_station_id').first().reset_index()[
        ['police_station_id', 'police_station', 'district_id',
         'district_name', 'is_lahore']]
    print(f'  PS universe: {len(ps_universe):,}')

    # Per-PS sorted date arrays for binary-search counting
    ps_dates_all = {}
    ps_dates_strict = {}
    district_dates_all = {}
    district_dates_strict = {}
    for ps_id, grp in inc.groupby('police_station_id'):
        ps_dates_all[int(ps_id)] = np.sort(
            grp['incident_date'].values).astype('datetime64[ns]')
        ps_dates_strict[int(ps_id)] = np.sort(
            grp[grp['is_minority_targeted']]['incident_date'].values
        ).astype('datetime64[ns]')
    for did, grp in inc.groupby('district_id'):
        district_dates_all[str(did)] = np.sort(
            grp['incident_date'].values).astype('datetime64[ns]')
        district_dates_strict[str(did)] = np.sort(
            grp[grp['is_minority_targeted']]['incident_date'].values
        ).astype('datetime64[ns]')

    # Calendars
    rel = load_calendar(os.path.join(
        PROJECT, 'data', 'external', 'religious_calendar.csv'))
    pol = load_calendar(os.path.join(
        PROJECT, 'data', 'external', 'political_calendar.csv'))
    misinfo = load_calendar(os.path.join(
        PROJECT, 'data', 'external', 'misinformation_events.csv'))
    rel['community'] = rel['community'].str.lower()

    rel_dates_by_comm = {
        c: np.sort(rel[rel['community'] == c]['date'].values).astype('datetime64[ns]')
        for c in ['islamic', 'christian', 'hindu', 'sikh']
    }
    rel_dates_all = np.sort(rel['date'].values).astype('datetime64[ns]')
    rel_major_dates = np.sort(
        rel[rel['significance'] == 'major']['date'].values
    ).astype('datetime64[ns]')

    pol_dates_all = np.sort(pol['date'].values).astype('datetime64[ns]')
    pol_major_dates = np.sort(
        pol[pol['severity'].str.lower() == 'major']['date'].values
    ).astype('datetime64[ns]')
    pol_election_dates = np.sort(
        pol[pol['event_type'].isin(['national_election', 'by_election'])]['date'].values
    ).astype('datetime64[ns]')

    print('[load] responsiveness baseline …')
    resp = fetch_response_time_responsiveness()
    print(f'  buckets: {len(resp):,}')

    # Build weeks: from WEEK_START_FROM until today - 30d (so 30-day target
    # is fully observed)
    today = date.today()
    last_week_start = today - timedelta(days=30)
    weeks = []
    d = WEEK_START_FROM
    while d <= last_week_start:
        weeks.append(d)
        d += timedelta(days=7)
    print(f'[build] {len(weeks)} weeks × {len(ps_universe)} PSes '
          f'= {len(weeks)*len(ps_universe):,} candidate rows')

    rows = []
    for _, ps in ps_universe.iterrows():
        ps_id = int(ps['police_station_id'])
        ps_name = ps['police_station']
        did = str(ps['district_id'])
        dn = ps['district_name']
        is_lah = bool(ps['is_lahore'])
        ps_d_all    = ps_dates_all.get(ps_id, np.array([], dtype='datetime64[ns]'))
        ps_d_strict = ps_dates_strict.get(ps_id, np.array([], dtype='datetime64[ns]'))
        d_d_all     = district_dates_all.get(did, np.array([], dtype='datetime64[ns]'))
        d_d_strict  = district_dates_strict.get(did, np.array([], dtype='datetime64[ns]'))
        for w in weeks:
            ws = np.datetime64(w, 'ns')
            # All look-back features use STRICTLY before week start (< ws).
            # Use searchsorted side='left' so points on the boundary aren't
            # counted (they belong to the "future" target window).
            row = {
                'police_station_id': ps_id,
                'police_station': ps_name,
                'district_id': did,
                'district_name': dn,
                'is_lahore': is_lah,
                'week_start_date': w,
            }
            for n in LOOKBACK_DAYS:
                lb = ws - np.timedelta64(n, 'D')
                row[f'prior_{n}d_ps_count'] = int(
                    np.searchsorted(ps_d_all, ws, side='left') -
                    np.searchsorted(ps_d_all, lb, side='left'))
                row[f'prior_{n}d_district_count'] = int(
                    np.searchsorted(d_d_all, ws, side='left') -
                    np.searchsorted(d_d_all, lb, side='left'))
            row['prior_30d_ps_strict']       = int(
                np.searchsorted(ps_d_strict, ws, side='left') -
                np.searchsorted(ps_d_strict,
                                ws - np.timedelta64(30, 'D'),
                                side='left'))
            row['prior_30d_district_strict'] = int(
                np.searchsorted(d_d_strict, ws, side='left') -
                np.searchsorted(d_d_strict,
                                ws - np.timedelta64(30, 'D'),
                                side='left'))
            # escalation ratio: 7d / (30d / 4)
            base = row['prior_30d_ps_count'] / 4.0
            row['escalation_ratio_7v30'] = (
                None if row['prior_30d_ps_count'] == 0
                else (np.searchsorted(ps_d_all, ws, side='left') -
                      np.searchsorted(ps_d_all,
                                       ws - np.timedelta64(7, 'D'),
                                       side='left')) / base
            )
            # Religious calendar
            for c in ['islamic', 'christian', 'hindu', 'sikh']:
                row[f'days_to_next_{c}_event']   = days_to_next(ws, rel_dates_by_comm[c])
                row[f'days_since_last_{c}_event'] = days_since_last(ws, rel_dates_by_comm[c])
            row['days_to_next_any_religious'] = days_to_next(ws, rel_dates_all)
            row['days_to_next_major_religious'] = days_to_next(ws, rel_major_dates)
            row['days_since_last_major_religious'] = days_since_last(ws, rel_major_dates)
            # Political calendar
            row['days_to_next_political'] = days_to_next(ws, pol_dates_all)
            row['days_since_last_political'] = days_since_last(ws, pol_dates_all)
            row['days_to_next_major_political'] = days_to_next(ws, pol_major_dates)
            row['in_election_period'] = False
            if len(pol_election_dates) > 0:
                diffs = np.abs((pol_election_dates - ws) / np.timedelta64(1, 'D'))
                row['in_election_period'] = bool((diffs <= 30).any())
            # Misinformation: any event in same district in last 14 days
            mis = misinfo[(misinfo['district'].astype(str).str.strip().str.lower() == dn.lower())
                          | (misinfo['district'].astype(str).str.strip().str.lower() == 'punjab')]
            row['misinfo_event_district_14d'] = False
            row['misinfo_event_district_30d'] = False
            if len(mis):
                m_dates = np.sort(mis['date'].values).astype('datetime64[ns]')
                row['misinfo_event_district_14d'] = bool(
                    ((m_dates >= ws - np.timedelta64(14, 'D')) & (m_dates < ws)).any())
                row['misinfo_event_district_30d'] = bool(
                    ((m_dates >= ws - np.timedelta64(30, 'D')) & (m_dates < ws)).any())
            # Responsiveness baseline (preceding month's bucket)
            m_y = w.year if w.month > 1 else w.year - 1
            m_m = w.month - 1 if w.month > 1 else 12
            r = resp.get((ps_id, m_y, m_m))
            row['avg_response_time_min_ps_1m'] = (
                None if (r is None or r['avg_rt'] is None)
                else r['avg_rt'] / 60.0)
            row['n_cases_ps_1m'] = r['n_cases'] if r else 0
            # Targets (forward windows)
            for h in HORIZONS:
                hi = ws + np.timedelta64(h, 'D')
                row[f'target_{h}d'] = int(
                    np.searchsorted(ps_d_strict, hi, side='right') -
                    np.searchsorted(ps_d_strict, ws, side='left') > 0
                )
            rows.append(row)

    df = pd.DataFrame(rows)
    print(f'[build] generated {len(df):,} rows')
    print(f'  target_7d  positive rate: {df["target_7d"].mean():.4f}  '
          f'(n_pos={int(df["target_7d"].sum())})')
    print(f'  target_30d positive rate: {df["target_30d"].mean():.4f}  '
          f'(n_pos={int(df["target_30d"].sum())})')

    df.to_csv(CSV_OUT, index=False)
    print(f'[OK] CSV: {CSV_OUT}')

    # Write to DB
    conn = get_db_postgres_predictive()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS minority_psweek_train")
    # Build DDL from dtypes
    type_map = {
        'int64': 'BIGINT', 'Int64': 'BIGINT',
        'float64': 'DOUBLE PRECISION', 'bool': 'BOOLEAN',
        'object': 'TEXT', 'datetime64[ns]': 'DATE',
    }
    cols_sql = []
    for c in df.columns:
        dt = str(df[c].dtype)
        pg = type_map.get(dt, 'TEXT')
        cols_sql.append(f'    "{c}" {pg}')
    cur.execute('CREATE TABLE minority_psweek_train (\n'
                 + ',\n'.join(cols_sql) + '\n)')
    cur.execute('CREATE INDEX idx_psw_ps   ON minority_psweek_train(police_station_id)')
    cur.execute('CREATE INDEX idx_psw_week ON minority_psweek_train(week_start_date)')
    cur.execute('CREATE INDEX idx_psw_tgt30 ON minority_psweek_train(target_30d)')
    conn.commit()

    cols = list(df.columns)
    placeholders = ', '.join(['%s'] * len(cols))
    quoted = ', '.join(f'"{c}"' for c in cols)
    INSERT = f'INSERT INTO minority_psweek_train ({quoted}) VALUES ({placeholders})'
    out_rows = []
    for _, r in df.iterrows():
        row = []
        for c in cols:
            v = r[c]
            if isinstance(v, float) and pd.isna(v): v = None
            elif v is pd.NaT: v = None
            row.append(v)
        out_rows.append(tuple(row))
    cur.executemany(INSERT, out_rows)
    conn.commit()
    cur.close(); conn.close()
    print('[OK] wrote db.minority_psweek_train')


if __name__ == '__main__':
    main()
