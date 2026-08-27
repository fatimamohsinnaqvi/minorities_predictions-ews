#!/usr/bin/env python3
"""
Compute police-responsiveness features for each case in minority_incidents.

For each case, look at the police station's responsiveness in the 3 months
PRIOR to the case (no leakage from the case's own month or later). Source
metrics come from test_1124.response_time:

  - response_time (int seconds; treated as the time from accept to first
    arrival)
  - caller_feedback (text; 'Positive' / 'Negative' / NULL)

Strategy:
  1. SQL aggregate response_time → per-(PS, year-month) bucket with
     mean / median / n_cases / positive count.
  2. For each minority_incidents case, look up the three buckets covering
     the months strictly before its incident_date, pool them by
     n_cases-weighted mean.
  3. Compute a within-month decile rank across all PSes.

Output:
  db_predictive_policing.minority_features_responsiveness
  data/processed/features_responsiveness.csv
"""
import os
import sys
from datetime import datetime, date, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_1124, get_db_postgres_predictive  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, 'schema_responsiveness.sql')
PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
CSV_OUT = os.path.join(PROJECT, 'data', 'processed',
                        'features_responsiveness.csv')

# Window: 3 calendar months prior to case month
PRIOR_MONTHS = 3


def month_index(d):
    """Map a date to a contiguous month index (year*12 + month)."""
    return d.year * 12 + d.month


