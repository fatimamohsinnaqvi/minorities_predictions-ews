#!/usr/bin/env python3
"""
Build a self-contained Leaflet/Chart.js dashboard for the Minorities
Early-Warning System.

Reads from db_predictive_policing:
  - minority_incidents  (cases + community + level3 + lat/long)
  - minority_predictions (LR + RF scores per case)

Writes:
  outputs/dashboards/dashboard.html   — open directly in a browser,
                                          or serve on port 8767.

Layout:
  Header — totals + model summary
  Left sidebar:
    - Layer toggles (heat / markers / strict / top-N risk)
    - Community filter (A/B/C of communities)
    - Year filter
    - Risk threshold slider (rf_score)
    - "Lahore only" toggle
  Main map (Leaflet + OSM + leaflet.heat + clusters)
  Right sidebar (collapsible):
    - Top-25 PSes by mean rf_score
    - Per-community split
    - Monthly trend (Chart.js)
"""
import json
import os
import re
import sys
from collections import defaultdict


# =====================================================================
# PII redaction — applied to every `description` field before it's
# embedded in the dashboard HTML. This dashboard is for external
# presentation; caller phone numbers, house numbers, and call-center
# meta blocks (SCC name/contact) must NEVER leave this layer.
# =====================================================================

_RE_PHONE = re.compile(
    r"(?:\+?92|0)\s?[\-\s]?\d{2,3}[\-\s]?\d{6,8}"
)
_RE_PLAIN_LONG_DIGITS = re.compile(r"\b\d{7,}\b")           # any 7+ digit run
_RE_CNIC = re.compile(r"\b\d{5}[\-\s]?\d{7}[\-\s]?\d\b")
_RE_HOUSE = re.compile(
    r"\b(?:H(?:ouse)?|مکان)\s*[#\.]?\s*\d+[A-Za-z\-/]?\b",
    re.IGNORECASE,
)
_RE_STREET = re.compile(
    r"\b(?:ST(?:reet)?|str)\s*[#\.]?\s*\d+[A-Za-z\-/]?\b",
    re.IGNORECASE,
)
_RE_SCC_BLOCK = re.compile(
    # Match 'SCC' followed by anything to end-of-text.
    # Covers variants: SCC, SCCD, SCC_, SCC:, SCC>>, SCC___Name, etc.
    r"\s*SCC[\s\S]*",
    re.IGNORECASE,
)
# Also strip lone designation markers that follow redacted phones
_RE_FC_TAIL = re.compile(r"\bFC\b\s*[\.,;:>=_-]?\s*$", re.IGNORECASE)
_RE_FO_TAIL = re.compile(r"\bFO\s*NO\.?\s*:?\s*[\d\s\-]+", re.IGNORECASE)
_RE_CONTACT_LINE = re.compile(
    r"(?:Contact|Mob(?:ile)?|Phone|Tel|Cell)\s*(?:No\.?|#)?\s*[:.]?\s*[+0-9\s\-]+",
    re.IGNORECASE,
)
_RE_NAME_FIELD = re.compile(
    r"\bName\s*:\s*[^\n,;]+",
    re.IGNORECASE,
)
_RE_FATHER_FIELD = re.compile(
    r"\b(?:S\/O|D\/O|Father)\s*:?\s*[^\n,;]+",
    re.IGNORECASE,
)
_RE_WS = re.compile(r"\s+")


def redact_description(text):
    """Strip phone numbers, CNICs, house/street numbers, SCC metadata,
    and 'Name:' / 'Contact No:' patterns from caller-supplied free text.

    Returns a redacted version with [redacted] markers for the bits we
    pulled out, then truncated to a short preview length.
    """
    if not text:
        return ""
    t = str(text)
    # Cut SCC tail first (it's the structured metadata block; everything
    # after the word SCC is usually call-center fields)
    t = _RE_SCC_BLOCK.sub(" [SCC block redacted]", t)
    # Then per-pattern redactions
    t = _RE_CONTACT_LINE.sub("[contact redacted]", t)
    t = _RE_FO_TAIL.sub("", t)
    t = _RE_FATHER_FIELD.sub("[redacted]", t)
    t = _RE_NAME_FIELD.sub("[name redacted]", t)
    t = _RE_CNIC.sub("[CNIC redacted]", t)
    t = _RE_PHONE.sub("[phone redacted]", t)
    t = _RE_PLAIN_LONG_DIGITS.sub("[number redacted]", t)
    t = _RE_HOUSE.sub("[house redacted]", t)
    t = _RE_STREET.sub("[street redacted]", t)
    t = _RE_FC_TAIL.sub("", t)
    # Normalize whitespace
    t = _RE_WS.sub(" ", t).strip()
    # Hard cap preview length
    if len(t) > 160:
        t = t[:157] + "..."
    return t

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
OUT_HTML = os.path.join(PROJECT, 'outputs', 'dashboards', 'dashboard.html')


# Pakistan bounding box (very generous — kept just to drop obvious garbage
# like (0,0), lat/lon swaps, or stray foreign points).
PK_LAT_MIN, PK_LAT_MAX = 23.5, 37.5
PK_LON_MIN, PK_LON_MAX = 60.0, 78.0


