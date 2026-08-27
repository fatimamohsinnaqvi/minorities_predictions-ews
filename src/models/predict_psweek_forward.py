#!/usr/bin/env python3
"""
Forward (real early-warning) predictions for every police station.

Computes a feature vector for each PS as of TODAY and scores it through
the trained LR forecaster. The output is the actual "next 30 days"
risk score per PS — the proper early-warning artifact.

Writes:
  db_predictive_policing.minority_psweek_forward
  data/processed/psweek_forward.csv
"""
import os
import sys
from datetime import date, datetime, timedelta

import joblib
import numpy as np
import pandas as pd

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
# Reuse the feature-extraction helpers
from psweek_dataset import (  # noqa
    fetch_minority_incidents, fetch_response_time_responsiveness,
    load_calendar, days_to_next, days_since_last,
)

PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
MODEL_PATH = os.path.join(PROJECT, 'outputs', 'models', 'psweek_lr.pkl')
CSV_OUT = os.path.join(PROJECT, 'data', 'processed', 'psweek_forward.csv')
LOOKBACK_DAYS = [30, 60, 90]


SCHEMA = """
DROP TABLE IF EXISTS minority_psweek_forward;
CREATE TABLE minority_psweek_forward (
    police_station_id   INTEGER PRIMARY KEY,
    police_station      TEXT,
    district_name       TEXT,
    is_lahore           BOOLEAN,
    ref_date            DATE,
    horizon_days        INTEGER,
    risk_score          DOUBLE PRECISION,
    rank_in_punjab      INTEGER,
    rank_in_lahore      INTEGER,
    prior_30d_ps_count        INTEGER,
    prior_30d_district_count  INTEGER,
    days_to_next_major_religious  INTEGER,
    days_to_next_political        INTEGER,
    misinfo_event_district_14d    BOOLEAN,
    generated_at        TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_pswf_score  ON minority_psweek_forward(risk_score);
CREATE INDEX idx_pswf_lahore ON minority_psweek_forward(is_lahore);
"""