def main():
    # ---- Pull per-(PS, year-month) aggregates from response_time
    print('[src] aggregating response_time by (PS, year-month) ...')
    src = get_db_postgres_1124()
    src_cur = src.cursor()
    src_cur.execute("""
        SELECT police_station_id,
               substring(date FROM 1 FOR 7) AS ym,    -- 'YYYY-MM'
               AVG(NULLIF(response_time, 0)::float)         AS avg_rt_sec,
               percentile_disc(0.5) WITHIN GROUP (ORDER BY response_time) AS median_rt_sec,
               COUNT(*)                                      AS n_cases,
               SUM(CASE WHEN caller_feedback = 'Positive' THEN 1 ELSE 0 END) AS pos_count
        FROM response_time
        WHERE police_station_id IS NOT NULL
          AND date IS NOT NULL
          AND date ~ '^[0-9]{4}-[0-9]{2}'
        GROUP BY police_station_id, ym
    """)
    agg = src_cur.fetchall()
    src_cur.close(); src.close()
    print(f'[src] {len(agg):,} (PS, year-month) buckets')

    # Index by (ps_id, year, month)
    by_key = {}
    by_ps = defaultdict(list)
    for ps_id, ym, avg_rt, med_rt, n, pos in agg:
        try:
            y, m = int(ym[:4]), int(ym[5:7])
        except Exception:
            continue
        key = (int(ps_id), y, m)
        by_key[key] = {
            'avg_rt': float(avg_rt) if avg_rt is not None else None,
            'median_rt': float(med_rt) if med_rt is not None else None,
            'n_cases': int(n),
            'pos_count': int(pos or 0),
        }
        by_ps[int(ps_id)].append((y, m))

    # ---- Load minority_incidents
    pre = get_db_postgres_predictive()
    df = pd.read_sql("""
        SELECT id, police_station_id, incident_date
        FROM minority_incidents
    """, pre)
    df['incident_date'] = pd.to_datetime(df['incident_date'], errors='coerce')
    print(f'[load] cases: {len(df):,}  (missing date: {df["incident_date"].isna().sum()})')

    # ---- Per-case responsiveness lookup
    feats = []
    for _, r in df.iterrows():
        cid = int(r['id'])
        ps = r['police_station_id']
        dt = r['incident_date']

        if ps is None or pd.isna(dt):
            feats.append({
                'case_id': cid,
                'avg_response_time_min_ps_90d': None,
                'median_response_time_min_ps_90d': None,
                'n_cases_ps_90d': 0,
                'positive_feedback_rate_ps_90d': None,
                'responsiveness_decile_ps': None,
                'has_responsiveness_data': False,
                '_case_month_index': None,
            })
            continue

        ps_i = int(ps)
        # Prior 3 months (the 3 months strictly before incident_date's month)
        case_mi = month_index(dt)
        prior_keys = [(ps_i, *_y_m_from_index(case_mi - k))
                       for k in range(1, PRIOR_MONTHS + 1)]
        prior_buckets = [by_key.get(k) for k in prior_keys]
        prior_buckets = [b for b in prior_buckets if b is not None]

        if not prior_buckets:
            feats.append({
                'case_id': cid,
                'avg_response_time_min_ps_90d': None,
                'median_response_time_min_ps_90d': None,
                'n_cases_ps_90d': 0,
                'positive_feedback_rate_ps_90d': None,
                'responsiveness_decile_ps': None,
                'has_responsiveness_data': False,
                '_case_month_index': case_mi,
            })
            continue

        # n-weighted mean of avg_rt
        n_total = sum(b['n_cases'] for b in prior_buckets)
        if n_total == 0:
            avg_rt_min = None
            median_rt_min = None
            pos_rate = None
        else:
            avg_rt_min = sum(
                (b['avg_rt'] or 0) * b['n_cases'] for b in prior_buckets
            ) / n_total / 60.0
            # Median: simple unweighted mean of the 3 monthly medians
            mds = [b['median_rt'] for b in prior_buckets if b['median_rt'] is not None]
            median_rt_min = (sum(mds) / len(mds) / 60.0) if mds else None
            pos_rate = sum(b['pos_count'] for b in prior_buckets) / n_total

        feats.append({
            'case_id': cid,
            'avg_response_time_min_ps_90d': avg_rt_min,
            'median_response_time_min_ps_90d': median_rt_min,
            'n_cases_ps_90d': n_total,
            'positive_feedback_rate_ps_90d': pos_rate,
            'responsiveness_decile_ps': None,  # filled after within-month rank
            'has_responsiveness_data': avg_rt_min is not None,
            '_case_month_index': case_mi,
        })

    feats_df = pd.DataFrame(feats)

    # ---- Per-case-month decile rank of avg_response_time
    # 1 = fastest, 10 = slowest
    print('[compute] within-month decile ranks ...')
    for mi, grp in feats_df.groupby('_case_month_index'):
        if mi is None or mi != mi:
            continue
        s = grp['avg_response_time_min_ps_90d']
        valid = s.dropna()
        if len(valid) < 2:
            continue
        ranks = valid.rank(method='average')
        deciles = np.ceil(ranks / len(valid) * 10).astype(int).clip(1, 10)
        feats_df.loc[deciles.index, 'responsiveness_decile_ps'] = deciles

    feats_df = feats_df.drop(columns=['_case_month_index'])

    # ---- Write CSV
    os.makedirs(os.path.dirname(CSV_OUT), exist_ok=True)
    feats_df.to_csv(CSV_OUT, index=False)
    print(f'\n[OK] CSV: {CSV_OUT}  ({len(feats_df):,} rows)')

    # ---- Write DB
    cur = pre.cursor()
    with open(SCHEMA_PATH) as f:
        cur.execute(f.read())
    pre.commit()
    print('[ddl] minority_features_responsiveness recreated')

    INSERT = """INSERT INTO minority_features_responsiveness (
        case_id,
        avg_response_time_min_ps_90d, median_response_time_min_ps_90d,
        n_cases_ps_90d, positive_feedback_rate_ps_90d,
        responsiveness_decile_ps, has_responsiveness_data, generated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""

    def _f(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)

    def _i(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return int(v)

    now = datetime.utcnow()
    for _, r in feats_df.iterrows():
        cur.execute(INSERT, (
            int(r['case_id']),
            _f(r['avg_response_time_min_ps_90d']),
            _f(r['median_response_time_min_ps_90d']),
            _i(r['n_cases_ps_90d']),
            _f(r['positive_feedback_rate_ps_90d']),
            _i(r['responsiveness_decile_ps']),
            bool(r['has_responsiveness_data']),
            now,
        ))
    pre.commit()

    # ---- Summary
    print('\n=== Summary (Punjab-wide) ===')
    print(f'Cases with responsiveness data: {feats_df["has_responsiveness_data"].sum():,} / {len(feats_df):,}')
    for col in ['avg_response_time_min_ps_90d',
                 'median_response_time_min_ps_90d',
                 'n_cases_ps_90d',
                 'positive_feedback_rate_ps_90d']:
        s = feats_df[col].dropna()
        if len(s):
            print(f'  {col:<40} mean={s.mean():.2f}  median={s.median():.2f}  '
                  f'min={s.min():.2f}  max={s.max():.2f}')

    cur.close(); pre.close()
    print('\n[done]')


def _y_m_from_index(mi):
    """Reverse of month_index."""
    return divmod(mi - 1, 12)[0] + 0, divmod(mi - 1, 12)[1] + 1


if __name__ == '__main__':
    main()
