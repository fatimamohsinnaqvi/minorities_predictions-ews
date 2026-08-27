#!/usr/bin/env python3
"""
PS-week forecaster — honest temporal evaluation + upgrades.

Standalone (reads the CSV snapshot, NOT the DB) so it runs offline. Does
four things the original single-split train_psweek.py does not:

  1. ROLLING-ORIGIN (walk-forward) validation with a 30-day embargo
     between train and test, so adjacent weeks' overlapping 30-day label
     windows can't leak future into past. Reports per-fold AND averaged
     metrics instead of one noisy cutoff.

  2. HONEST Precision@K + LIFT. Lift@K = precision@K / test base rate, so
     a big-looking lift is always shown next to its absolute precision.

  3. CALIBRATION. Raw-probability reliability (Brier, ECE) on the final
     out-of-time fold, then an isotonic re-fit, with a before/after plot.

  4. CALENDAR INTERACTION FEATURES (festival overlap, religious x political
     coincidence, imminence). Re-runs rolling-origin with base vs
     base+interaction features to see if they actually help out-of-time.

Outputs:
  outputs/reports/psweek_temporal_eval.json
  outputs/figures/model/psweek_rolling_origin.png
  outputs/figures/model/psweek_calibration.png
"""
import json
import os
import sys
from datetime import datetime

import joblib  # noqa: F401  (kept for parity; models are not persisted here)
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
from evaluate import precision_recall_at_k  # noqa: E402

PROJECT = os.path.abspath(os.path.join(HERE, '..', '..'))
CSV = os.path.join(PROJECT, 'data', 'csv_snapshot', 'minority_psweek_train.csv')
REPORTS_DIR = os.path.join(PROJECT, 'outputs', 'reports')
FIG_DIR = os.path.join(PROJECT, 'outputs', 'figures', 'model')
for d in (REPORTS_DIR, FIG_DIR):
    os.makedirs(d, exist_ok=True)

TARGET = 'target_30d'
EMBARGO_DAYS = 30          # gap between train end and test start
KS = (10, 20, 50)

# Identifiers / labels — never features
NON_FEATURE = {
    'police_station_id', 'police_station',
    'district_id', 'district_name',
    'week_start_date',
    'target_7d', 'target_30d',
}

# Test windows for rolling-origin (expanding train window each time).
# Each fold trains on everything up to (test_start - EMBARGO_DAYS).
FOLDS = [
    ('2025Q1', '2025-01-01', '2025-04-01'),
    ('2025Q2', '2025-04-01', '2025-07-01'),
    ('2025Q3', '2025-07-01', '2025-10-01'),
    ('2025Q4', '2025-10-01', '2026-01-01'),
    ('2026Q1', '2026-01-01', '2026-04-01'),
    ('2026Q2', '2026-04-01', '2026-07-01'),
]


# ----------------------------------------------------------------------
# Feature engineering
# ----------------------------------------------------------------------
def add_interaction_features(df):
    """Calendar interaction / imminence features built from the existing
    days_to_next_* columns. Hypothesis (from the Research Design report):
    risk rises when multiple communities' festivals overlap, and when a
    religious date coincides with a political event."""
    d = df.copy()

    def le(col, thr):
        # 1 if an event of this type is within `thr` days ahead, else 0.
        return (pd.to_numeric(d[col], errors='coerce').fillna(9999) <= thr).astype(int)

    # Imminence of a major religious festival (within a week / fortnight).
    d['imminent_major_religious_7d'] = le('days_to_next_major_religious', 7)
    d['imminent_major_religious_14d'] = le('days_to_next_major_religious', 14)

    # Multi-community festival OVERLAP: how many communities have an event
    # within 14 days. Captures the "overlapping calendars raise tension" idea.
    overlap = (le('days_to_next_islamic_event', 14)
               + le('days_to_next_christian_event', 14)
               + le('days_to_next_hindu_event', 14)
               + le('days_to_next_sikh_event', 14))
    d['religious_overlap_count_14d'] = overlap
    d['religious_overlap_2plus_14d'] = (overlap >= 2).astype(int)

    # Religious date coinciding with a political event.
    d['relig_x_political_14d'] = (le('days_to_next_major_religious', 14)
                                  & le('days_to_next_political', 14)).astype(int)

    # Just after a major religious event (aftermath window).
    d['post_major_religious_7d'] = (
        pd.to_numeric(d['days_since_last_major_religious'], errors='coerce')
        .fillna(9999) <= 7).astype(int)

    return d


