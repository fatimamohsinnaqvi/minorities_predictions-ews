#!/usr/bin/env python3
"""
Load the VCM (Virtual Center for Minorities) case dataset.

The source can be:
  - A CSV/Excel file dropped into data/raw/
  - A database table (when access is set up)

Output: data/processed/vcm_cases.csv with cleaned, standardized columns.

This is a stub until the actual VCM data source is wired in.
"""
import argparse
import os
import sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
RAW_DIR = os.path.join(PROJECT_ROOT, 'data', 'raw')
PROCESSED_DIR = os.path.join(PROJECT_ROOT, 'data', 'processed')

# Expected canonical column names after cleaning. The loader maps source
# columns to these regardless of input format.
CANONICAL_COLS = [
    'case_id',
    'reported_at',
    'district',
    'police_station',
    'lat',
    'lon',
    'incident_type',
    'description',
    'minority_community',
    'outcome',
    'feedback_rating',
]


def find_source_file():
    """Auto-detect VCM source file in data/raw/."""
    if not os.path.isdir(RAW_DIR):
        return None
    candidates = []
    for fn in os.listdir(RAW_DIR):
        if fn.startswith('.'):
            continue
        if fn.lower().endswith(('.csv', '.xlsx', '.xls')):
            candidates.append(os.path.join(RAW_DIR, fn))
    return candidates[0] if candidates else None


def load(path):
    if path.lower().endswith(('.xlsx', '.xls')):
        return pd.read_excel(path)
    return pd.read_csv(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', help='Path to source CSV/Excel '
                                       '(default: autodetect in data/raw/)')
    args = ap.parse_args()

    src = args.source or find_source_file()
    if not src:
        print('[ERR] no VCM source file found.\n'
              f'      drop the VCM export into {RAW_DIR}/ '
              'and re-run.', file=sys.stderr)
        sys.exit(1)

    print(f'[load] reading {src}')
    df = load(src)
    print(f'[load] rows: {len(df)}, columns: {list(df.columns)}')

    # TODO: column mapping once we see the real schema
    print('\n[TODO] map source columns to CANONICAL_COLS:')
    for c in CANONICAL_COLS:
        print(f'   {c}')

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    out = os.path.join(PROCESSED_DIR, 'vcm_cases.csv')
    df.to_csv(out, index=False)
    print(f'\n[OK] wrote pass-through copy to {out}  (mapping pending)')


if __name__ == '__main__':
    main()
