# 05 — Dashboard Design

**Phase:** W9–10
**Status:** ✅ Shipped — self-contained HTML with Leaflet + Chart.js (Streamlit not used; venv proxy-blocked from pip)
**Last updated:** 2026-06-23

---

## Shipped artifact

| Field | Value |
|---|---|
| File | [`outputs/dashboards/dashboard.html`](../outputs/dashboards/dashboard.html) |
| Size | 1.3 MB (all data embedded inline) |
| Local URL | http://localhost:8767/dashboard.html |
| Generator | [`src/viz/dashboard.py`](../src/viz/dashboard.py) |
| Reads from | `minority_incidents` + `minority_predictions` |

### Why we deviated from Streamlit

The methodology originally specified Streamlit. The dev box's Python
environment doesn't have Streamlit installed and the network proxy
blocks `pip install`. Instead we used the **same self-contained
Leaflet HTML pattern** already established in this repo for the imam-
bargah dashboard (`imam_bargahs_data/development/dashboard.html`) and
the Muharram 2026 dashboard (`muharram_2026/dashboard.html`) — a single
HTML file that embeds the data and loads Leaflet + Chart.js from CDN.

The trade-off: no live Python backend, but the dashboard works offline
once loaded, runs in any browser, and stays consistent with the rest of
the project's deliverables.

## What's actually in the dashboard

### Header

- Total cases mapped: **3,281**
- Lahore subset
- Strict-label minority-targeted count
- Per-community breakdown with color dots

### Left sidebar — Filters and layer toggles

- **Layer toggles** (4): Heat density, Incident markers (clustered),
  Strict-label-only overlay (red rings), Top-100 by RF model score
- **Community filter** — checkboxes for the 6 communities
- **Year filter** — 2024 / 2025 / 2026 YTD
- **Risk threshold slider** — show only cases with `rf_score ≥ X` (0–1)
- **"Lahore only" toggle**

### Map (center)

- OSM tile base
- Leaflet + leaflet.heat + leaflet.markercluster
- Markers colored by community
- Popup on click: level3 / date / district / PS / community / RF + LR
  scores / description preview / "strict-targeted" badge

### Right sidebar — Operational panel

- **Top-25 PSes by mean RF score** — dynamically recomputed every time
  the filter set changes. Each row shows:
  - Rank, PS name, mean RF score
  - District, total cases in filter, strict count, top-community
- **Monthly trend chart** (Chart.js line plot) — all cases vs strict-label
- **Community split bar chart** — reactive to current filter

## How to (re)build and serve

```bash
# 1. Make sure models and predictions exist:
python3 minorities/minorities_project/src/models/predict_batch.py

# 2. Build the dashboard HTML:
python3 minorities/minorities_project/src/viz/dashboard.py

# 3. Serve it locally:
cd minorities/minorities_project/outputs/dashboards
python3 -m http.server 8767 --bind 0.0.0.0

# 4. Open http://localhost:8767/dashboard.html
```

---

---

## Goal

A self-service interactive dashboard for the supervisor, PSCA leadership,
and policy stakeholders. It must explain *what is happening*, *where*,
*for which community*, and *what the model predicts next* — without the
viewer needing to query the database.

## Audience and use cases

| Audience | Use case |
|---|---|
| PSCA shift commander | "What's the risk in my division this week? Are any PSes at red?" |
| Policy analyst | "How has minority-targeted crime moved in 2025 vs 2024? Where is it growing?" |
| Internship supervisor | "Show me the artifact." |
| Minority community representatives (if shared) | "Is my community visible in your data, and how?" |

## Stack

| Layer | Choice | Rationale |
|---|---|---|
| Map | **Leaflet + OSM tiles** | Already used elsewhere in the cpis-backend project — consistent UX with the imam-bargah / Muharram dashboards |
| Heat layer | `leaflet.heat` | Lightweight, browser-side, no Python folium needed |
| Clustering | `leaflet.markercluster` | Required when 4,000+ markers compete for the same view |
| Dashboard shell | **Streamlit** | Per the Timeline PDF; easy to deploy locally, low maintenance |
| Charts | Plotly inside Streamlit | Interactive tooltips, no Streamlit-charts limitations |
| Backend | Direct SQL against `db_predictive_policing` | No intermediate API layer needed for v1 |

## Layout