def fetch_cases():
    conn = get_db_postgres_predictive()
    cur = conn.cursor()
    cur.execute("""
        SELECT mi.id, mi.incident_date, mi.incident_year,
               mi.district_name, mi.police_station, mi.lat, mi.long,
               mi.is_lahore, mi.minority_community, mi.level3_case_nature,
               mi.is_minority_targeted, mi.match_source,
               COALESCE(mp.rf_score, 0)::float AS rf_score,
               COALESCE(mp.lr_score, 0)::float AS lr_score,
               LEFT(mi.description, 220) AS desc_short
        FROM minority_incidents mi
        LEFT JOIN minority_predictions mp ON mi.id = mp.case_id
        WHERE mi.lat IS NOT NULL AND mi.long IS NOT NULL
    """)
    rows = []
    dropped = 0
    for r in cur.fetchall():
        try:
            lat = float(r[5]); lon = float(r[6])
        except (ValueError, TypeError):
            continue
        if not (PK_LAT_MIN <= lat <= PK_LAT_MAX
                and PK_LON_MIN <= lon <= PK_LON_MAX):
            dropped += 1
            continue
        rows.append({
            'id': r[0],
            'date': str(r[1]) if r[1] else '',
            'yr': r[2] or 0,
            'dist': r[3] or '',
            'ps': r[4] or '',
            'lat': lat, 'lon': lon,
            'lah': bool(r[7]),
            'comm': r[8] or 'unspecified',
            'l3': r[9] or '',
            'tgt': bool(r[10]),
            'src': r[11] or '',
            'rf': float(r[12] or 0),
            'lr': float(r[13] or 0),
            # Description goes through PII redaction before it's ever
            # written into the dashboard HTML. See redact_description().
            'desc': redact_description(r[14]),
        })
    cur.close(); conn.close()
    if dropped:
        print(f'[load] dropped {dropped} cases with coordinates outside Pakistan')
    return rows


def fetch_forward_predictions():
    """The genuine early-warning output: per-PS risk for next 30 days,
    produced by the PS-week forecaster."""
    conn = get_db_postgres_predictive()
    cur = conn.cursor()
    cur.execute("""
        SELECT police_station_id, police_station, district_name, is_lahore,
               ref_date::text, horizon_days, risk_score,
               rank_in_punjab, rank_in_lahore,
               prior_30d_ps_count, prior_30d_district_count,
               days_to_next_major_religious, days_to_next_political,
               misinfo_event_district_14d
        FROM minority_psweek_forward
        ORDER BY risk_score DESC
        LIMIT 50
    """)
    rows = []
    for r in cur.fetchall():
        rows.append({
            'ps_id': r[0], 'ps': r[1], 'dist': r[2], 'lah': bool(r[3]),
            'ref_date': r[4], 'horizon': r[5],
            'score': float(r[6]),
            'rank_p': r[7], 'rank_l': r[8],
            'p30': r[9], 'd30': r[10],
            'd2_rel': r[11], 'd2_pol': r[12],
            'misinfo': bool(r[13]),
        })
    cur.close(); conn.close()
    return rows


def ps_centroid(cases):
    """For each PS, compute the mean lat/lon of its past cases — used
    to fly to a PS when the user clicks on a forward-list row."""
    bag = {}
    for r in cases:
        k = (r['dist'], r['ps'])
        if k not in bag: bag[k] = {'lats': [], 'lons': []}
        bag[k]['lats'].append(r['lat'])
        bag[k]['lons'].append(r['lon'])
    out = {}
    for k, v in bag.items():
        out[k[0] + '||' + k[1]] = {
            'lat': sum(v['lats']) / len(v['lats']),
            'lon': sum(v['lons']) / len(v['lons']),
        }
    return out


def per_ps_summary(rows):
    """Aggregate by (district, police_station) → mean rf, n, n_strict."""
    bag = defaultdict(lambda: {'n': 0, 'n_strict': 0, 'rf_sum': 0.0,
                                 'comm_count': defaultdict(int)})
    for r in rows:
        key = (r['dist'], r['ps'])
        b = bag[key]
        b['n'] += 1
        b['n_strict'] += int(r['tgt'])
        b['rf_sum'] += r['rf']
        b['comm_count'][r['comm']] += 1
    out = []
    for (d, p), b in bag.items():
        if b['n'] < 2:
            continue
        out.append({
            'd': d, 'p': p,
            'n': b['n'],
            'n_strict': b['n_strict'],
            'mean_rf': round(b['rf_sum'] / b['n'], 4),
            'top_comm': max(b['comm_count'].items(), key=lambda x: x[1])[0],
        })
    out.sort(key=lambda x: -x['mean_rf'])
    return out[:25]


def monthly_trend(rows):
    """Per-month totals + strict counts."""
    bag = defaultdict(lambda: {'all': 0, 'strict': 0})
    for r in rows:
        if not r['date']: continue
        ym = r['date'][:7]
        bag[ym]['all'] += 1
        bag[ym]['strict'] += int(r['tgt'])
    months = sorted(bag.keys())
    return {
        'labels': months,
        'all':    [bag[m]['all'] for m in months],
        'strict': [bag[m]['strict'] for m in months],
    }