INTERACTION_COLS = [
    'imminent_major_religious_7d', 'imminent_major_religious_14d',
    'religious_overlap_count_14d', 'religious_overlap_2plus_14d',
    'relig_x_political_14d', 'post_major_religious_7d',
]


def make_matrix(df, feature_cols, medians=None):
    """Return X (float, median-imputed) for the given feature columns.
    medians: if provided (train medians), use them; else compute and return."""
    use = df[feature_cols].copy()
    for c in use.columns:
        if use[c].dtype == bool:
            use[c] = use[c].astype(int)
    use = use.apply(pd.to_numeric, errors='coerce')
    if medians is None:
        medians = use.median()
        medians = medians.fillna(0.0)
    use = use.fillna(medians)
    use = use.fillna(0.0)
    return use.values.astype(float), medians


def feature_columns(df, include_interactions):
    cols = [c for c in df.columns if c not in NON_FEATURE and c != 'qtr']
    if not include_interactions:
        cols = [c for c in cols if c not in INTERACTION_COLS]
    return cols


# ----------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------
def fit_lr(X, y):
    pipe = Pipeline([
        ('scaler', StandardScaler()),
        ('lr', LogisticRegression(class_weight='balanced',
                                  max_iter=5000, solver='lbfgs')),
    ])
    pipe.fit(X, y)
    return pipe


def fit_rf(X, y):
    rf = RandomForestClassifier(
        n_estimators=300, max_depth=None, min_samples_leaf=4,
        class_weight='balanced', n_jobs=-1, random_state=42)
    rf.fit(X, y)
    return rf


def k_metrics(y_true, scores, base_rate):
    out = {}
    for k in KS:
        p, r, h = precision_recall_at_k(y_true, scores, k)
        out[f'precision_at_{k}'] = round(p, 4)
        out[f'recall_at_{k}'] = round(r, 4)
        out[f'hits_at_{k}'] = h
        out[f'lift_at_{k}'] = round(p / base_rate, 2) if base_rate > 0 else None
    return out


# ----------------------------------------------------------------------
# Rolling-origin
# ----------------------------------------------------------------------
def rolling_origin(df, include_interactions, label):
    feat_cols = feature_columns(df, include_interactions)
    fold_rows = []
    for name, test_start, test_end in FOLDS:
        ts = pd.Timestamp(test_start)
        te = pd.Timestamp(test_end)
        train_end = ts - pd.Timedelta(days=EMBARGO_DAYS)

        tr = df[df['week_start_date'] < train_end]
        teidx = (df['week_start_date'] >= ts) & (df['week_start_date'] < te)
        test = df[teidx]

        if tr[TARGET].sum() < 10 or test[TARGET].sum() < 5:
            # not enough signal to train/evaluate this fold honestly
            fold_rows.append({'fold': name, 'skipped': True,
                              'train_pos': int(tr[TARGET].sum()),
                              'test_pos': int(test[TARGET].sum())})
            continue

        X_tr, med = make_matrix(tr, feat_cols)
        y_tr = tr[TARGET].astype(int).values
        X_te, _ = make_matrix(test, feat_cols, medians=med)
        y_te = test[TARGET].astype(int).values
        base = y_te.mean()

        lr = fit_lr(X_tr, y_tr)
        rf = fit_rf(X_tr, y_tr)
        p_lr = lr.predict_proba(X_te)[:, 1]
        p_rf = rf.predict_proba(X_te)[:, 1]

        row = {
            'fold': name, 'skipped': False,
            'train_end': str(train_end.date()),
            'test_window': f'{test_start}..{test_end}',
            'train_rows': len(tr), 'test_rows': len(test),
            'test_pos': int(y_te.sum()),
            'test_base_rate': round(float(base), 5),
            'lr_roc_auc': round(float(roc_auc_score(y_te, p_lr)), 4),
            'lr_pr_auc': round(float(average_precision_score(y_te, p_lr)), 4),
            'rf_roc_auc': round(float(roc_auc_score(y_te, p_rf)), 4),
            'rf_pr_auc': round(float(average_precision_score(y_te, p_rf)), 4),
        }
        for mdl, sc in (('lr', p_lr), ('rf', p_rf)):
            for kk, vv in k_metrics(y_te, sc, base).items():
                row[f'{mdl}_{kk}'] = vv
        fold_rows.append(row)
        print(f'  [{label}] {name}: LR AUC={row["lr_roc_auc"]} '
              f'P@20={row["lr_precision_at_20"]} lift@20={row["lr_lift_at_20"]} '
              f'(test pos={row["test_pos"]}, base={row["test_base_rate"]})')

    used = [r for r in fold_rows if not r.get('skipped')]
    avg = {}
    if used:
        agg_keys = ['lr_roc_auc', 'lr_pr_auc', 'rf_roc_auc', 'rf_pr_auc']
        for k in KS:
            agg_keys += [f'lr_precision_at_{k}', f'lr_recall_at_{k}', f'lr_lift_at_{k}',
                         f'rf_precision_at_{k}', f'rf_recall_at_{k}', f'rf_lift_at_{k}']
        for k in agg_keys:
            vals = [r[k] for r in used if r.get(k) is not None]
            avg[k] = round(float(np.mean(vals)), 4) if vals else None
    return {'feature_set': label, 'n_features': len(feat_cols),
            'folds': fold_rows, 'mean_over_folds': avg}


