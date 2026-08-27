#!/usr/bin/env python3
"""
Compute the "prior incident density" feature family for each row in
minority_incidents.

Reads:  db_predictive_policing.minority_incidents
Writes: db_predictive_policing.minority_features_prior_density
        data/processed/features_prior_density.csv

For each case we compute rolling counts of *prior* cases (strictly before
the case's `accepted_time`) at three scopes:
  - same police station, windows 7/30/60/90 days
  - same district, windows 7/30/60/90 days
  - strict-label (is_minority_targeted=TRUE) variants for 30d
Plus a short-term spike detector `escalation_ratio_7v30`.

Strictness:
  An "earlier" case is one whose `accepted_time` is strictly less than the
  current case's `accepted_time`. Ties on the same `accepted_time` are
  broken by `id` — earlier ids count, later ids do not.
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
SCHEMA_PATH = os.path.join(HERE, 'schema_prior_density.sql')
PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
CSV_OUT = os.path.join(PROJECT, 'data', 'processed', 'features_prior_density.csv')


WINDOWS = [7, 30, 60, 90]


def _ordering_key(df):
    """Return a 1-D int64 'ordering key' (nanoseconds + tiebreak on id).
    Strictly comparable: a < b iff (accepted_time, id) lexicographically less.
    """
    # 32-bit headroom for id offset; ids in minority_incidents are < 1e7.
    ns = df['ts_use'].astype('datetime64[ns]').view('int64')
    return ns.astype('int64') + (df['id'].astype('int64') % 1_000_000_000)


def prior_count(df, group_col, window_days, filter_col=None):
    """For each row, count rows with same group_col and ordering_key strictly
    smaller, but with `ts_use` >= (this.ts_use - window_days).
    If filter_col is given (column of bool), only count rows where True."""
    df = df.reset_index(drop=True)
    out = np.zeros(len(df), dtype=np.int64)
    for _, grp in df.groupby(group_col, dropna=True):
        if grp.empty:
            continue
        # candidates = rows in this group that could be counted (filtered)
        if filter_col is not None:
            cand = grp[grp[filter_col]]
        else:
            cand = grp
        if cand.empty:
            continue
        cand_ts = cand['ts_use'].values.astype('datetime64[ns]')
        cand_ord = cand['_ord'].values
        # Sort candidates by ordering key
        sort_idx = np.argsort(cand_ord)
        cand_ts = cand_ts[sort_idx]
        cand_ord = cand_ord[sort_idx]
        for _, row in grp.iterrows():
            t = np.datetime64(row['ts_use'], 'ns')
            cutoff = t - np.timedelta64(window_days, 'D')
            # Strictly < this.ord
            hi = np.searchsorted(cand_ord, row['_ord'], side='left')
            # And ts >= cutoff
            lo = np.searchsorted(cand_ts[:hi], cutoff, side='left')
            out[row['_row']] = hi - lo
    return out


def main():
    conn = get_db_postgres_predictive()

    print('[load] minority_incidents ...')
    df = pd.read_sql("""
        SELECT id, district_id, police_station_id,
               incident_date, accepted_time, is_minority_targeted
        FROM minority_incidents
    """, conn)
    print(f'[load] rows: {len(df):,}')

    # Use accepted_time when present; fall back to incident_date (midnight)
    df['accepted_time'] = pd.to_datetime(df['accepted_time'], errors='coerce')
    df['incident_date'] = pd.to_datetime(df['incident_date'], errors='coerce')
    df['ts_use'] = df['accepted_time'].fillna(df['incident_date'])
    # If even that's NaT, push to a far-past so they don't contribute as
    # "prior" to anything sensibly. (Rare — flag in the count.)
    n_missing_ts = int(df['ts_use'].isna().sum())
    df['ts_use'] = df['ts_use'].fillna(pd.Timestamp('1970-01-01'))
    print(f'[prep] rows with no usable timestamp: {n_missing_ts}')

    df['_row'] = np.arange(len(df))
    df['_ord'] = _ordering_key(df)

    feats = pd.DataFrame({'case_id': df['id'].values})

    # ------- per-PS counts (all windows)
    for w in WINDOWS:
        print(f'[compute] per-PS prior {w}d ...')
        feats[f'prior_{w}d_ps_count'] = prior_count(df, 'police_station_id', w)

    # ------- per-district counts (all windows)
    for w in WINDOWS:
        print(f'[compute] per-district prior {w}d ...')
        feats[f'prior_{w}d_district_count'] = prior_count(df, 'district_id', w)

    # ------- strict-label variants (30d only)
    print('[compute] strict-label prior 30d (PS + district) ...')
    feats['prior_30d_ps_minority_targeted'] = prior_count(
        df, 'police_station_id', 30, filter_col='is_minority_targeted')
    feats['prior_30d_district_minority_targeted'] = prior_count(
        df, 'district_id', 30, filter_col='is_minority_targeted')

    # ------- escalation ratio
    # escalation_ratio_7v30 = prior_7d / (prior_30d / 4)
    # NULL when prior_30d_ps_count == 0 (no base rate)
    print('[compute] escalation_ratio_7v30 ...')
    base = feats['prior_30d_ps_count'] / 4.0
    feats['escalation_ratio_7v30'] = np.where(
        feats['prior_30d_ps_count'] > 0,
        feats['prior_7d_ps_count'] / base,
        np.nan,
    )

    # ------- write CSV
    os.makedirs(os.path.dirname(CSV_OUT), exist_ok=True)
    feats.to_csv(CSV_OUT, index=False)
    print(f'\n[OK] CSV: {CSV_OUT}  ({len(feats):,} rows)')

    # ------- write DB
    cur = conn.cursor()
    with open(SCHEMA_PATH) as f:
        cur.execute(f.read())
    conn.commit()
    print('[ddl] minority_features_prior_density recreated')

    INSERT = """INSERT INTO minority_features_prior_density (
        case_id,
        prior_7d_ps_count, prior_30d_ps_count, prior_60d_ps_count, prior_90d_ps_count,
        prior_7d_district_count, prior_30d_district_count,
        prior_60d_district_count, prior_90d_district_count,
        prior_30d_ps_minority_targeted, prior_30d_district_minority_targeted,
        escalation_ratio_7v30, generated_at
    ) VALUES (
        %s,
        %s, %s, %s, %s,
        %s, %s,
        %s, %s,
        %s, %s,
        %s, %s
    )"""

    now = datetime.utcnow()
    for _, r in feats.iterrows():
        cur.execute(INSERT, (
            int(r['case_id']),
            int(r['prior_7d_ps_count']), int(r['prior_30d_ps_count']),
            int(r['prior_60d_ps_count']), int(r['prior_90d_ps_count']),
            int(r['prior_7d_district_count']), int(r['prior_30d_district_count']),
            int(r['prior_60d_district_count']), int(r['prior_90d_district_count']),
            int(r['prior_30d_ps_minority_targeted']),
            int(r['prior_30d_district_minority_targeted']),
            None if pd.isna(r['escalation_ratio_7v30']) else float(r['escalation_ratio_7v30']),
            now,
        ))
    conn.commit()

    # ------- summary
    print('\n=== Summary (Punjab-wide) ===')
    print(f'{"feature":<40} {"mean":>8} {"median":>8} {"max":>8}')
    for c in feats.columns:
        if c == 'case_id': continue
        s = feats[c].dropna() if c == 'escalation_ratio_7v30' else feats[c]
        if len(s) == 0:
            print(f'  {c:<40} (all NULL)')
            continue
        print(f'  {c:<40} {s.mean():>8.2f} {s.median():>8.0f} {s.max():>8.0f}')

    # Top 5 PSes by prior_30d_ps_count (illustrative)
    print('\n=== Top 5 PSes by max prior_30d_ps_count ===')
    df['prior_30d_ps_count'] = feats['prior_30d_ps_count'].values
    df_with_ps = pd.read_sql("""
        SELECT id, police_station, district_name FROM minority_incidents
    """, conn).set_index('id')
    j = df.set_index('id').join(df_with_ps)
    top = j.groupby(['district_name', 'police_station'])['prior_30d_ps_count']\
           .max().sort_values(ascending=False).head(5)
    for (dn, ps), v in top.items():
        print(f'  {int(v):>4}  PS={ps} ({dn})')

    cur.close(); conn.close()
    print('\n[done]')


if __name__ == '__main__':
    main()