def main():
    rows = fetch_cases()
    print(f'[load] cases with coords: {len(rows):,}')

    totals = {
        'all': len(rows),
        'lahore': sum(1 for r in rows if r['lah']),
        'strict': sum(1 for r in rows if r['tgt']),
        'comm': dict([(c, 0) for c in ['christian','ahmadi','hindu','sikh',
                                         'multiple','unspecified']]),
    }
    for r in rows:
        totals['comm'][r['comm']] = totals['comm'].get(r['comm'], 0) + 1

    top_ps = per_ps_summary(rows)
    trend = monthly_trend(rows)
    forward = fetch_forward_predictions()
    centroids = ps_centroid(rows)
    # Attach centroids to forward predictions
    for f in forward:
        c = centroids.get(f['dist'] + '||' + f['ps'])
        f['lat'] = c['lat'] if c else None
        f['lon'] = c['lon'] if c else None

    data = {
        'cases': rows,
        'totals': totals,
        'top_ps': top_ps,
        'trend': trend,
        'forward': forward,
        'forward_ref_date': forward[0]['ref_date'] if forward else None,
    }

    html = HTML.replace('__DATA__', json.dumps(data, ensure_ascii=False,
                                                 separators=(',', ':')))
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    sz = os.path.getsize(OUT_HTML) / 1024
    print(f'[OK] wrote {OUT_HTML} ({sz:.0f} KB)')


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Minorities Early-Warning Dashboard — Lahore (Punjab)</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
<style>
  * { box-sizing: border-box; }
  html, body { margin:0; padding:0; height:100%; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; color:#222; }
  #app { display:flex; flex-direction:column; height:100vh; }
  header { background:#1a1a2e; color:#fff; padding:9px 16px; display:flex; align-items:center; gap:18px; flex-wrap:wrap; flex-shrink:0; }
  header h1 { font-size:14px; margin:0; font-weight:600; }
  header .stats { font-size:12px; opacity:0.95; }
  header .stats span { margin-right:12px; }
  header .stats .dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px; vertical-align:middle; }
  #main { display:flex; flex:1; min-height:0; }
  .panel { background:#f5f5f7; border-right:1px solid #ddd; overflow-y:auto; flex-shrink:0; }
  #left { width:280px; }
  #right { width:340px; border-right:none; border-left:1px solid #ddd; }
  .ctrl-block { padding:10px 12px; border-bottom:1px solid #ddd; background:#fff; }
  .ctrl-block:first-child { position:sticky; top:0; z-index:2; }
  .ctrl-block h4 { margin:0 0 6px; font-size:11px; color:#666; text-transform:uppercase; letter-spacing:0.5px; }
  label.toggle { display:block; padding:3px 0; font-size:13px; cursor:pointer; user-select:none; }
  label.toggle .count { color:#777; font-size:11px; margin-left:6px; }
  .sub-toggles { padding-left:18px; margin-top:4px; font-size:12px; }
  .sub-toggles label { display:inline-block; margin-right:8px; cursor:pointer; padding:1px 0; }
  #map { flex:1; }
  input[type=range] { width:100%; }
  #threshold-val { font-family: monospace; font-size:12px; }
  .leaflet-popup-content { font-size:12px; line-height:1.4; max-width:300px; }
  .leaflet-popup-content b { color:#1a1a2e; }
  .leaflet-popup-content .scores { background:#f1f1f1; padding:3px 6px; border-radius:3px; margin-top:4px; font-family:monospace; font-size:11px; }
  #ps-list { list-style:none; margin:0; padding:0; font-size:12px; }
  #ps-list li { padding:7px 12px; border-bottom:1px solid #ececec; }
  #ps-list li .ps-row { display:flex; justify-content:space-between; align-items:center; gap:6px; }
  #ps-list li .name { flex:1; }
  #ps-list li .score { font-family:monospace; color:#c0392b; font-weight:600; }
  #ps-list li .sub { color:#888; font-size:11px; margin-top:1px; }
  .legend { background:#fff; padding:8px 10px; border-radius:4px; box-shadow:0 1px 4px rgba(0,0,0,.2); font-size:11px; line-height:1.4; }
  .legend .row { display:flex; align-items:center; margin-bottom:2px; }
  .legend .sw { display:inline-block; width:12px; height:12px; border-radius:50%; margin-right:6px; border:1px solid #555; }
  .legend .gradient { display:flex; gap:0; height:8px; margin:4px 0; }
  .legend .gradient div { flex:1; }
  .chart-wrap { padding:10px 12px; background:#fff; border-bottom:1px solid #ddd; }
  .chart-wrap h4 { margin:0 0 6px; font-size:11px; color:#666; text-transform:uppercase; letter-spacing:0.5px; }
  .predictions-panel { background:#fff5f3 !important; border-left:4px solid #c0392b; }
  .predictions-panel h4 { font-size:13px !important; text-transform:none !important; letter-spacing:0 !important; }
  .warning-panel { background:#fff8e7 !important; border-left:4px solid #f39c12; }
  .warning-panel h4 { font-size:13px !important; text-transform:none !important; letter-spacing:0 !important; }
  #forward-list { list-style:none; margin:0; padding:0; }
  #forward-list li { padding:9px 12px; border-bottom:1px solid #ececec; cursor:pointer; font-size:12px; }
  #forward-list li:hover { background:#fff8e7; }
  #forward-list li .fw-row { display:flex; justify-content:space-between; align-items:center; }
  #forward-list li .fw-rank { font-family:monospace; color:#1a1a2e; font-weight:700; font-size:11px; min-width:26px; }
  #forward-list li .fw-ps { flex:1; padding-left:6px; }
  #forward-list li .fw-score { background:#f39c12; color:white; font-family:monospace; font-size:11px; padding:1px 6px; border-radius:3px; font-weight:600; }
  #forward-list li .fw-sub { color:#666; font-size:10px; margin-top:2px; padding-left:32px; }
  .pred-kpi { display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:12px; }
  .pred-kpi .box { background:#fff; padding:8px 10px; border-radius:4px; box-shadow:0 1px 3px rgba(0,0,0,0.07); }
  .pred-kpi .box .v { font-size:18px; font-weight:700; color:#c0392b; }
  .pred-kpi .box .l { color:#666; font-size:10px; text-transform:uppercase; }
  #top-cases-list { list-style:none; margin:0; padding:0; }
  #top-cases-list li { padding:8px 12px; border-bottom:1px solid #ececec; cursor:pointer; }
  #top-cases-list li:hover { background:#fff5f3; }
  #top-cases-list li .tc-row { display:flex; justify-content:space-between; align-items:center; gap:6px; }
  #top-cases-list li .rank { font-weight:700; color:#c0392b; font-family:monospace; font-size:11px; }
  #top-cases-list li .ps { flex:1; font-size:12px; }
  #top-cases-list li .score-pill { background:#c0392b; color:white; font-family:monospace; font-size:11px; padding:1px 6px; border-radius:3px; font-weight:600; }
  #top-cases-list li .sub { color:#777; font-size:10px; margin-top:2px; }
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>Minorities Early-Warning Dashboard</h1>
    <div class="stats" id="stats"></div>
  </header>
  <div id="main">
    <aside id="left" class="panel">
      <div class="ctrl-block">
        <h4>Layers</h4>
        <label class="toggle"><input type="checkbox" id="lyr-heat" checked> Heat density</label>
        <label class="toggle" style="padding-left:18px;font-size:11px;color:#666"><input type="checkbox" id="weight-by-risk" checked> Weight heat by model risk (RF)</label>
        <label class="toggle"><input type="checkbox" id="lyr-points"> Incident markers</label>
        <label class="toggle"><input type="checkbox" id="lyr-strict"> Strict-label only (is_minority_targeted)</label>
        <label class="toggle"><input type="checkbox" id="lyr-topn" checked> Top-100 by model risk (RF)</label>
      </div>
      <div class="ctrl-block">
        <h4>Community filter</h4>
        <div class="sub-toggles" id="comm-toggles">
          <label><input type="checkbox" data-c="christian" checked> <span style="color:#3498db">Christian</span></label>
          <label><input type="checkbox" data-c="ahmadi" checked> <span style="color:#e67e22">Ahmadi</span></label>
          <label><input type="checkbox" data-c="hindu" checked> <span style="color:#9b59b6">Hindu</span></label>
          <label><input type="checkbox" data-c="sikh" checked> <span style="color:#16a085">Sikh</span></label>
          <label><input type="checkbox" data-c="multiple" checked> <span style="color:#f1c40f">Multiple</span></label>
          <label><input type="checkbox" data-c="unspecified" checked> <span style="color:#7f8c8d">Unspecified</span></label>
        </div>
      </div>
      <div class="ctrl-block">
        <h4>Year</h4>
        <div class="sub-toggles" id="year-toggles">
          <label><input type="checkbox" data-y="2024" checked> 2024</label>
          <label><input type="checkbox" data-y="2025" checked> 2025</label>
          <label><input type="checkbox" data-y="2026" checked> 2026 YTD</label>
        </div>
      </div>
      <div class="ctrl-block">
        <h4>Risk-score threshold (RF)</h4>
        <div style="font-size:11px;color:#666;margin-bottom:4px">Show only cases with rf_score ≥ <span id="threshold-val">0.00</span></div>
        <input type="range" id="threshold" min="0" max="1" step="0.01" value="0">
      </div>
      <div class="ctrl-block">
        <h4>Scope</h4>
        <label class="toggle"><input type="checkbox" id="lahore-only"> Lahore only</label>
      </div>
      <div class="ctrl-block">
        <h4>Privacy</h4>
        <label class="toggle"><input type="checkbox" id="show-desc"> Show incident description text</label>
        <p style="font-size:10px;color:#888;margin:4px 0 0">
          Hidden by default for external presentations. When shown, caller phone numbers,
          addresses, and named individuals have been auto-redacted but residual names
          in free text may remain.
        </p>
      </div>
    </aside>

    <div id="map"></div>

    <aside id="right" class="panel">

      <!-- FORWARD EARLY-WARNING PANEL — the real forecast -->
      <div class="ctrl-block warning-panel">
        <h4 style="color:#1a1a2e;font-weight:700">🔮 Early Warning — Next 30 Days</h4>
        <div style="font-size:11px;color:#555;margin-bottom:6px">
          PS-week LR forecaster · ROC AUC 0.72 · trained on 2024-2025
        </div>
        <div id="forward-meta" style="font-size:11px;color:#666;margin-bottom:8px"></div>
      </div>

      <div class="ctrl-block">
        <h4 style="color:#1a1a2e">Top-15 PSes for next 30 days <span style="font-weight:400;color:#888">(click to fly)</span></h4>
      </div>
      <ul id="forward-list"></ul>

      <!-- PER-CASE TRIAGE PANEL -->
      <div class="ctrl-block predictions-panel" style="margin-top:6px">
        <h4 style="color:#c0392b;font-weight:700">⚡ Per-case triage (retrospective)</h4>
        <div style="font-size:11px;color:#555;margin-bottom:8px">
          Random Forest (trained 2024–2025) · ROC AUC 0.81 · Precision@20 0.35
        </div>
        <div id="pred-kpis"></div>
      </div>

      <div class="ctrl-block">
        <h4 style="color:#c0392b">Top-10 highest-risk cases <span style="font-weight:400;color:#888">(click to zoom)</span></h4>
      </div>
      <ul id="top-cases-list"></ul>

      <div class="ctrl-block" style="margin-top:6px">
        <h4>Top-25 PSes by mean RF score</h4>
        <p style="font-size:11px;color:#666;margin:0">Where the model flags the most risk on average. Operational input for force allocation.</p>
      </div>
      <ul id="ps-list"></ul>
      <div class="chart-wrap">
        <h4>Cases per month — strict vs all</h4>
        <canvas id="trend-chart" height="180"></canvas>
      </div>
      <div class="chart-wrap">
        <h4>By community</h4>
        <canvas id="comm-chart" height="180"></canvas>
      </div>
    </aside>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
const DATA = __DATA__;
const COMM_COLOR = {christian:'#3498db', ahmadi:'#e67e22', hindu:'#9b59b6', sikh:'#16a085', multiple:'#f1c40f', unspecified:'#7f8c8d'};

// Compute the headline RF stat
const N_FLAGGED = DATA.cases.filter(r => r.rf >= 0.5).length;
const PCT_FLAGGED = ((N_FLAGGED / DATA.totals.all) * 100).toFixed(1);
const MAX_RF = Math.max(...DATA.cases.map(r => r.rf));

document.getElementById('stats').innerHTML =
  `<span><b>${DATA.totals.all.toLocaleString()}</b> cases (with coords)</span>` +
  `<span><b>${DATA.totals.lahore.toLocaleString()}</b> Lahore</span>` +
  `<span><b>${DATA.totals.strict.toLocaleString()}</b> strict-label</span>` +
  `<span style="background:#c0392b;padding:2px 8px;border-radius:3px;font-weight:600">` +
  `RF flagged (≥0.5): <b>${N_FLAGGED}</b> (${PCT_FLAGGED}%)</span>` +
  Object.entries(DATA.totals.comm)
    .filter(([k,v])=>v>0)
    .map(([k,v])=>`<span><span class="dot" style="background:${COMM_COLOR[k]||'#888'}"></span>${k}: ${v}</span>`).join('');

// State — predictions are the default focus
let active = {
  heat: true, weightByRisk: true,
  points: false, strict: false, topN: true,
  comms: new Set(['christian','ahmadi','hindu','sikh','multiple','unspecified']),
  years: new Set([2024,2025,2026]),
  threshold: 0,
  lahoreOnly: false,
  showDesc: false,    // privacy: description text hidden by default
};

function filtered() {
  return DATA.cases.filter(r =>
    active.comms.has(r.comm)
    && active.years.has(r.yr)
    && r.rf >= active.threshold
    && (!active.lahoreOnly || r.lah)
  );
}

// Hardcoded bboxes — robust against bad incident coordinates and give a
// consistent initial view regardless of data state. The project's
// geographic focus is Lahore; the broader view is Pakistan.
const LAHORE_BBOX  = [[31.30, 73.95], [31.72, 74.60]];   // metro Lahore
const PUNJAB_BBOX  = [[27.50, 69.00], [34.10, 76.00]];   // Punjab province
const PAKISTAN_BBOX = [[23.50, 60.00], [37.50, 78.00]];  // safety ceiling

const map = L.map('map', {
  preferCanvas: true,
  maxBounds: PAKISTAN_BBOX,     // don't let the user pan to Algeria, etc.
  maxBoundsViscosity: 0.6,
  minZoom: 5,
}).fitBounds(LAHORE_BBOX);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom:19, attribution:'&copy; OpenStreetMap'}).addTo(map);

let heatLayer = null;
const cluster = L.markerClusterGroup({showCoverageOnHover:false, maxClusterRadius:45, disableClusteringAtZoom:15});
const strictLayer = L.layerGroup();
const topNLayer = L.layerGroup();

function buildHeat(rows){
  if(heatLayer) map.removeLayer(heatLayer);
  // When weightByRisk is ON, the heat layer is genuinely a MODEL RISK
  // surface — only cases with rf_score >= 0.1 contribute, and their
  // contribution scales with the score.
  let pts;
  if(active.weightByRisk) {
    pts = rows.filter(r => r.rf >= 0.1)
              .map(r => [r.lat, r.lon, r.rf]);
  } else {
    pts = rows.map(r => [r.lat, r.lon, 0.5]);
  }
  heatLayer = L.heatLayer(pts, {
    radius:28, blur:30, maxZoom:15, max: 1.0,
    gradient:{0.15:'#fee5d9', 0.35:'#fcae91', 0.55:'#fb6a4a', 0.75:'#de2d26', 1.0:'#a50f15'},
    minOpacity: 0.45,
  });
  if(active.heat) map.addLayer(heatLayer);
}

function popupHtml(r){
  // Privacy: description shown only when user explicitly toggles it on
  let descBlock = '';
  if (active.showDesc && r.desc) {
    descBlock = `<div style="color:#555;margin-top:4px;font-style:italic;font-size:11px">${r.desc}</div>`
      + `<div style="color:#aaa;font-size:9px;margin-top:2px">— phone, address, contact, and SCC fields auto-redacted</div>`;
  } else if (!active.showDesc && r.desc) {
    descBlock = `<div style="color:#aaa;font-size:10px;margin-top:4px;font-style:italic">[Description hidden — enable in left sidebar for redacted text]</div>`;
  }
  return `<b>${r.l3 || '(no category)'}</b><br><small>${r.date} · ${r.dist} · PS ${r.ps}</small>`+
    `<div style="margin-top:4px"><b>Community:</b> ${r.comm}` +
    (r.tgt ? ' <span style="color:#c0392b;font-weight:600">[strict-targeted]</span>' : '') + '</div>' +
    `<div class="scores">RF: ${r.rf.toFixed(3)} &nbsp; LR: ${r.lr.toFixed(3)}</div>` +
    descBlock;
}

// Haversine in metres
function havM(la1, lo1, la2, lo2){
  const R = 6371000.0;
  const a1 = la1 * Math.PI / 180, a2 = la2 * Math.PI / 180;
  const dp = (la2 - la1) * Math.PI / 180;
  const dl = (lo2 - lo1) * Math.PI / 180;
  const h = Math.sin(dp/2)**2 + Math.cos(a1)*Math.cos(a2)*Math.sin(dl/2)**2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

// Click-anywhere handler — find nearest case(s) within 200m and show them
function nearbyCasesPopup(e){
  const RADIUS_M = 250;
  const lat = e.latlng.lat, lon = e.latlng.lng;
  const visible = filtered();
  const nearby = visible
    .map(c => ({...c, _d: havM(lat, lon, c.lat, c.lon)}))
    .filter(c => c._d <= RADIUS_M)
    .sort((a, b) => b.rf - a.rf);
  if(!nearby.length){
    L.popup({maxWidth: 280})
      .setLatLng(e.latlng)
      .setContent(`<div style="color:#666"><b>No cases within ${RADIUS_M}m</b><br><small>Lat ${lat.toFixed(5)}, Lon ${lon.toFixed(5)}</small></div>`)
      .openOn(map);
    return;
  }
  if(nearby.length === 1){
    L.popup({maxWidth: 320})
      .setLatLng([nearby[0].lat, nearby[0].lon])
      .setContent(popupHtml(nearby[0]))
      .openOn(map);
    return;
  }
  const top = nearby.slice(0, 5);
  const html =
    `<b>${nearby.length} cases within ${RADIUS_M}m</b>` +
    `<div style="font-size:11px;color:#666;margin-top:2px">Sorted by RF risk · showing top ${top.length}</div>` +
    top.map((r, i) =>
      `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #ddd"><b style="color:#c0392b">#${i+1} · ${r._d.toFixed(0)}m away</b><br>` +
      popupHtml(r) + `</div>`).join('');
  L.popup({maxWidth: 360})
    .setLatLng(e.latlng)
    .setContent(html)
    .openOn(map);
}

map.on('click', nearbyCasesPopup);

function buildMarkers(rows){
  cluster.clearLayers();
  rows.forEach(r => {
    const color = COMM_COLOR[r.comm] || '#888';
    const m = L.circleMarker([r.lat,r.lon], {
      radius:5, fillColor:color, color:'#222', weight:0.6, opacity:0.9, fillOpacity:0.85});
    m.bindPopup(popupHtml(r));
    cluster.addLayer(m);
  });
}

function buildStrict(rows){
  strictLayer.clearLayers();
  rows.filter(r => r.tgt).forEach(r => {
    const m = L.circleMarker([r.lat,r.lon], {
      radius:7, fillColor:'transparent', color:'#c0392b', weight:2, opacity:0.95});
    m.bindPopup(popupHtml(r));
    strictLayer.addLayer(m);
  });
}

function buildTopN(rows){
  topNLayer.clearLayers();
  const sorted = [...rows].sort((a,b)=>b.rf-a.rf).slice(0,100);
  sorted.forEach((r,i) => {
    const m = L.circleMarker([r.lat,r.lon], {
      radius: 9-Math.floor(i/15), fillColor:'#c0392b', color:'#000', weight:1.2, opacity:1, fillOpacity:0.9});
    m.bindPopup(`<b>Rank #${i+1} by RF score</b><br>` + popupHtml(r));
    topNLayer.addLayer(m);
  });
}

function refreshLayers(){
  const rows = filtered();
  buildHeat(rows);
  buildMarkers(rows);
  buildStrict(rows);
  buildTopN(rows);
  if(active.heat) map.addLayer(heatLayer); else map.removeLayer(heatLayer);
  if(active.points) map.addLayer(cluster); else map.removeLayer(cluster);
  if(active.strict) map.addLayer(strictLayer); else map.removeLayer(strictLayer);
  if(active.topN) map.addLayer(topNLayer); else map.removeLayer(topNLayer);
  populateForwardPanel();
  updatePredictionsPanel(rows);
  updateTopCasesList(rows);
  updateRightPanel(rows);
}

// Forward-prediction panel — actual early warning (top of right sidebar)
function populateForwardPanel(){
  const fwd = DATA.forward || [];
  document.getElementById('forward-meta').innerHTML =
    fwd.length
      ? `Predicting for week of <b>${DATA.forward_ref_date}</b>, horizon 30 days · ` +
        `<b>${fwd.length}</b> PSes scored`
      : '<i>(no forward predictions available)</i>';

  const ul = document.getElementById('forward-list');
  const showLahoreOnly = active.lahoreOnly;
  const items = showLahoreOnly ? fwd.filter(f => f.lah) : fwd;
  ul.innerHTML = items.slice(0, 15).map((f, i) => {
    const reasons = [];
    if(f.p30 > 0) reasons.push(`prior 30d: ${f.p30} cases`);
    if(f.d2_rel !== null && f.d2_rel <= 14) reasons.push(`major religious event in ${f.d2_rel}d`);
    if(f.d2_pol !== null && f.d2_pol <= 14) reasons.push(`political event in ${f.d2_pol}d`);
    if(f.misinfo) reasons.push('recent misinfo event in district');
    const why = reasons.length ? reasons.join(' · ') : 'context-only signal';
    return `<li data-lat="${f.lat||''}" data-lon="${f.lon||''}">
      <div class="fw-row">
        <span class="fw-rank">#${i+1}</span>
        <span class="fw-ps"><b>${f.ps || '(no PS)'}</b><br><span style="color:#888">${f.dist}</span></span>
        <span class="fw-score">${f.score.toFixed(2)}</span>
      </div>
      <div class="fw-sub">${why}</div>
    </li>`;
  }).join('');
  ul.querySelectorAll('li').forEach(li => {
    li.addEventListener('click', () => {
      const la = parseFloat(li.dataset.lat), lo = parseFloat(li.dataset.lon);
      if(!isNaN(la) && !isNaN(lo)) map.flyTo([la, lo], 15, { duration: 0.6 });
    });
  });
}

// Prominent model-predictions KPI box (top of right sidebar)
function updatePredictionsPanel(rows){
  const n_total = rows.length;
  const n_flag05 = rows.filter(r => r.rf >= 0.5).length;
  const n_flag03 = rows.filter(r => r.rf >= 0.3).length;
  const n_strict = rows.filter(r => r.tgt).length;
  const max_rf = n_total ? Math.max(...rows.map(r => r.rf)) : 0;
  document.getElementById('pred-kpis').innerHTML =
    '<div class="pred-kpi">' +
      `<div class="box"><div class="v">${n_flag05}</div><div class="l">flagged ≥0.5</div></div>` +
      `<div class="box"><div class="v">${n_flag03}</div><div class="l">flagged ≥0.3</div></div>` +
      `<div class="box"><div class="v">${n_strict}</div><div class="l">strict-targeted (truth)</div></div>` +
      `<div class="box"><div class="v">${max_rf.toFixed(2)}</div><div class="l">max RF score</div></div>` +
    '</div>';
}

// Top-10 highest-risk cases list (clickable to zoom)
function updateTopCasesList(rows){
  const ul = document.getElementById('top-cases-list');
  const top10 = [...rows].sort((a,b)=>b.rf-a.rf).slice(0,10);
  ul.innerHTML = top10.map((r,i) => {
    const tgt = r.tgt ? ' <span style="color:#c0392b;font-weight:600">★</span>' : '';
    const col = COMM_COLOR[r.comm] || '#888';
    return `<li data-lat="${r.lat}" data-lon="${r.lon}" data-id="${r.id}">
      <div class="tc-row">
        <span class="rank">#${i+1}</span>
        <span class="ps">${r.ps || '(no PS)'}${tgt}</span>
        <span class="score-pill">${r.rf.toFixed(2)}</span>
      </div>
      <div class="sub">${r.date} · ${r.dist} · <span style="color:${col};font-weight:600">${r.comm}</span> · ${r.l3 ? r.l3.substring(0,50) : '(no category)'}</div>
    </li>`;
  }).join('');
  // Click → fly to case
  ul.querySelectorAll('li').forEach(li => {
    li.addEventListener('click', () => {
      const la = parseFloat(li.dataset.lat), lo = parseFloat(li.dataset.lon);
      map.flyTo([la, lo], 16, { duration: 0.6 });
    });
  });
}

// Top-25 PSes panel — recomputed from current filtered set
function updateRightPanel(rows){
  const bag = {};
  rows.forEach(r => {
    const k = r.dist + '||' + r.ps;
    if(!bag[k]) bag[k] = {d:r.dist, p:r.ps, n:0, strict:0, rfsum:0, comm:{}};
    bag[k].n += 1;
    bag[k].strict += r.tgt ? 1 : 0;
    bag[k].rfsum += r.rf;
    bag[k].comm[r.comm] = (bag[k].comm[r.comm]||0) + 1;
  });
  const list = Object.values(bag)
    .filter(b => b.n >= 2)
    .map(b => {
      const top = Object.entries(b.comm).sort((a,b)=>b[1]-a[1])[0];
      return {...b, mean_rf: b.rfsum / b.n, top_comm: top ? top[0] : '?'};
    })
    .sort((a,b)=>b.mean_rf-a.mean_rf)
    .slice(0,25);
  const ul = document.getElementById('ps-list');
  ul.innerHTML = list.map((b,i) => {
    const col = COMM_COLOR[b.top_comm] || '#888';
    return `<li><div class="ps-row"><span class="name"><b>${i+1}.</b> ${b.p}</span><span class="score">${b.mean_rf.toFixed(3)}</span></div>` +
           `<div class="sub">${b.d} · ${b.n} cases · ${b.strict} strict · top-comm: <span style="color:${col};font-weight:600">${b.top_comm}</span></div></li>`;
  }).join('');

  // Update community chart
  const commCounts = {};
  rows.forEach(r => { commCounts[r.comm] = (commCounts[r.comm]||0)+1; });
  const labels = Object.keys(commCounts).sort();
  commChart.data.labels = labels;
  commChart.data.datasets[0].data = labels.map(l => commCounts[l]);
  commChart.data.datasets[0].backgroundColor = labels.map(l => COMM_COLOR[l] || '#888');
  commChart.update();
}

document.getElementById('lyr-heat').addEventListener('change', e=>{active.heat=e.target.checked; refreshLayers();});
document.getElementById('weight-by-risk').addEventListener('change', e=>{active.weightByRisk=e.target.checked; refreshLayers();});
document.getElementById('lyr-points').addEventListener('change', e=>{active.points=e.target.checked; refreshLayers();});
document.getElementById('lyr-strict').addEventListener('change', e=>{active.strict=e.target.checked; refreshLayers();});
document.getElementById('lyr-topn').addEventListener('change', e=>{active.topN=e.target.checked; refreshLayers();});

document.querySelectorAll('#comm-toggles input').forEach(cb => cb.addEventListener('change', ()=>{
  active.comms = new Set([...document.querySelectorAll('#comm-toggles input:checked')].map(c=>c.dataset.c));
  refreshLayers();
}));

document.querySelectorAll('#year-toggles input').forEach(cb => cb.addEventListener('change', ()=>{
  active.years = new Set([...document.querySelectorAll('#year-toggles input:checked')].map(c=>parseInt(c.dataset.y)));
  refreshLayers();
}));

document.getElementById('threshold').addEventListener('input', e=>{
  active.threshold = parseFloat(e.target.value);
  document.getElementById('threshold-val').textContent = active.threshold.toFixed(2);
  refreshLayers();
});

document.getElementById('show-desc').addEventListener('change', e=>{
  active.showDesc = e.target.checked;
  // Popups are rebuilt on next click; nothing else to do
});
document.getElementById('lahore-only').addEventListener('change', e=>{
  active.lahoreOnly = e.target.checked;
  refreshLayers();
  // Couple zoom to the user's filter intent — fit map to Lahore when
  // they enable the filter, full-Punjab when they disable it.
  if(active.lahoreOnly) {
    map.flyToBounds(LAHORE_BBOX, { padding: [40, 40], duration: 0.6 });
  } else {
    map.flyToBounds(PUNJAB_BBOX, { padding: [30, 30], duration: 0.6 });
  }
});

// Trend chart (Chart.js) — always shows the unfiltered series (context)
const trendCtx = document.getElementById('trend-chart');
new Chart(trendCtx, {
  type: 'line',
  data: {
    labels: DATA.trend.labels,
    datasets: [
      {label:'All', data: DATA.trend.all, borderColor:'#34495e', backgroundColor:'rgba(52,73,94,0.1)', tension:0.25, fill:true, pointRadius:2},
      {label:'Strict-label', data: DATA.trend.strict, borderColor:'#c0392b', backgroundColor:'rgba(192,57,43,0.1)', tension:0.25, fill:true, pointRadius:2},
    ]
  },
  options: {
    responsive:true, maintainAspectRatio:false,
    plugins:{legend:{position:'bottom', labels:{font:{size:10}}}},
    scales:{ x:{ticks:{maxRotation:45, minRotation:45, font:{size:9}}}, y:{beginAtZero:true} }
  }
});

// Community chart (reactive)
const commCtx = document.getElementById('comm-chart');
const commChart = new Chart(commCtx, {
  type:'bar',
  data: {labels: [], datasets:[{label:'cases', data:[], backgroundColor: []}]},
  options: {
    responsive:true, maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{ x:{ticks:{font:{size:10}}}, y:{beginAtZero:true} }
  }
});

// Legend
const legend = L.control({position:'bottomright'});
legend.onAdd = function(){
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML =
    '<div><b>Heat density (low → high)</b></div>' +
    '<div class="gradient"><div style="background:#fee5d9"></div><div style="background:#fcae91"></div><div style="background:#fb6a4a"></div><div style="background:#de2d26"></div><div style="background:#a50f15"></div></div>' +
    '<div style="margin-top:6px"><b>Community</b></div>' +
    Object.entries(COMM_COLOR).map(([k,c])=>`<div class="row"><span class="sw" style="background:${c}"></span>${k}</div>`).join('') +
    '<div style="margin-top:6px"><b>Special</b></div>' +
    '<div class="row"><span class="sw" style="background:transparent;border:2px solid #c0392b"></span>Strict-label</div>' +
    '<div class="row"><span class="sw" style="background:#c0392b"></span>Top-100 by RF risk</div>';
  return div;
};
legend.addTo(map);

refreshLayers();
</script>
</body>
</html>
"""


if __name__ == '__main__':
    main()