def main():
    print('[load] model ...')
    pkg = joblib.load(MODEL_PATH)
    pipe = pkg['pipeline']
    feat_names = pkg['feature_names']
    print(f'  features: {len(feat_names)}')

    # Pull everything needed
    print('[load] minority_incidents + calendars + responsiveness ...')
    inc = fetch_minority_incidents()
    rel = load_calendar(os.path.join(PROJECT, 'data', 'external',
                                       'religious_calendar.csv'))
    pol = load_calendar(os.path.join(PROJECT, 'data', 'external',
                                       'political_calendar.csv'))
    misinfo = load_calendar(os.path.join(PROJECT, 'data', 'external',
                                          'misinformation_events.csv'))
    rel['community'] = rel['community'].str.lower()
    resp = fetch_response_time_responsiveness()

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

    # Per-PS sorted date arrays
    ps_dates_all = {}
    ps_dates_strict = {}
    district_dates_all = {}
    district_dates_strict = {}
    for ps_id, grp in inc.dropna(subset=['police_station_id']).groupby('police_station_id'):
        ps_dates_all[int(ps_id)] = np.sort(grp['incident_date'].values).astype('datetime64[ns]')
        ps_dates_strict[int(ps_id)] = np.sort(
            grp[grp['is_minority_targeted']]['incident_date'].values
        ).astype('datetime64[ns]')
    for did, grp in inc.groupby('district_id'):
        district_dates_all[str(did)] = np.sort(grp['incident_date'].values).astype('datetime64[ns]')
        district_dates_strict[str(did)] = np.sort(
            grp[grp['is_minority_targeted']]['incident_date'].values
        ).astype('datetime64[ns]')

    # PS universe
    ps_universe = inc.dropna(subset=['police_station_id']).groupby(
        'police_station_id').first().reset_index()[
        ['police_station_id', 'police_station', 'district_id',
         'district_name', 'is_lahore']]
    print(f'  PS universe: {len(ps_universe):,}')

    # Reference date: start of NEXT Monday's week so we score the upcoming
    # 30 days. If today is Monday, ref = today.
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    ref_date = today + timedelta(days=days_ahead)
    ws = np.datetime64(ref_date, 'ns')
    print(f'[predict] ref_date (next Monday): {ref_date}  horizon: 30 days')

    rows = []
    for _, ps in ps_universe.iterrows():
        ps_id = int(ps['police_station_id'])
        did = str(ps['district_id'])
        dn = ps['district_name'] or ''
        ps_d_all    = ps_dates_all.get(ps_id, np.array([], dtype='datetime64[ns]'))
        ps_d_strict = ps_dates_strict.get(ps_id, np.array([], dtype='datetime64[ns]'))
        d_d_all     = district_dates_all.get(did, np.array([], dtype='datetime64[ns]'))
        d_d_strict  = district_dates_strict.get(did, np.array([], dtype='datetime64[ns]'))
        row = {
            'police_station_id': ps_id,
            'police_station': ps['police_station'],
            'district_id': did,
            'district_name': dn,
            'is_lahore': bool(ps['is_lahore']),
            'week_start_date': ref_date,
        }
        for n in LOOKBACK_DAYS:
            lb = ws - np.timedelta64(n, 'D')
            row[f'prior_{n}d_ps_count'] = int(
                np.searchsorted(ps_d_all, ws, side='left') -
                np.searchsorted(ps_d_all, lb, side='left'))
            row[f'prior_{n}d_district_count'] = int(
                np.searchsorted(d_d_all, ws, side='left') -
                np.searchsorted(d_d_all, lb, side='left'))
        row['prior_30d_ps_strict'] = int(
            np.searchsorted(ps_d_strict, ws, side='left') -
            np.searchsorted(ps_d_strict, ws - np.timedelta64(30, 'D'), side='left'))
        row['prior_30d_district_strict'] = int(
            np.searchsorted(d_d_strict, ws, side='left') -
            np.searchsorted(d_d_strict, ws - np.timedelta64(30, 'D'), side='left'))
        base = row['prior_30d_ps_count'] / 4.0
        if row['prior_30d_ps_count'] == 0:
            row['escalation_ratio_7v30'] = None
        else:
            row['escalation_ratio_7v30'] = (
                np.searchsorted(ps_d_all, ws, side='left') -
                np.searchsorted(ps_d_all, ws - np.timedelta64(7, 'D'), side='left')
            ) / base
        for c in ['islamic', 'christian', 'hindu', 'sikh']:
            row[f'days_to_next_{c}_event']   = days_to_next(ws, rel_dates_by_comm[c])
            row[f'days_since_last_{c}_event'] = days_since_last(ws, rel_dates_by_comm[c])
        row['days_to_next_any_religious']    = days_to_next(ws, rel_dates_all)
        row['days_to_next_major_religious']  = days_to_next(ws, rel_major_dates)
        row['days_since_last_major_religious'] = days_since_last(ws, rel_major_dates)
        row['days_to_next_political']        = days_to_next(ws, pol_dates_all)
        row['days_since_last_political']     = days_since_last(ws, pol_dates_all)
        row['days_to_next_major_political']  = days_to_next(ws, pol_major_dates)
        row['in_election_period'] = bool(
            len(pol_election_dates) > 0 and
            (np.abs((pol_election_dates - ws) / np.timedelta64(1, 'D')) <= 30).any())
        mis = misinfo[(misinfo['district'].astype(str).str.strip().str.lower() == dn.lower())
                      | (misinfo['district'].astype(str).str.strip().str.lower() == 'punjab')]
        m_dates = (np.sort(mis['date'].values).astype('datetime64[ns]')
                   if len(mis) else np.array([], dtype='datetime64[ns]'))
        row['misinfo_event_district_14d'] = bool(
            ((m_dates >= ws - np.timedelta64(14, 'D')) & (m_dates < ws)).any())
        row['misinfo_event_district_30d'] = bool(
            ((m_dates >= ws - np.timedelta64(30, 'D')) & (m_dates < ws)).any())
        m_y = ref_date.year if ref_date.month > 1 else ref_date.year - 1
        m_m = ref_date.month - 1 if ref_date.month > 1 else 12
        r = resp.get((ps_id, m_y, m_m))
        row['avg_response_time_min_ps_1m'] = (
            None if (r is None or r['avg_rt'] is None)
            else r['avg_rt'] / 60.0)
        row['n_cases_ps_1m'] = r['n_cases'] if r else 0
        rows.append(row)

    df = pd.DataFrame(rows)
    print(f'[predict] feature rows: {len(df)}')

    # Prep for model — same as training (drop non-features, numeric, impute)
    NON_FEATURE = {
        'police_station_id', 'police_station', 'district_id',
        'district_name', 'week_start_date',
    }
    use = df.drop(columns=[c for c in NON_FEATURE if c in df.columns])
    for c in list(use.columns):
        if use[c].dtype == bool:
            use[c] = use[c].astype(int)
    use = use.apply(pd.to_numeric, errors='coerce')
    for c in use.columns:
        if use[c].isna().any():
            med = use[c].median()
            if pd.isna(med): med = 0
            use[c] = use[c].fillna(med)
    # Align column order to training
    use = use.reindex(columns=feat_names, fill_value=0.0)
    X = use.values.astype(float)
    scores = pipe.predict_proba(X)[:, 1]
    df['risk_score'] = scores

    # Ranks
    df['rank_in_punjab'] = df['risk_score'].rank(ascending=False, method='min').astype(int)
    lah_mask = df['is_lahore']
    df['rank_in_lahore'] = np.where(
        lah_mask,
        df['risk_score'].where(lah_mask).rank(ascending=False, method='min'),
        np.nan,
    )
    df['rank_in_lahore'] = df['rank_in_lahore'].astype('Int64')

    df = df.sort_values('risk_score', ascending=False)

    df.to_csv(CSV_OUT, index=False)
    print(f'[OK] CSV: {CSV_OUT}')

    # Write to DB
    conn = get_db_postgres_predictive()
    cur = conn.cursor()
    cur.execute(SCHEMA)
    conn.commit()
    INSERT = """INSERT INTO minority_psweek_forward (
        police_station_id, police_station, district_name, is_lahore,
        ref_date, horizon_days, risk_score,
        rank_in_punjab, rank_in_lahore,
        prior_30d_ps_count, prior_30d_district_count,
        days_to_next_major_religious, days_to_next_political,
        misinfo_event_district_14d, generated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    now = datetime.utcnow()
    for _, r in df.iterrows():
        cur.execute(INSERT, (
            int(r['police_station_id']),
            r['police_station'],
            r['district_name'],
            bool(r['is_lahore']),
            ref_date,
            30,
            float(r['risk_score']),
            int(r['rank_in_punjab']),
            int(r['rank_in_lahore']) if pd.notna(r['rank_in_lahore']) else None,
            int(r['prior_30d_ps_count']),
            int(r['prior_30d_district_count']),
            int(r['days_to_next_major_religious']) if pd.notna(r['days_to_next_major_religious']) else None,
            int(r['days_to_next_political']) if pd.notna(r['days_to_next_political']) else None,
            bool(r['misinfo_event_district_14d']),
            now,
        ))
    conn.commit()
    cur.close(); conn.close()
    print(f'[OK] wrote db.minority_psweek_forward ({len(df)} rows)')

    print('\n=== Top 15 PSes for next 30 days (Punjab) ===')
    for _, r in df.head(15).iterrows():
        print(f'  #{int(r["rank_in_punjab"]):>3} {r["police_station"]:<28} '
              f'({r["district_name"]:<14})  score={r["risk_score"]:.3f}  '
              f'prior30={r["prior_30d_ps_count"]:>2}')

    print('\n=== Top 15 PSes for next 30 days (Lahore) ===')
    lah = df[df['is_lahore']].head(15)
    for _, r in lah.iterrows():
        print(f'  #{int(r["rank_in_lahore"]):>3} {r["police_station"]:<28}  '
              f'score={r["risk_score"]:.3f}  prior30={r["prior_30d_ps_count"]:>2}')


if __name__ == '__main__':
    main()
