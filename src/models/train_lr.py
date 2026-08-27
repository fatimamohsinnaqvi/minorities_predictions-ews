#!/usr/bin/env python3
"""
Train the Logistic Regression baseline.

  Target: minority_features_merged.is_minority_targeted
  Split: temporal — train 2024–2025, test 2026 YTD
  Class imbalance: handled via class_weight='balanced'

Outputs:
  outputs/models/lr_baseline.pkl     — joblib-pickled fitted pipeline + meta
  outputs/reports/model_card_lr.md   — model card (real numbers)
  outputs/figures/model/             — confusion matrix, calibration plot,
                                       per-community bar
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
from dataset import load_merged, temporal_split, prepare, class_balance  # noqa
from evaluate import (
    overall_metrics, per_group_breakdown, calibration_table,
)  # noqa


PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
MODEL_DIR = os.path.join(PROJECT, 'outputs', 'models')
REPORTS_DIR = os.path.join(PROJECT, 'outputs', 'reports')
FIG_DIR = os.path.join(PROJECT, 'outputs', 'figures', 'model')
for d in (MODEL_DIR, REPORTS_DIR, FIG_DIR):
    os.makedirs(d, exist_ok=True)


def plot_confusion(cm_dict, title, out_path):
    """cm_dict has keys tn fp fn tp."""
    cm = np.array([[cm_dict['tn'], cm_dict['fp']],
                    [cm_dict['fn'], cm_dict['tp']]], dtype=int)
    fig, ax = plt.subplots(figsize=(4.5, 4))
    im = ax.imshow(cm, cmap='Blues')
    ax.set_title(title, fontweight='bold')
    ax.set_xlabel('Predicted'); ax.set_ylabel('True')
    ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
    ax.set_xticklabels(['neg', 'pos']); ax.set_yticklabels(['neg', 'pos'])
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(cm[i, j]), ha='center', va='center',
                     color=('white' if cm[i, j] > cm.max() / 2 else 'black'),
                     fontsize=14)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches='tight')
    plt.close(fig)


def plot_calibration(calib_df, out_path):
    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.plot([0, 1], [0, 1], 'k--', alpha=0.4, label='perfect')
    sizes = calib_df['n'].values
    sizes_norm = 80 * (sizes / max(1, sizes.max())) + 10
    ax.scatter(calib_df['mean_pred'], calib_df['observed'],
                s=sizes_norm, alpha=0.6, color='#c0392b', edgecolor='black')
    ax.plot(calib_df['mean_pred'], calib_df['observed'], color='#c0392b', alpha=0.5)
    ax.set_xlabel('Mean predicted probability')
    ax.set_ylabel('Observed positive rate')
    ax.set_title('Calibration (decile bins) — LR baseline', fontweight='bold')
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out_path, dpi=130, bbox_inches='tight')
    plt.close(fig)


def plot_per_group(df, group_name, out_path):
    fig, ax = plt.subplots(figsize=(7, 4))
    df_plot = df.dropna(subset=['roc_auc']).copy()
    if df_plot.empty:
        ax.text(0.5, 0.5, 'no group has both positive and negative cases',
                ha='center', va='center')
    else:
        bars = ax.bar(df_plot[group_name].astype(str), df_plot['roc_auc'],
                       color='#34495e')
        ax.set_ylim(0, 1)
        ax.set_ylabel('ROC AUC')
        ax.set_title(f'Per-{group_name} ROC AUC — LR baseline', fontweight='bold')
        ax.axhline(0.5, ls='--', color='grey', alpha=0.5)
        for b, v in zip(bars, df_plot['roc_auc']):
            ax.text(b.get_x() + b.get_width()/2, v + 0.02, f'{v:.2f}',
                    ha='center', fontsize=9)
    fig.tight_layout(); fig.savefig(out_path, dpi=130, bbox_inches='tight')
    plt.close(fig)


def main():
    print('[load] minority_features_merged ...')
    df = load_merged()
    print(f'  total rows: {len(df):,}')

    train_df, test_df = temporal_split(df)
    print(f'\n[split] train (2024-2025): {len(train_df):,}')
    print(f'[split] test  (2026 YTD):  {len(test_df):,}')

    print('\n[prepare] train ...')
    X_train, y_train, feat_names, train_meta, fitted_cats = prepare(train_df, fitted_cats=None)
    pos_tr, neg_tr, rate_tr = class_balance(y_train)
    print(f'  features: {len(feat_names)}')
    print(f'  class balance — positives={pos_tr} ({rate_tr*100:.2f}%), negatives={neg_tr}')

    print('\n[prepare] test ...')
    X_test, y_test, feat_names_te, test_meta, _ = prepare(test_df, fitted_cats=fitted_cats)
    pos_te, neg_te, rate_te = class_balance(y_test)
    print(f'  features (must align with train): {len(feat_names_te)}')
    if feat_names != feat_names_te:
        # Re-align — categorical encoding can produce different col sets
        common = sorted(set(feat_names) & set(feat_names_te))
        print(f'  [warn] aligning to {len(common)} common columns')
        # Recompute as a DataFrame so we can pick consistent columns
        X_tr_df = pd.DataFrame(X_train, columns=feat_names)
        X_te_df = pd.DataFrame(X_test, columns=feat_names_te)
        for c in common:
            pass  # already in both
        X_tr_df = X_tr_df.reindex(columns=common, fill_value=0.0)
        X_te_df = X_te_df.reindex(columns=common, fill_value=0.0)
        X_train = X_tr_df.values; X_test = X_te_df.values
        feat_names = common
    print(f'  class balance — positives={pos_te} ({rate_te*100:.2f}%), negatives={neg_te}')

    print('\n[train] LogisticRegression (class_weight=balanced) ...')
    pipe = Pipeline([
        ('scaler', StandardScaler()),
        ('lr', LogisticRegression(
            class_weight='balanced',
            max_iter=5000, solver='lbfgs', n_jobs=-1)),
    ])
    pipe.fit(X_train, y_train)
    print('  fitted.')

    # ---- Evaluate
    print('\n[evaluate] computing metrics on train and test ...')
    train_scores = pipe.predict_proba(X_train)[:, 1]
    test_scores  = pipe.predict_proba(X_test)[:,  1]

    train_metrics = overall_metrics(y_train, train_scores)
    test_metrics  = overall_metrics(y_test,  test_scores)

    # Community breakdown on test set
    comm_breakdown = per_group_breakdown(
        y_test, test_scores, test_meta['minority_community'],
        group_name='minority_community',
    )
    lah_breakdown = per_group_breakdown(
        y_test, test_scores, test_meta['is_lahore'],
        group_name='is_lahore',
    )

    # Calibration
    calib = calibration_table(y_test, test_scores)

    # ---- Save model and meta
    model_path = os.path.join(MODEL_DIR, 'lr_baseline.pkl')
    joblib.dump({
        'pipeline': pipe,
        'feature_names': feat_names,
        'fitted_cats': fitted_cats,
        'trained_at': datetime.utcnow().isoformat(),
    }, model_path)
    print(f'\n[OK] model saved: {model_path}')

    # ---- Coefficient summary (top features by |coef|)
    coefs = pipe.named_steps['lr'].coef_[0]
    coef_df = pd.DataFrame({
        'feature': feat_names,
        'coef': coefs,
        'abs_coef': np.abs(coefs),
    }).sort_values('abs_coef', ascending=False)
    top_feats = coef_df.head(20)

    # ---- Figures
    plot_confusion(train_metrics, 'Confusion matrix — train',
                    os.path.join(FIG_DIR, 'lr_cm_train.png'))
    plot_confusion(test_metrics, 'Confusion matrix — test',
                    os.path.join(FIG_DIR, 'lr_cm_test.png'))
    plot_calibration(calib, os.path.join(FIG_DIR, 'lr_calibration.png'))
    plot_per_group(comm_breakdown, 'minority_community',
                    os.path.join(FIG_DIR, 'lr_per_community.png'))

    # ---- Save metrics JSON
    summary = {
        'model': 'LogisticRegression',
        'trained_at': datetime.utcnow().isoformat(),
        'features_count': len(feat_names),
        'train': train_metrics,
        'test': test_metrics,
        'community_breakdown': comm_breakdown.to_dict('records'),
        'lahore_breakdown': lah_breakdown.to_dict('records'),
        'top_features': top_feats.to_dict('records'),
    }
    metrics_path = os.path.join(REPORTS_DIR, 'lr_metrics.json')
    with open(metrics_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f'[OK] metrics saved: {metrics_path}')

    # ---- Print top-line numbers
    print('\n========== TEST METRICS (held-out 2026 YTD) ==========')
    for k in ('n', 'n_positive', 'n_negative', 'positive_rate',
              'roc_auc', 'pr_auc', 'precision', 'recall', 'f1',
              'tp', 'fp', 'fn', 'tn',
              'precision_at_10', 'recall_at_10',
              'precision_at_20', 'recall_at_20',
              'precision_at_50', 'recall_at_50'):
        v = test_metrics.get(k)
        print(f'  {k:<25} {v}')

    print('\n========== Per-community breakdown (test set) ==========')
    print(comm_breakdown.to_string(index=False))

    print('\n========== Top 15 features by |coef| ==========')
    print(top_feats[['feature', 'coef']].head(15).to_string(index=False))

    print('\n[done]')


if __name__ == '__main__':
    main()
