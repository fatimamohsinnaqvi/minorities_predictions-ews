#!/usr/bin/env python3
"""
Social-media sentiment features.

**Placeholder.** This module creates the empty rows in
`minority_features_sentiment` with all feature columns set to NULL and
`has_sentiment_data = FALSE`.

It will be replaced by a real implementation when a sentiment data feed
is connected — see [docs/03_feature_engineering.md] §1 for the data
sources and feature definitions.

Until then, downstream model code must treat these columns as missing.
Tree-based models (RF/XGB) handle NULL natively; a linear baseline will
need a sentinel.
"""
import os
import sys
from datetime import datetime

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, 'schema_sentiment.sql')


def main():
    conn = get_db_postgres_predictive()
    cur = conn.cursor()
    with open(SCHEMA_PATH) as f:
        cur.execute(f.read())
    conn.commit()
    print('[ddl] minority_features_sentiment recreated (placeholder)')

    cur.execute("SELECT id FROM minority_incidents")
    case_ids = [r[0] for r in cur.fetchall()]
    print(f'[populate] {len(case_ids)} cases — all NULL, has_sentiment_data=FALSE')

    now = datetime.utcnow()
    INSERT = """INSERT INTO minority_features_sentiment (
        case_id, sm_post_count_7d, sm_negative_share_7d,
        sm_post_count_30d, sm_negative_share_30d, sm_velocity,
        has_sentiment_data, generated_at
    ) VALUES (%s, NULL, NULL, NULL, NULL, NULL, FALSE, %s)"""
    for cid in case_ids:
        cur.execute(INSERT, (int(cid), now))
    conn.commit()

    print('[OK] sentiment placeholder rows inserted.')
    print('     Replace this script when a data feed is connected.')
    cur.close(); conn.close()


if __name__ == '__main__':
    main()
