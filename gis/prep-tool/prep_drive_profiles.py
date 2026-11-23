"""Everything here comes from the Drive folder "Data for the Dash" only:
DCCMS extreme rainfall and dry spell (January-March), cyclone tracks 2000-2026, Sentinel-1 flood frequency (7 districts),
and the BSA preliminary export (13 Nov 2026)."""
import json, glob, os, re, geopandas as gpd, pandas as pd, numpy as np
from shapely.ops import unary_union
os.environ['SHAPE_RESTORE_SHX'] = 'YES'
rain = gpd.read_file('out_rain.geojson'); dry = gpd.read_file('out_dry.geojson'); cyc = gpd.read_file('out_cyclones.geojson'); gvh = gpd.read_file('out_gvh.geojson')
# ---- flood frequency: one layer, years flooded out of 10, 'never flooded' class dropped, simplified to 20 m
parts = []; stats = {}
for f in sorted(glob.glob('ff/*_Flood_Frequency.geojson')):
    d = re.match(r'ff/(.+)_Flood_Frequency', f).group(1); g = gpd.read_file(f)
    g = g[g.Years_flooded > 0].copy(); g['district'] = d
    u = g.to_crs(32736)
    # pixel outlines are heavy: close 1-pixel gaps, drop patches under 2 ha, then simplify to 40 m (map display only; areas in the profile use the original figures)
    u['geometry'] = u.geometry.buffer(15, resolution=1).buffer(-15, resolution=1).simplify(40, preserve_topology=True)
    u = u.explode(index_parts=False); u = u[u.geometry.area >= 20000]; u = u.dissolve(by='Years_flooded', as_index=False, aggfunc='first')
    parts.append(u.to_crs(4326)[['district', 'Years_flooded', 'Freq_pct', 'Description', 'Area_km2', 'geometry']])
    stats[d] = {'flood_area_any_km2': round(float(g.Area_km2.sum()), 1), 'flood_area_5plus_km2': round(float(g[g.Years_flooded >= 5].Area_km2.sum()), 1), 'flood_max_years': int(g.Years_flooded.max())}
FF = pd.concat(parts, ignore_index=True)
FF = gpd.GeoDataFrame(FF.rename(columns={'Years_flooded': 'years_flooded', 'Freq_pct': 'pct_of_years', 'Description': 'description', 'Area_km2': 'area_km2'}), crs=4326)
FF['years_class'] = FF.years_flooded.map(lambda y: '1 year' if y == 1 else ('2 years' if y == 2 else ('3–4 years' if y <= 4 else ('5–7 years' if y <= 7 else '8–10 years'))))
FF = FF.dissolve(by=['district', 'years_class'], as_index=False, aggfunc={'area_km2': 'sum', 'years_flooded': 'min'})
FF['geometry'] = FF.geometry.set_precision(1e-5)
FF.to_file('drv_flood_frequency.geojson', driver='GeoJSON', COORDINATE_PRECISION=5); print('flood frequency', len(FF), round(os.path.getsize('drv_flood_frequency.geojson') / 1e6, 2), 'MB')
# ---- district profiles
LV = {'No threat': 0, 'Moderate': 1, 'Severe': 2, 'Extreme': 3}
target = set(gvh.district.dropna())
D = rain[['district', 'region', 'risk', 'geometry']].rename(columns={'risk': 'rain_jfm'}).merge(dry[['district', 'risk']].rename(columns={'risk': 'dry_jfm'}), on='district', how='left')
alias = {'Blantyre City': 'Blantyre'}  # flood frequency for Blantyre covers the city too
rows = []
for _, r in D.iterrows():
    tr = cyc[cyc.intersects(r.geometry)].sort_values('season'); names = [f'{n} ({s})' for n, s in zip(tr.name, tr.season)]
    st = stats.get(r.district) or {}
    rows.append({'district': r.district, 'region': r.region, 'target': r.district in target,
      'rain_jfm': r.rain_jfm, 'rain_narrative': f'Extreme rainfall risk for January–March is {r.rain_jfm.lower() if r.rain_jfm != "No threat" else "none (no threat)"}.',
      'dry_jfm': r.dry_jfm, 'dry_narrative': f'Dry spell risk for January–March is {r.dry_jfm.lower() if r.dry_jfm != "No threat" else "none (no threat)"}.',
      'cyclone_count': len(names), 'cyclone_names': ', '.join(names),
      'cyclone_narrative': 'No cyclone track in the dataset crosses the district.' if not names else ('One cyclone track in the dataset crosses the district.' if len(names) == 1 else f'{len(names)} cyclone tracks in the dataset cross the district.'),
      'flood_area_any_km2': st.get('flood_area_any_km2'), 'flood_area_5plus_km2': st.get('flood_area_5plus_km2'), 'flood_max_years': st.get('flood_max_years')})
P = gpd.GeoDataFrame(rows, geometry=D.geometry.values, crs=4326)
P.to_file('drv_district_profiles.geojson', driver='GeoJSON')
print(P[P.target][['district', 'rain_jfm', 'dry_jfm', 'cyclone_count', 'flood_area_any_km2', 'flood_area_5plus_km2']].to_string())
