#!/usr/bin/env python3
"""
Train the Random Forest model on the same per-case classification task.

Outputs (alongside the LR baseline):
  outputs/models/rf.pkl
  outputs/reports/rf_metrics.json
  outputs/figures/model/rf_*.png
"""
import json
import os
import sys
from datetime import datetime

import joblib
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestClassifier

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
from dataset import load_merged, temporal_split, prepare, class_balance  # noqa
from evaluate import (
    overall_metrics, per_group_breakdown, calibration_table,
)  # noqa
from train_lr import plot_confusion, plot_calibration, plot_per_group  # noqa


PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
MODEL_DIR = os.path.join(PROJECT, 'outputs', 'models')
REPORTS_DIR = os.path.join(PROJECT, 'outputs', 'reports')
FIG_DIR = os.path.join(PROJECT, 'outputs', 'figures', 'model')


def main():
    print('[load] minority_features_merged ...')
    df = load_merged()
    train_df, test_df = temporal_split(df)
    print(f'[split] train={len(train_df):,}  test={len(test_df):,}')

    print('\n[prepare] ...')
    X_train, y_train, feat_names, train_meta, fitted_cats = prepare(train_df, fitted_cats=None)
    X_test,  y_test,  feat_names_te, test_meta,  _ = prepare(test_df, fitted_cats=fitted_cats)

    if feat_names != feat_names_te:
        common = sorted(set(feat_names) & set(feat_names_te))
        X_tr_df = pd.DataFrame(X_train, columns=feat_names)
        X_te_df = pd.DataFrame(X_test, columns=feat_names_te)
        X_tr_df = X_tr_df.reindex(columns=common, fill_value=0.0)
        X_te_df = X_te_df.reindex(columns=common, fill_value=0.0)
        X_train = X_tr_df.values; X_test = X_te_df.values
        feat_names = common

    pos_tr, neg_tr, rate_tr = class_balance(y_train)
    pos_te, neg_te, rate_te = class_balance(y_test)
    print(f'  features={len(feat_names)}')
    print(f'  train: pos={pos_tr}/{rate_tr*100:.2f}%  neg={neg_tr}')
    print(f'  test:  pos={pos_te}/{rate_te*100:.2f}%  neg={neg_te}')

    print('\n[train] RandomForestClassifier ...')
    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=2,
        class_weight='balanced',
        n_jobs=-1,
        random_state=42,
    )
    rf.fit(X_train, y_train)
    print('  fitted.')

    train_scores = rf.predict_proba(X_train)[:, 1]
    test_scores  = rf.predict_proba(X_test)[:, 1]

    train_metrics = overall_metrics(y_train, train_scores)
    test_metrics  = overall_metrics(y_test,  test_scores)
    comm_breakdown = per_group_breakdown(
        y_test, test_scores, test_meta['minority_community'],
        group_name='minority_community')
    lah_breakdown = per_group_breakdown(
        y_test, test_scores, test_meta['is_lahore'],
        group_name='is_lahore')
    calib = calibration_table(y_test, test_scores)

    # ---- Feature importances
    importances = pd.DataFrame({
        'feature': feat_names,
        'importance': rf.feature_importances_,
    }).sort_values('importance', ascending=False).head(20)

    # ---- Save
    model_path = os.path.join(MODEL_DIR, 'rf.pkl')
    joblib.dump({
        'model': rf,
        'feature_names': feat_names,
        'fitted_cats': fitted_cats,
        'trained_at': datetime.utcnow().isoformat(),
    }, model_path)
    print(f'\n[OK] model saved: {model_path}')

    plot_confusion(test_metrics, 'Confusion matrix — RF, test',
                    os.path.join(FIG_DIR, 'rf_cm_test.png'))
    plot_calibration(calib, os.path.join(FIG_DIR, 'rf_calibration.png'))
    plot_per_group(comm_breakdown, 'minority_community',
                    os.path.join(FIG_DIR, 'rf_per_community.png'))

    # Feature importance plot
    fig, ax = plt.subplots(figsize=(8, 6))
    importances.iloc[::-1].plot(
        kind='barh', x='feature', y='importance', ax=ax,
        color='#16a085', legend=False)
    ax.set_title('Top 20 features — RF importance', fontweight='bold')
    ax.set_xlabel('Mean decrease in impurity'); ax.set_ylabel('')
    fig.tight_layout(); fig.savefig(
        os.path.join(FIG_DIR, 'rf_feature_importance.png'),
        dpi=130, bbox_inches='tight')
    plt.close(fig)

    summary = {
        'model': 'RandomForestClassifier',
        'trained_at': datetime.utcnow().isoformat(),
        'features_count': len(feat_names),
        'hyperparameters': {
            'n_estimators': 300,
            'max_depth': None,
            'min_samples_leaf': 2,
            'class_weight': 'balanced',
        },
        'train': train_metrics,
        'test': test_metrics,
        'community_breakdown': comm_breakdown.to_dict('records'),
        'lahore_breakdown': lah_breakdown.to_dict('records'),
        'top_features': importances.to_dict('records'),
    }
    metrics_path = os.path.join(REPORTS_DIR, 'rf_metrics.json')
    with open(metrics_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f'[OK] metrics saved: {metrics_path}')

    print('\n========== TEST METRICS (held-out 2026 YTD) ==========')
    for k in ('n', 'n_positive', 'roc_auc', 'pr_auc', 'precision', 'recall', 'f1',
              'tp', 'fp', 'fn', 'tn',
              'precision_at_10', 'recall_at_10',
              'precision_at_20', 'recall_at_20',
              'precision_at_50', 'recall_at_50'):
        v = test_metrics.get(k)
        print(f'  {k:<25} {v}')

    print('\n========== Per-community breakdown (test set) ==========')
    print(comm_breakdown.to_string(index=False))

    print('\n========== Top 15 features by importance ==========')
    print(importances[['feature', 'importance']].head(15).to_string(index=False))

    print('\n[done]')


if __name__ == '__main__':
    main()
