-- Prior incident density features (one row per minority_incidents case).
-- Database: db_predictive_policing

DROP TABLE IF EXISTS minority_features_prior_density;

CREATE TABLE minority_features_prior_density (
    case_id                                 INTEGER PRIMARY KEY,

    prior_7d_ps_count                       INTEGER,
    prior_30d_ps_count                      INTEGER,
    prior_60d_ps_count                      INTEGER,
    prior_90d_ps_count                      INTEGER,

    prior_7d_district_count                 INTEGER,
    prior_30d_district_count                INTEGER,
    prior_60d_district_count                INTEGER,
    prior_90d_district_count                INTEGER,

    prior_30d_ps_minority_targeted          INTEGER,
    prior_30d_district_minority_targeted    INTEGER,

    escalation_ratio_7v30                   DOUBLE PRECISION,

    generated_at                            TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_pdens_ps_30d ON minority_features_prior_density(prior_30d_ps_count);
CREATE INDEX idx_pdens_esc    ON minority_features_prior_density(escalation_ratio_7v30);