# ----------------------------------------------------------------------
# Calibration (final out-of-time fold)
# ----------------------------------------------------------------------
def calibration_analysis(df, include_interactions):
    feat_cols = feature_columns(df, include_interactions)
    # Train on everything up to 2025-12-02 (30d embargo before 2026), test 2026+.
    ts = pd.Timestamp('2026-01-01')
    train_end = ts - pd.Timedelta(days=EMBARGO_DAYS)
    tr = df[df['week_start_date'] < train_end]
    test = df[df['week_start_date'] >= ts]

    X_tr, med = make_matrix(tr, feat_cols)
    y_tr = tr[TARGET].astype(int).values
    X_te, _ = make_matrix(test, feat_cols, medians=med)
    y_te = test[TARGET].astype(int).values

    lr = fit_lr(X_tr, y_tr)
    p_raw = lr.predict_proba(X_te)[:, 1]

    # Isotonic re-fit using a time-ordered internal calibration slice:
    # fit base on the earlier 80% of train, fit isotonic on the latest 20%.
    tr_sorted = tr.sort_values('week_start_date')
    cut = int(len(tr_sorted) * 0.8)
    base_part = tr_sorted.iloc[:cut]
    cal_part = tr_sorted.iloc[cut:]
    Xb, medb = make_matrix(base_part, feat_cols)
    yb = base_part[TARGET].astype(int).values
    Xc, _ = make_matrix(cal_part, feat_cols, medians=medb)
    yc = cal_part[TARGET].astype(int).values
    lr_base = fit_lr(Xb, yb)
    p_cal_in = lr_base.predict_proba(Xc)[:, 1]
    iso = IsotonicRegression(out_of_bounds='clip')
    iso.fit(p_cal_in, yc)
    Xte2, _ = make_matrix(test, feat_cols, medians=medb)
    p_cal = iso.predict(lr_base.predict_proba(Xte2)[:, 1])

    def ece(y, p, n_bins=10):
        bins = np.linspace(0, 1, n_bins + 1)
        idx = np.digitize(p, bins) - 1
        idx = np.clip(idx, 0, n_bins - 1)
        e, N = 0.0, len(p)
        for b in range(n_bins):
            m = idx == b
            if m.sum() == 0:
                continue
            e += (m.sum() / N) * abs(y[m].mean() - p[m].mean())
        return float(e)

    def reliability(y, p, n_bins=10):
        bins = np.linspace(0, 1, n_bins + 1)
        idx = np.digitize(p, bins) - 1
        idx = np.clip(idx, 0, n_bins - 1)
        xs, ys = [], []
        for b in range(n_bins):
            m = idx == b
            if m.sum() == 0:
                continue
            xs.append(p[m].mean())
            ys.append(y[m].mean())
        return xs, ys

    out = {
        'test_rows': len(test), 'test_pos': int(y_te.sum()),
        'test_base_rate': round(float(y_te.mean()), 5),
        'brier_raw': round(float(brier_score_loss(y_te, p_raw)), 6),
        'brier_isotonic': round(float(brier_score_loss(y_te, p_cal)), 6),
        'ece_raw': round(ece(y_te, p_raw), 5),
        'ece_isotonic': round(ece(y_te, p_cal), 5),
        'mean_pred_raw': round(float(p_raw.mean()), 5),
        'mean_pred_isotonic': round(float(p_cal.mean()), 5),
    }

    # Plot reliability before/after
    xr, yr = reliability(y_te, p_raw)
    xc2, yc2 = reliability(y_te, p_cal)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], '--', color='#94a3b8', label='perfect')
    ax.plot(xr, yr, 'o-', color='#c0392b',
            label=f'raw LR (Brier {out["brier_raw"]}, ECE {out["ece_raw"]})')
    ax.plot(xc2, yc2, 's-', color='#16a085',
            label=f'isotonic (Brier {out["brier_isotonic"]}, ECE {out["ece_isotonic"]})')
    ax.set_xlabel('Mean predicted probability')
    ax.set_ylabel('Observed positive rate')
    ax.set_title('PS-week forecaster — calibration (2026 out-of-time)',
                 fontweight='bold')
    ax.legend(fontsize=8, loc='upper left')
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, 'psweek_calibration.png'),
                dpi=130, bbox_inches='tight')
    plt.close(fig)
    return out