```
┌─────────────────────────────────────────────────────┐
│ Header: 4,110 incidents · 928 Lahore · 312 strict  │
├─────────────────────────────────────────────────────┤
│  Sidebar         │            MAP                   │
│  Filters         │   (heat / pins / strict only)    │
│  - Year          │                                  │
│  - District      │                                  │
│  - Community     │                                  │
│  - Severity      │                                  │
│  - Strict label  │                                  │
│  - Date range    │                                  │
│                  │                                  │
│  Layer toggles   │                                  │
│  - heat          │                                  │
│  - incidents     │                                  │
│  - predictions   │                                  │
└─────────────────────────────────────────────────────┘
│  KPI row: monthly trend, top PSes, community share  │
├─────────────────────────────────────────────────────┤
│  Detail row:                                        │
│   - Per-district severity table                     │
│   - Top-N flagged PSes for next 7 days (from model) │
│   - Sample case descriptions (anonymized)           │
└─────────────────────────────────────────────────────┘
```

## Map layers

1. **Heat density** — `leaflet.heat`, yellow → red gradient. The signature
   visualization from the Research Design Report.
2. **Individual case markers** — clustered, color-coded by community
   (christian=blue, ahmadi=orange, hindu=purple, sikh=teal,
   unspecified=grey).
3. **Strict-label overlay** — red ring around the 312 high-confidence
   cases (toggleable).
4. **Predicted risk** — once the model is trained, top-N predicted
   high-risk PSes for the next 7 days shown as larger red diamonds with
   the predicted risk score in the popup.
5. **Police-station boundaries** (optional) — outline of the PS in focus,
   pulled from `db_predictive_policing.police_station_boundaries_v2`.

## Filters

| Filter | UI |
|---|---|
| Year | multi-select (2024, 2025, 2026) |
| District | searchable dropdown |
| Community | checkbox group (the 6 categories) |
| Severity band | checkbox group (Low / Medium / High / Critical) |
| Match source | radio (any / both / religious_offence / desc_keyword) |
| Strict label only | toggle |
| Date range | range slider over `incident_date` |

All filters compose. A "reset filters" button is mandatory.

## KPI charts

- **Monthly trend line** — total cases per month, with a separate line
  for `is_minority_targeted = TRUE`.
- **Top-15 PSes bar** — filterable.
- **Community pie** — under current filter.
- **Severity distribution** — colored stacked bar per district.

## Predicted-risk panel (W7-8 output)

A table of the top-25 PSes by next-7-day predicted risk score:

| Rank | PS | District | Risk score | Driving features (SHAP) | Last incident |
|---|---|---|---|---|---|
| 1 | Nisthar Colony | Lahore | 0.74 | `prior_30d_ps_count=12`, `days_to_christmas=8` | 2026-06-18 |
| … | … | … | … | … | … |

The "driving features" column is the model card's explanation handed
through to the dashboard — a non-technical reader should be able to read
a row aloud.

## Performance budgets

- Initial page load: < 3 seconds on localhost.
- Map redraw on filter change: < 1 second up to 4,000 markers.
- All data preloaded at startup (4,110 rows × ~15 cols = trivial).

## Decisions and trade-offs

- **Streamlit not Plotly Dash.** Streamlit is faster to ship the v1; Dash
  has more flexibility but the timeline doesn't justify it.
- **No login in v1.** The dashboard runs on localhost or behind an
  existing access-controlled URL; we don't build a user-auth layer.
  Discussed in [ethics_and_limitations.md](ethics_and_limitations.md).
- **One screen, no tabs.** Tabs hide information. The Research Design
  Report assumes a single-screen heatmap with surrounding context; we
  preserve that.

## Output artifacts

```
src/viz/
  dashboard.py           ← Streamlit app
  heatmap.py             ← HTML heatmap generator (already shipped — W3-4)
  components.py          ← reusable Plotly chart functions

outputs/
  dashboard_runbook.md   ← "how to run / how to deploy"
  screenshots/           ← for the policy brief
```

## Deployment

For the supervisor: `streamlit run src/viz/dashboard.py` on a machine
with DB access — the dashboard reads live from `minority_incidents` so
new data shows up on refresh.

For demo / submission: a screen-recording (mp4) and 4-6 screenshots saved
to `outputs/screenshots/`.

## Limitations

- No real-time updating beyond a page refresh. Acceptable for a research
  prototype.
- Live filtering of model predictions requires re-running the model on
  current data — that pipeline is not in scope for W9-10. The dashboard
  reads predictions from a precomputed table.

## Next steps

- Static HTML heatmaps are already shipped — see [`../outputs/figures/heatmap_lahore.html`](../outputs/figures/heatmap_lahore.html).
- Build Streamlit shell when feature + model phases are complete.
- See [06_policy_brief.md](06_policy_brief.md) for what the dashboard
  must support for the final deliverable.

## References

- HTML heatmap source: [`../src/viz/heatmap.py`](../src/viz/heatmap.py)
- Reference timeline: [`../references/Timeline.pdf`](../references/Timeline.pdf) Weeks 9-10
