-- Religious-calendar features (one row per minority_incidents case).
-- Database: db_predictive_policing
-- Source: data/external/religious_calendar.csv

DROP TABLE IF EXISTS minority_features_religious_calendar;

CREATE TABLE minority_features_religious_calendar (
    case_id                            INTEGER PRIMARY KEY,

    -- Days to NEXT event per community (NULL if no upcoming event known)
    days_to_next_islamic_event         INTEGER,
    days_to_next_christian_event       INTEGER,
    days_to_next_hindu_event           INTEGER,
    days_to_next_sikh_event            INTEGER,
    days_to_next_any_event             INTEGER,

    -- Days since LAST event per community (NULL if no past event known)
    days_since_last_islamic_event      INTEGER,
    days_since_last_christian_event    INTEGER,
    days_since_last_hindu_event        INTEGER,
    days_since_last_sikh_event         INTEGER,

    -- Two or more communities have at least one event within ±3 days
    is_multi_religion_overlap_week     BOOLEAN,

    -- Weighted count of events in ±7-day window. major=2, observance=1.
    religious_density_score            DOUBLE PRECISION,

    -- 1 if the case fell on or within ±1 day of any major event
    on_major_event_day                 BOOLEAN,

    generated_at                       TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_relcal_density ON minority_features_religious_calendar(religious_density_score);
CREATE INDEX idx_relcal_overlap ON minority_features_religious_calendar(is_multi_religion_overlap_week);
CREATE INDEX idx_relcal_major   ON minority_features_religious_calendar(on_major_event_day);
