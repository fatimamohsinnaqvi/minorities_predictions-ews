-- minority_incidents: Punjab-wide working table for the early-warning project.
-- Source: test_1124.response_time
-- Database: db_predictive_policing
--
-- Includes any case where:
--   level2_case_nature = 'Religious Offences'   OR
--   description matches a minority keyword
--
-- Rebuilt on each loader run.

DROP TABLE IF EXISTS minority_incidents;

CREATE TABLE minority_incidents (
    id                       SERIAL PRIMARY KEY,

    -- identifiers from response_time
    case_number              TEXT,
    lead_id                  TEXT,

    -- time
    incident_date            DATE,
    accepted_time            TIMESTAMP,
    incident_year            INTEGER,
    incident_month           INTEGER,

    -- location
    district_id              TEXT,
    district_name            TEXT,
    police_station_id        TEXT,
    police_station           TEXT,
    lat                      DOUBLE PRECISION,
    long                     DOUBLE PRECISION,
    is_lahore                BOOLEAN,

    -- case nature taxonomy
    level1_case_nature       TEXT,
    level2_case_nature       TEXT,
    level3_case_nature       TEXT,

    -- free text + derived signals
    description              TEXT,
    match_source             TEXT,                   -- 'religious_offence' | 'desc_keyword' | 'both'
    matched_keywords         TEXT[],                 -- which minority keywords hit
    minority_community       TEXT,                   -- 'christian' | 'ahmadi' | 'hindu' | 'sikh' | 'multiple' | 'unspecified'
    is_minority_targeted     BOOLEAN,                -- strict label: religious_offence AND minority keyword

    loaded_at                TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_mi_date         ON minority_incidents(incident_date);
CREATE INDEX idx_mi_district     ON minority_incidents(district_id);
CREATE INDEX idx_mi_lahore       ON minority_incidents(is_lahore);
CREATE INDEX idx_mi_ps           ON minority_incidents(police_station_id);
CREATE INDEX idx_mi_l3           ON minority_incidents(level3_case_nature);
CREATE INDEX idx_mi_community    ON minority_incidents(minority_community);
CREATE INDEX idx_mi_targeted     ON minority_incidents(is_minority_targeted);
CREATE INDEX idx_mi_latlon       ON minority_incidents(lat, long);
