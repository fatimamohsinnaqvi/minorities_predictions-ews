"""
Shared evaluation utilities for the modeling phase.

Produces:
  - Standard metrics (ROC AUC, PR AUC, F1, precision, recall, confusion matrix)
  - Precision@k / Recall@k at the operationally relevant top-N
  - Per-community fairness breakdown
  - Calibration data (decile bins)
"""
from collections import OrderedDict

import numpy as np
import pandas as pd
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    precision_score, recall_score, f1_score,
    confusion_matrix, classification_report,
)


def precision_recall_at_k(y_true, scores, k):
    """For top-k highest-scoring examples, return precision and recall.

    Returns (precision, recall, hits)."""
    n = len(scores)
    if k > n:
        k = n
    if k <= 0:
        return 0.0, 0.0, 0
    order = np.argsort(scores)[::-1]
    top_idx = order[:k]
    hits = int(y_true[top_idx].sum())
    total_pos = int(y_true.sum())
    precision = hits / k if k > 0 else 0.0
    recall = hits / total_pos if total_pos > 0 else 0.0
    return precision, recall, hits


def overall_metrics(y_true, scores, threshold=0.5):
    """Compute the full set of standard binary-classification metrics."""
    y_pred = (scores >= threshold).astype(int)
    out = OrderedDict()
    pos = int(y_true.sum())
    neg = int(len(y_true) - pos)
    out['n'] = int(len(y_true))
    out['n_positive'] = pos
    out['n_negative'] = neg
    out['positive_rate'] = round(pos / max(1, len(y_true)), 4)

    # AUCs only meaningful if both classes present
    if pos > 0 and neg > 0:
        out['roc_auc'] = round(float(roc_auc_score(y_true, scores)), 4)
        out['pr_auc']  = round(float(average_precision_score(y_true, scores)), 4)
    else:
        out['roc_auc'] = None
        out['pr_auc']  = None

    out['threshold'] = threshold
    out['precision'] = round(float(precision_score(y_true, y_pred, zero_division=0)), 4)
    out['recall']    = round(float(recall_score(y_true, y_pred, zero_division=0)), 4)
    out['f1']        = round(float(f1_score(y_true, y_pred, zero_division=0)), 4)

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    out['tn'], out['fp'], out['fn'], out['tp'] = (
        int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])
    )

    # Precision@k / Recall@k for k = 10, 20, 50
    for k in (10, 20, 50):
        p, r, h = precision_recall_at_k(y_true, scores, k)
        out[f'precision_at_{k}'] = round(p, 4)
        out[f'recall_at_{k}']    = round(r, 4)
        out[f'hits_at_{k}']      = h

    return out


def per_group_breakdown(y_true, scores, groups, group_name='group', threshold=0.5):
    """Per-group metrics. groups is a Series aligned with y_true / scores."""
    rows = []
    for g in sorted(set(groups)):
        mask = (groups == g).values
        n = int(mask.sum())
        if n == 0:
            continue
        yt = y_true[mask]; sc = scores[mask]
        pos = int(yt.sum()); neg = int(n - pos)
        roc = (round(float(roc_auc_score(yt, sc)), 4)
               if pos > 0 and neg > 0 else None)
        pa20, ra20, _ = precision_recall_at_k(yt, sc, 20)
        y_pred = (sc >= threshold).astype(int)
        rows.append({
            group_name: g,
            'n': n, 'n_pos': pos, 'n_neg': neg,
            'roc_auc': roc,
            'precision': round(float(precision_score(yt, y_pred, zero_division=0)), 4),
            'recall':    round(float(recall_score(yt, y_pred, zero_division=0)), 4),
            'precision_at_20': round(pa20, 4),
            'recall_at_20':    round(ra20, 4),
        })
    return pd.DataFrame(rows)


def calibration_table(y_true, scores, n_bins=10):
    """Group predictions into n equal-width bins and report observed positive
    rate per bin — the input to a calibration plot."""
    df = pd.DataFrame({'y': y_true, 'p': scores})
    df['bin'] = pd.cut(df['p'], bins=np.linspace(0, 1, n_bins + 1),
                        include_lowest=True)
    out = df.groupby('bin', observed=True).agg(
        mean_pred=('p', 'mean'),
        observed=('y', 'mean'),
        n=('y', 'size'),
    ).reset_index()
    return out
