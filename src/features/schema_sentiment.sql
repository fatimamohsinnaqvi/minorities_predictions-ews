-- Social-media sentiment features (one row per minority_incidents case).
-- Source: NONE WIRED IN YET — placeholder schema.
-- All values are NULL until a sentiment data feed (X/Facebook scrape +
-- Urdu/Punjabi sentiment lexicon) is connected.
-- Database: db_predictive_policing

DROP TABLE IF EXISTS minority_features_sentiment;

CREATE TABLE minority_features_sentiment (
    case_id                       INTEGER PRIMARY KEY,

    sm_post_count_7d              INTEGER,
    sm_negative_share_7d          DOUBLE PRECISION,
    sm_post_count_30d             INTEGER,
    sm_negative_share_30d         DOUBLE PRECISION,
    sm_velocity                   DOUBLE PRECISION,

    has_sentiment_data            BOOLEAN,             -- always FALSE in v1
    generated_at                  TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_sent_has ON minority_features_sentiment(has_sentiment_data);
