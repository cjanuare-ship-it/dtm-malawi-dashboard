"""Everything here comes from the Drive folder "Data for the Dash" plus the target-area flood frequency GeoPackage shared on 24 Nov 2026:
DCCMS extreme rainfall and dry spell (January-March), cyclone tracks 2000-2026, flood frequency for all target areas (RE2CLID_target_areas_flood_frequency.gpkg),
and the BSA preliminary export (13 Nov 2026)."""
import json, glob, os, re, geopandas as gpd, pandas as pd, numpy as np
from shapely.ops import unary_union
os.environ['SHAPE_RESTORE_SHX'] = 'YES'
rain = gpd.read_file('out_rain.geojson'); dry = gpd.read_file('out_dry.geojson'); cyc = gpd.read_file('out_cyclones.geojson'); gvh = gpd.read_file('out_gvh.geojson')
# ---- flood frequency for all target areas (one GeoPackage, kept at full detail as supplied)
FF = gpd.read_file('/home/claude/ffall/ff.gpkg').rename(columns={'unit': 'district', 'Years_flooded': 'years_flooded'})
FF['years_class'] = FF.years_flooded.map(lambda y: '1 year' if y == 1 else ('2 years' if y == 2 else ('3–4 years' if y <= 4 else ('5–7 years' if y <= 7 else '8–10 years'))))
FF['area_km2'] = (FF.to_crs(32736).area / 1e6).round(3)
FF[['district', 'years_flooded', 'years_class', 'area_km2', 'geometry']].to_file('drv_flood_frequency.geojson', driver='GeoJSON')
stats = {d: {'flood_area_any_km2': round(float(g.area_km2.sum()), 1), 'flood_area_5plus_km2': round(float(g[g.years_flooded >= 5].area_km2.sum()), 1), 'flood_max_years': int(g.years_flooded.max())} for d, g in FF.groupby('district')}
print('flood frequency', len(FF), round(os.path.getsize('drv_flood_frequency.geojson') / 1e6, 1), 'MB')
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
