#!/usr/bin/env python3
"""
EDA on `minority_incidents`. Produces summary CSVs and PNG figures.

Outputs:
  data/processed/district_severity.csv
  data/processed/eda_summary.json
  outputs/figures/eda/*.png
"""
import json
import os
import sys
from collections import Counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
PROCESSED = os.path.join(PROJECT, 'data', 'processed')
FIG_DIR = os.path.join(PROJECT, 'outputs', 'figures', 'eda')

os.makedirs(PROCESSED, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

plt.rcParams.update({
    'figure.dpi': 110,
    'savefig.dpi': 140,
    'savefig.bbox': 'tight',
    'font.family': 'DejaVu Sans',
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.titleweight': 'bold',
})


def main():
    conn = get_db_postgres_predictive()
    df = pd.read_sql("""SELECT id, case_number, incident_date, incident_year,
                               incident_month, district_id, district_name,
                               police_station_id, police_station, lat, long,
                               is_lahore, level1_case_nature, level2_case_nature,
                               level3_case_nature, description, match_source,
                               minority_community, is_minority_targeted
                        FROM minority_incidents""", conn)
    conn.close()
    print(f'[eda] loaded {len(df):,} rows from minority_incidents')
    df['incident_date'] = pd.to_datetime(df['incident_date'], errors='coerce')

    summary = {
        'total_rows': int(len(df)),
        'rows_lahore': int(df['is_lahore'].sum()),
        'rows_minority_targeted_strict': int(df['is_minority_targeted'].sum()),
        'rows_with_coords': int(df[['lat', 'long']].dropna().shape[0]),
    }

    # -------- Figure 1: cases per month (stacked: Lahore vs rest of Punjab)
    df_dated = df.dropna(subset=['incident_date']).copy()
    df_dated['ym'] = df_dated['incident_date'].dt.to_period('M').astype(str)
    months = sorted(df_dated['ym'].unique().tolist())
    lahore_mask = df_dated['is_lahore'].fillna(False).astype(bool)
    lahore_counts = df_dated[lahore_mask].groupby('ym').size().reindex(months, fill_value=0)
    rest_counts   = df_dated[~lahore_mask].groupby('ym').size().reindex(months, fill_value=0)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    x = range(len(months))
    ax.bar(x, lahore_counts.values, width=0.9, color='#c0392b', label='Lahore')
    ax.bar(x, rest_counts.values, width=0.9, bottom=lahore_counts.values,
           color='#7f8c8d', label='Rest of Punjab')
    ax.set_xticks(list(x)); ax.set_xticklabels(months, rotation=45, ha='right')
    ax.set_title('Cases per month (minority_incidents) — Lahore vs rest of Punjab')
    ax.set_xlabel('Month'); ax.set_ylabel('Cases')
    ax.legend(loc='upper left', frameon=False)
    out = os.path.join(FIG_DIR, '01_cases_per_month.png')
    fig.savefig(out); plt.close(fig)
    print(f'  → {out}')
    totals = (lahore_counts.fillna(0) + rest_counts.fillna(0)).astype(int)
    if len(totals):
        summary['monthly_total_peak'] = int(totals.max())
        summary['monthly_total_peak_month'] = str(totals.idxmax())

    # -------- Figure 2: top districts
    by_dist = df['district_name'].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(9, 5.6))
    by_dist.iloc[::-1].plot(kind='barh', ax=ax, color='#34495e')
    ax.set_title('Top 15 districts by minority-incident count')
    ax.set_xlabel('Cases')
    for i, v in enumerate(by_dist.iloc[::-1].values):
        ax.text(v + max(by_dist) * 0.005, i, str(v), va='center', fontsize=9)
    out = os.path.join(FIG_DIR, '02_top_districts.png')
    fig.savefig(out); plt.close(fig)
    print(f'  → {out}')
    summary['top_districts'] = by_dist.head(5).to_dict()

    # -------- Figure 3: level3 case-nature mix (top 12)
    by_l3 = df['level3_case_nature'].value_counts().head(12)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    by_l3.iloc[::-1].plot(kind='barh', ax=ax, color='#16a085')
    ax.set_title('Top 12 level-3 case categories in minority_incidents')
    ax.set_xlabel('Cases')
    for i, v in enumerate(by_l3.iloc[::-1].values):
        ax.text(v + max(by_l3) * 0.005, i, str(v), va='center', fontsize=9)
    out = os.path.join(FIG_DIR, '03_top_level3_categories.png')
    fig.savefig(out); plt.close(fig)
    print(f'  → {out}')
    summary['top_level3'] = by_l3.head(8).to_dict()

    # -------- Figure 4: community pie
    community = df['minority_community'].value_counts()
    fig, ax = plt.subplots(figsize=(6, 6))
    colors = {'christian': '#3498db', 'ahmadi': '#e67e22', 'hindu': '#9b59b6',
              'sikh': '#16a085', 'multiple': '#f1c40f', 'unspecified': '#bdc3c7'}
    cs = [colors.get(c, '#7f8c8d') for c in community.index]
    ax.pie(community.values, labels=community.index, autopct='%1.1f%%',
           colors=cs, startangle=90, textprops={'fontsize': 10})
    ax.set_title('Inferred minority community')
    out = os.path.join(FIG_DIR, '04_minority_community_pie.png')
    fig.savefig(out); plt.close(fig)
    print(f'  → {out}')
    summary['by_community'] = community.to_dict()

    # -------- Figure 5: Lahore — top police stations
    lahore_df = df[df['is_lahore']].copy()
    by_ps = lahore_df['police_station'].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(9, 5.6))
    by_ps.iloc[::-1].plot(kind='barh', ax=ax, color='#c0392b')
    ax.set_title('Lahore — top 15 police stations by minority-incident count')
    ax.set_xlabel('Cases')
    for i, v in enumerate(by_ps.iloc[::-1].values):
        ax.text(v + max(by_ps) * 0.005, i, str(v), va='center', fontsize=9)
    out = os.path.join(FIG_DIR, '05_lahore_top_ps.png')
    fig.savefig(out); plt.close(fig)
    print(f'  → {out}')
    summary['lahore_top_ps'] = by_ps.head(5).to_dict()

    # -------- Figure 6: day-of-week pattern (Lahore)
    if not lahore_df.empty:
        lahore_df['dow'] = pd.to_datetime(lahore_df['incident_date']).dt.day_name()
        dow_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        by_dow = lahore_df['dow'].value_counts().reindex(dow_order, fill_value=0)
        fig, ax = plt.subplots(figsize=(8, 4))
        by_dow.plot(kind='bar', ax=ax, color='#2980b9')
        ax.set_title('Lahore — minority incidents by day of week')
        ax.set_xlabel(''); ax.set_ylabel('Cases')
        plt.xticks(rotation=30, ha='right')
        out = os.path.join(FIG_DIR, '06_lahore_day_of_week.png')
        fig.savefig(out); plt.close(fig)
        print(f'  → {out}')
        summary['lahore_by_dow'] = by_dow.to_dict()

    # -------- Figure 7: strict-label trend (is_minority_targeted)
    targeted = df[df['is_minority_targeted']].dropna(subset=['incident_date']).copy()
    if not targeted.empty:
        targeted['ym'] = targeted['incident_date'].dt.to_period('M').astype(str)
        ts = targeted.groupby('ym').size()
        fig, ax = plt.subplots(figsize=(11, 4))
        ts.plot(kind='line', ax=ax, marker='o', color='#c0392b', linewidth=2)
        ax.set_title('Strict-label minority-targeted cases per month (Punjab)')
        ax.set_xlabel('Month'); ax.set_ylabel('Cases')
        ax.fill_between(range(len(ts)), 0, ts.values, color='#c0392b', alpha=0.12)
        plt.xticks(rotation=45, ha='right')
        out = os.path.join(FIG_DIR, '07_strict_label_trend.png')
        fig.savefig(out); plt.close(fig)
        print(f'  → {out}')
        summary['strict_label_peak_month'] = str(ts.idxmax())
        summary['strict_label_peak_value'] = int(ts.max())

    # -------- Figure 8: match_source mix
    by_src = df['match_source'].value_counts()
    fig, ax = plt.subplots(figsize=(6, 4.5))
    by_src.plot(kind='bar', ax=ax,
                 color=['#27ae60', '#e67e22', '#8e44ad'])
    ax.set_title('How each row qualified (match_source)')
    ax.set_xlabel(''); ax.set_ylabel('Cases')
    plt.xticks(rotation=0)
    for i, v in enumerate(by_src.values):
        ax.text(i, v + max(by_src) * 0.01, str(v), ha='center', fontsize=10)
    out = os.path.join(FIG_DIR, '08_match_source.png')
    fig.savefig(out); plt.close(fig)
    print(f'  → {out}')
    summary['by_match_source'] = by_src.to_dict()

    # -------- District-severity CSV (per Data Dictionary report bands)
    def severity_band(n):
        if n <= 50:   return 'Low'
        if n <= 150:  return 'Medium'
        if n <= 300:  return 'High'
        return 'Critical'
    by_dist_full = df['district_name'].value_counts().reset_index()
    by_dist_full.columns = ['District', 'Total Cases']
    by_dist_full['Severity_level'] = by_dist_full['Total Cases'].apply(severity_band)
    by_dist_full['Reporting Period'] = 'Current Dataset (2024 → 2026 YTD)'
    by_dist_full.to_csv(os.path.join(PROCESSED, 'district_severity.csv'), index=False)
    print(f'  → {os.path.join(PROCESSED, "district_severity.csv")}')

    # -------- Sample 15 cases for human review
    sample = df.sample(min(15, len(df)), random_state=42)[
        ['incident_date', 'district_name', 'police_station',
         'level3_case_nature', 'minority_community', 'description']
    ].copy()
    sample['description'] = sample['description'].astype(str).str[:200]
    sample_path = os.path.join(PROCESSED, 'sample_cases_for_review.csv')
    sample.to_csv(sample_path, index=False)
    print(f'  → {sample_path}')

    # -------- Save summary JSON for the doc
    # Convert any numpy types to native ints for clean JSON
    def jsonify(v):
        if hasattr(v, 'item'):
            try: return v.item()
            except Exception: pass
        return v
    summary = {k: ({k2: jsonify(v2) for k2, v2 in v.items()} if isinstance(v, dict) else jsonify(v))
               for k, v in summary.items()}
    with open(os.path.join(PROCESSED, 'eda_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)
    print(f'  → {os.path.join(PROCESSED, "eda_summary.json")}')
    print('\n[done]')


if __name__ == '__main__':
    main()
