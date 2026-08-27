#!/usr/bin/env python3
"""
Build interactive heatmaps for the minority_incidents table.

Produces three self-contained HTML files in outputs/figures/:
  heatmap_lahore.html   — Lahore-only view
  heatmap_punjab.html   — Punjab-wide view
  heatmap_strict.html   — strict-label minority-targeted rows only

Each HTML embeds its own data + Leaflet/Leaflet.heat from CDN. No server
needed — just open the file in a browser.
"""
import json
import os
import sys

ROOT = '/home/rizwan.tahir/cpis-backend'
sys.path.append(os.path.join(ROOT, 'utilties'))
from db_config import get_db_postgres_predictive  # noqa: E402

PROJECT = '/home/rizwan.tahir/cpis-backend/minorities/minorities_project'
OUT = os.path.join(PROJECT, 'outputs', 'figures')
os.makedirs(OUT, exist_ok=True)


def fetch(conn, where, label):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT lat, long, minority_community,
               level3_case_nature, district_name, police_station,
               TO_CHAR(incident_date, 'YYYY-MM-DD'),
               LEFT(description, 200)
        FROM minority_incidents
        WHERE lat IS NOT NULL AND long IS NOT NULL {where}
    """)
    rows = []
    for lat, lon, comm, l3, dn, ps, dt, desc in cur.fetchall():
        rows.append({
            'lat': float(lat), 'lon': float(lon),
            'comm': comm or 'unspecified',
            'l3': l3 or '',
            'dist': dn or '',
            'ps': ps or '',
            'date': dt or '',
            'desc': desc or '',
        })
    cur.close()
    print(f'  {label}: {len(rows)} mappable rows')
    return rows


HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
<style>
  *{box-sizing:border-box;}
  html,body{margin:0;padding:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
  #app{display:flex;flex-direction:column;height:100vh;}
  header{background:#1a1a2e;color:#fff;padding:10px 16px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;flex-shrink:0;}
  header h1{font-size:14px;margin:0;font-weight:600;}
  header .stats{font-size:12px;opacity:0.95;}
  header .stats span{margin-right:12px;}
  #ctrl{position:absolute;top:60px;right:14px;background:#fff;padding:10px 12px;border-radius:6px;box-shadow:0 1px 5px rgba(0,0,0,0.2);font-size:13px;z-index:1000;}
  #ctrl label{display:block;padding:3px 0;cursor:pointer;user-select:none;}
  #ctrl h4{margin:0 0 6px;font-size:11px;color:#666;text-transform:uppercase;}
  #map{flex:1;}
  .leaflet-popup-content{font-size:12px;line-height:1.4;max-width:300px;}
  .leaflet-popup-content b{color:#1a1a2e;}
  .legend{background:#fff;padding:8px 10px;border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.2);font-size:11px;line-height:1.4;}
  .legend .gradient{display:flex;gap:0;height:10px;margin:4px 0;}
  .legend .gradient div{flex:1;}
</style></head>
<body>
<div id="app">
  <header>
    <h1>__TITLE__</h1>
    <div class="stats" id="stats"></div>
  </header>
  <div id="map"></div>
  <div id="ctrl">
    <h4>Layers</h4>
    <label><input type="checkbox" id="lyr-heat" checked> Heat density</label>
    <label><input type="checkbox" id="lyr-points"> Individual cases</label>
    <h4 style="margin-top:8px">Filter by community</h4>
    <label><input type="checkbox" data-c="christian" checked> Christian</label>
    <label><input type="checkbox" data-c="ahmadi" checked> Ahmadi</label>
    <label><input type="checkbox" data-c="hindu" checked> Hindu</label>
    <label><input type="checkbox" data-c="sikh" checked> Sikh</label>
    <label><input type="checkbox" data-c="multiple" checked> Multiple</label>
    <label><input type="checkbox" data-c="unspecified" checked> Unspecified</label>
  </div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<script>
const DATA = __DATA__;
const COMM_COLOR = {christian:'#3498db', ahmadi:'#e67e22', hindu:'#9b59b6', sikh:'#16a085', multiple:'#f1c40f', unspecified:'#bdc3c7'};

document.getElementById('stats').innerHTML =
  `<span><b>${DATA.length}</b> mappable cases</span>` +
  Object.entries(DATA.reduce((a,r)=>{a[r.comm]=(a[r.comm]||0)+1;return a;}, {}))
        .map(([k,n])=>`<span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${COMM_COLOR[k]||'#888'};margin-right:4px;vertical-align:middle"></span>${k}: ${n}</span>`).join('');

let lats=DATA.map(r=>r.lat), lons=DATA.map(r=>r.lon);
const BBOX=[[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]];

const map=L.map('map',{preferCanvas:true}).fitBounds(BBOX);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(map);

let activeComms=new Set(['christian','ahmadi','hindu','sikh','multiple','unspecified']);
let heatLayer=null;
const cluster=L.markerClusterGroup({showCoverageOnHover:false, maxClusterRadius:45, disableClusteringAtZoom:15});

function buildHeat(){
  const pts=DATA.filter(r=>activeComms.has(r.comm)).map(r=>[r.lat, r.lon, 0.5]);
  if(heatLayer) map.removeLayer(heatLayer);
  heatLayer=L.heatLayer(pts,{radius:22, blur:24, maxZoom:15,
    gradient:{0.2:'#fee5d9', 0.4:'#fcae91', 0.6:'#fb6a4a', 0.8:'#de2d26', 1.0:'#a50f15'}});
  if(document.getElementById('lyr-heat').checked) map.addLayer(heatLayer);
}

function buildPoints(){
  cluster.clearLayers();
  DATA.filter(r=>activeComms.has(r.comm)).forEach(r=>{
    const m=L.circleMarker([r.lat,r.lon],{radius:5, fillColor:COMM_COLOR[r.comm]||'#888', color:'#222', weight:0.7, opacity:0.9, fillOpacity:0.85});
    m.bindPopup(`<b>${r.l3||'(no category)'}</b><br><small>${r.date}</small><table><tr><td><b>District:</b></td><td>${r.dist}</td></tr><tr><td><b>PS:</b></td><td>${r.ps}</td></tr><tr><td><b>Community:</b></td><td>${r.comm}</td></tr></table><div style="color:#555;margin-top:4px">${r.desc||''}</div>`);
    cluster.addLayer(m);
  });
}

buildHeat(); buildPoints();
document.getElementById('lyr-heat').addEventListener('change', e=>{
  if(e.target.checked) map.addLayer(heatLayer); else map.removeLayer(heatLayer);
});
document.getElementById('lyr-points').addEventListener('change', e=>{
  if(e.target.checked) map.addLayer(cluster); else map.removeLayer(cluster);
});
document.querySelectorAll('#ctrl input[data-c]').forEach(cb=>{
  cb.addEventListener('change',()=>{
    activeComms.clear();
    document.querySelectorAll('#ctrl input[data-c]').forEach(c=>{if(c.checked) activeComms.add(c.dataset.c);});
    buildHeat(); buildPoints();
  });
});

const legend=L.control({position:'bottomright'});
legend.onAdd=function(){
  const div=L.DomUtil.create('div','legend');
  div.innerHTML='<b>Heat density (low → high)</b><div class="gradient"><div style="background:#fee5d9"></div><div style="background:#fcae91"></div><div style="background:#fb6a4a"></div><div style="background:#de2d26"></div><div style="background:#a50f15"></div></div>'
    + '<div><b>Community markers</b></div>'
    + Object.entries(COMM_COLOR).map(([k,c])=>`<div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${c};margin-right:4px"></span>${k}</div>`).join('');
  return div;
};
legend.addTo(map);
</script>
</body></html>
"""


def write_html(rows, title, out_name):
    html = (HTML
            .replace('__TITLE__', title)
            .replace('__DATA__', json.dumps(rows, ensure_ascii=False, separators=(',', ':'))))
    p = os.path.join(OUT, out_name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'  → {p}  ({os.path.getsize(p)/1024:.0f} KB)')


def main():
    conn = get_db_postgres_predictive()
    lah  = fetch(conn, "AND is_lahore", 'Lahore')
    full = fetch(conn, "", 'Punjab')
    strict = fetch(conn, "AND is_minority_targeted", 'Strict')
    conn.close()

    write_html(lah,  'Minority Incidents — Lahore (heatmap)',    'heatmap_lahore.html')
    write_html(full, 'Minority Incidents — Punjab (heatmap)',    'heatmap_punjab.html')
    write_html(strict,'Minority Incidents — Strict-label only',  'heatmap_strict.html')


if __name__ == '__main__':
    main()
