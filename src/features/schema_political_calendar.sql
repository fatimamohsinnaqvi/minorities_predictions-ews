-- Political-calendar features (one row per minority_incidents case).
-- Source: data/external/political_calendar.csv
-- Database: db_predictive_policing

DROP TABLE IF EXISTS minority_features_political_calendar;

CREATE TABLE minority_features_political_calendar (
    case_id                             INTEGER PRIMARY KEY,

    days_to_next_political_event        INTEGER,
    days_since_last_political_event     INTEGER,
    days_to_next_major_political_event  INTEGER,
    days_since_last_major_political_event INTEGER,

    in_election_period                  BOOLEAN,    -- within ±30 days of a national_election / by_election
    is_protest_window                   BOOLEAN,    -- within ±7 days of a protest event
    political_event_density_30d         INTEGER,    -- count of political events in ±15 days

    generated_at                        TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_polcal_density  ON minority_features_political_calendar(political_event_density_30d);
CREATE INDEX idx_polcal_election ON minority_features_political_calendar(in_election_period);