def plot_rolling(base_res, inter_res):
    used_b = [r for r in base_res['folds'] if not r.get('skipped')]
    names = [r['fold'] for r in used_b]
    lr_auc_b = [r['lr_roc_auc'] for r in used_b]
    used_i = [r for r in inter_res['folds'] if not r.get('skipped')]
    lr_auc_i = [r['lr_roc_auc'] for r in used_i]
    p20_b = [r['lr_precision_at_20'] for r in used_b]
    p20_i = [r['lr_precision_at_20'] for r in used_i]

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
    x = np.arange(len(names))
    a1.plot(x, lr_auc_b, 'o-', color='#34495e', label='base features')
    a1.plot(x, lr_auc_i, 's-', color='#16a085', label='+ interactions')
    a1.axhline(0.5, ls='--', color='#cbd5e1')
    a1.set_xticks(x); a1.set_xticklabels(names, rotation=45)
    a1.set_ylabel('LR ROC AUC'); a1.set_title('Rolling-origin ROC AUC by fold',
                                               fontweight='bold')
    a1.legend(fontsize=8)
    a2.plot(x, p20_b, 'o-', color='#34495e', label='base features')
    a2.plot(x, p20_i, 's-', color='#16a085', label='+ interactions')
    a2.set_xticks(x); a2.set_xticklabels(names, rotation=45)
    a2.set_ylabel('LR Precision@20'); a2.set_title('Rolling-origin Precision@20 by fold',
                                                    fontweight='bold')
    a2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, 'psweek_rolling_origin.png'),
                dpi=130, bbox_inches='tight')
    plt.close(fig)


def main():
    df = pd.read_csv(CSV, parse_dates=['week_start_date'])
    df = add_interaction_features(df)
    print(f'[load] {len(df):,} PS-weeks, {df["police_station_id"].nunique()} PSes')

    print('\n[rolling-origin] BASE features')
    base_res = rolling_origin(df, include_interactions=False, label='base')
    print('\n[rolling-origin] BASE + INTERACTION features')
    inter_res = rolling_origin(df, include_interactions=True, label='base+interact')

    print('\n[calibration] final 2026 out-of-time fold')
    calib = calibration_analysis(df, include_interactions=True)
    print(f'  Brier raw={calib["brier_raw"]}  isotonic={calib["brier_isotonic"]}')
    print(f'  ECE   raw={calib["ece_raw"]}  isotonic={calib["ece_isotonic"]}')

    plot_rolling(base_res, inter_res)

    summary = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'target': TARGET,
        'embargo_days': EMBARGO_DAYS,
        'data': {
            'rows': len(df),
            'pses': int(df['police_station_id'].nunique()),
            'date_min': str(df['week_start_date'].min().date()),
            'date_max': str(df['week_start_date'].max().date()),
            'overall_pos_rate': round(float(df[TARGET].mean()), 5),
        },
        'rolling_origin_base': base_res,
        'rolling_origin_interactions': inter_res,
        'calibration': calib,
        'interaction_features': INTERACTION_COLS,
    }
    out_path = os.path.join(REPORTS_DIR, 'psweek_temporal_eval.json')
    with open(out_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f'\n[OK] wrote {out_path}')
    print(f'[OK] figures: psweek_rolling_origin.png, psweek_calibration.png')

    # Headline comparison
    b = base_res['mean_over_folds']; i = inter_res['mean_over_folds']
    print('\n=== MEAN OVER FOLDS (LR) ===')
    print(f'  ROC AUC:       base {b.get("lr_roc_auc")}  ->  +interact {i.get("lr_roc_auc")}')
    print(f'  PR AUC:        base {b.get("lr_pr_auc")}  ->  +interact {i.get("lr_pr_auc")}')
    print(f'  Precision@20:  base {b.get("lr_precision_at_20")}  ->  +interact {i.get("lr_precision_at_20")}')
    print(f'  Lift@20:       base {b.get("lr_lift_at_20")}  ->  +interact {i.get("lr_lift_at_20")}')


if __name__ == '__main__':
    main()
