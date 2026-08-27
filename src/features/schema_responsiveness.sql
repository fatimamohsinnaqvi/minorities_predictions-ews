-- Police-responsiveness features (one row per minority_incidents case).
-- Source: test_1124.response_time (per-PS aggregated to year-month, then
-- the 3 months prior to each case are pooled).
-- Database: db_predictive_policing

DROP TABLE IF EXISTS minority_features_responsiveness;

CREATE TABLE minority_features_responsiveness (
    case_id                                   INTEGER PRIMARY KEY,

    avg_response_time_min_ps_90d              DOUBLE PRECISION,   -- mean of `response_time` (seconds → min) in prior 3 months, same PS
    median_response_time_min_ps_90d           DOUBLE PRECISION,   -- median, prior 3 months
    n_cases_ps_90d                            INTEGER,            -- volume in prior 3 months, same PS
    positive_feedback_rate_ps_90d             DOUBLE PRECISION,   -- share with caller_feedback='Positive'

    -- Decile rank of avg_response_time_min_ps_90d within the case's month
    -- across ALL Punjab PSes (1 = fastest, 10 = slowest)
    responsiveness_decile_ps                  INTEGER,

    -- Data-quality flags
    has_responsiveness_data                   BOOLEAN,            -- false if no prior cases for the PS

    generated_at                              TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_resp_avg     ON minority_features_responsiveness(avg_response_time_min_ps_90d);
CREATE INDEX idx_resp_decile  ON minority_features_responsiveness(responsiveness_decile_ps);
