#!/usr/bin/env python3
"""
Build the `minority_incidents` working table for the project.

Reads from:  test_1124.response_time
Writes to:   db_predictive_policing.minority_incidents

Filter:
  level2_case_nature = 'Religious Offences'  OR
  description matches a minority keyword (case-insensitive)

For each row we also compute:
  - match_source       'religious_offence' / 'desc_keyword' / 'both'
  - matched_keywords   TEXT[] of which keywords hit in description
  - minority_community 'christian' / 'ahmadi' / 'hindu' / 'sikh' /
                       'multiple' / 'unspecified'
  - is_minority_targeted (strict label)
  - is_lahore
"""
import os
import re
import sys
from datetime import datetime, date


def _parse_date(s):
    """Source `response_time.date` is TEXT, common formats vary."""
    if s is None or s == '':
        return None
    if isinstance(s, (datetime, date)):
        return s if isinstance(s, date) else s.date()
    s = str(s).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_ts(s):
    """Source `response_time.accepted_time` is TEXT."""
    if s is None or s == '':
        return None
    if isinstance(s, datetime):
        return s
    s = str(s).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_1124, get_db_postgres_predictive  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, 'schema.sql')

# Each pattern → minority community label (regex, case-insensitive).
COMMUNITY_PATTERNS = [
    ('christian', re.compile(r'\b(christian|christians|church|churches|pastor|chrch|masihi|maseehi)\b', re.I)),
    ('ahmadi',    re.compile(r'\b(ahmadi|ahmedi|qadiani|qadiyani|qadian)\b', re.I)),
    ('hindu',     re.compile(r'\b(hindu|hindus|mandir|mundir|temple)\b', re.I)),
    ('sikh',      re.compile(r'\b(sikh|sikhs|gurdwara|gurudwara)\b', re.I)),
]
BLASPHEM_RE = re.compile(r'\b(blasphem|gustakh|tauhin)\w*\b', re.I)

# Single combined regex used by the SQL WHERE — kept in sync with above
SQL_KEYWORD_PATTERN = (
    r'(christian|ahmadi|hindu|sikh|qadia|church|gurdwara|temple|pastor|blasphem)'
)


def detect_community(desc):
    """Return ('community', [matched_keywords_lower]) for a description."""
    if not desc:
        return ('unspecified', [])
    hits = set()
    matched_keywords = []
    for label, pat in COMMUNITY_PATTERNS:
        m = pat.findall(desc)
        if m:
            hits.add(label)
            matched_keywords.extend(w.lower() for w in m)
    if BLASPHEM_RE.search(desc):
        matched_keywords.extend(['blasphemy'])
    if len(hits) == 0:
        return ('unspecified', matched_keywords)
    if len(hits) == 1:
        return (next(iter(hits)), matched_keywords)
    return ('multiple', matched_keywords)


def main():
    # --- read all candidate rows from source ---
    src = get_db_postgres_1124()
    cur = src.cursor()
    sql = f"""
    SELECT
        case_number, lead_id,
        date, accepted_time,
        district_id::text, police_station_id::text, police_station,
        lat, long,
        level1_case_nature, level2_case_nature, level3_case_nature,
        description
    FROM response_time
    WHERE level2_case_nature = 'Religious Offences'
       OR LOWER(description) ~ '{SQL_KEYWORD_PATTERN}'
    """
    print('[src] querying response_time …')
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close(); src.close()
    print(f'[src] candidate rows: {len(rows):,}')

    # --- get district_name lookup from predictive DB ---
    pre = get_db_postgres_predictive()
    pcur = pre.cursor()
    pcur.execute("""SELECT DISTINCT district_id::text, district_name
                    FROM police_station_boundaries_v2
                    WHERE district_name IS NOT NULL""")
    DID2NAME = {did: dn for did, dn in pcur.fetchall()}
    print(f'[lookup] district_id → name map: {len(DID2NAME)} entries')
    pcur.close()

    # --- (re)create destination table ---
    cur = pre.cursor()
    with open(SCHEMA_PATH) as f:
        cur.execute(f.read())
    pre.commit()
    print('[ddl] minority_incidents (re)created in db_predictive_policing')

    # --- transform + insert ---
    INSERT_SQL = """
    INSERT INTO minority_incidents (
        case_number, lead_id,
        incident_date, accepted_time, incident_year, incident_month,
        district_id, district_name, police_station_id, police_station,
        lat, long, is_lahore,
        level1_case_nature, level2_case_nature, level3_case_nature,
        description, match_source, matched_keywords,
        minority_community, is_minority_targeted, loaded_at
    ) VALUES (
        %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s
    )
    """

    inserted = 0
    desc_match_re = re.compile(SQL_KEYWORD_PATTERN, re.I)
    now = datetime.utcnow()

    stats_match = {'religious_offence': 0, 'desc_keyword': 0, 'both': 0}
    stats_community = {}
    stats_targeted = 0
    stats_lahore = 0

    for (case_no, lead_id, dt, atime, did, ps_id, ps,
         lat, lon, l1, l2, l3, desc) in rows:
        # Decide match source
        is_relig = (l2 == 'Religious Offences')
        is_kw = bool(desc and desc_match_re.search(desc))
        if is_relig and is_kw:
            ms = 'both'
        elif is_relig:
            ms = 'religious_offence'
        else:
            ms = 'desc_keyword'
        stats_match[ms] += 1

        # Community + keywords (only meaningful when desc has minority terms)
        community, kws = detect_community(desc)
        stats_community[community] = stats_community.get(community, 0) + 1

        is_lahore = (str(did) == '40')
        if is_lahore:
            stats_lahore += 1

        # Strict label: tagged religious AND mentions a specific minority community
        is_targeted = is_relig and (community in ('christian', 'ahmadi', 'hindu', 'sikh', 'multiple'))
        if is_targeted:
            stats_targeted += 1

        # Date parsing (source columns are TEXT)
        inc_date = _parse_date(dt)
        atime_parsed = _parse_ts(atime)
        yr = inc_date.year if inc_date else None
        mo = inc_date.month if inc_date else None

        try:
            lat_f = float(lat) if lat is not None else None
            lon_f = float(lon) if lon is not None else None
        except (ValueError, TypeError):
            lat_f = None; lon_f = None

        cur.execute(INSERT_SQL, (
            case_no, lead_id,
            inc_date, atime_parsed, yr, mo,
            did, DID2NAME.get(str(did)), ps_id, ps,
            lat_f, lon_f, is_lahore,
            l1, l2, l3,
            desc, ms, kws if kws else None,
            community, is_targeted, now,
        ))
        inserted += 1
        if inserted % 1000 == 0:
            pre.commit()

    pre.commit()

    print(f'\n[OK] inserted {inserted:,} rows into minority_incidents\n')
    print('Match source:')
    for k, v in stats_match.items():
        print(f'  {k:<18} {v:,}')
    print(f'\nMinority community distribution:')
    for k, v in sorted(stats_community.items(), key=lambda x: -x[1]):
        print(f'  {k:<14} {v:,}')
    print(f'\nis_minority_targeted (strict): {stats_targeted:,}')
    print(f'is_lahore:                    {stats_lahore:,}')

    cur.close(); pre.close()


if __name__ == '__main__':
    main()
