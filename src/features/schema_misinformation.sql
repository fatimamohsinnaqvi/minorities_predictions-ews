-- Misinformation-propagation features (one row per minority_incidents case).
-- Source: data/external/misinformation_events.csv
-- Database: db_predictive_policing

DROP TABLE IF EXISTS minority_features_misinformation;

CREATE TABLE minority_features_misinformation (
    case_id                             INTEGER PRIMARY KEY,

    -- Events in the SAME district (preferred signal). Includes "Punjab"
    -- wildcard events targeting the whole province.
    misinfo_event_in_window_district    BOOLEAN,    -- any same-district event in ±7 days
    misinfo_event_severity_district     INTEGER,    -- max severity (1-3) of in-window same-district events
    days_since_last_misinfo_event_district  INTEGER,    -- capped at 60

    -- Events anywhere in Punjab (broader signal).
    misinfo_event_in_window_anywhere    BOOLEAN,
    misinfo_event_severity_anywhere     INTEGER,
    days_since_last_misinfo_event_anywhere INTEGER,

    -- Targeted at this case's community (extra precision)
    misinfo_event_in_window_same_community BOOLEAN,

    generated_at                        TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_misinfo_dist ON minority_features_misinformation(misinfo_event_in_window_district);
CREATE INDEX idx_misinfo_anywhere ON minority_features_misinformation(misinfo_event_in_window_anywhere);
