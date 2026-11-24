"""Drought risk (Drive folder 'Drought'), IPC projection Oct 2026 - Mar 2027 (CSV shared 24 Nov 2026), DTM sites (Drive 'DTM sites.xlsx')."""
import os, pandas as pd, geopandas as gpd, numpy as np
os.environ['SHAPE_RESTORE_SHX'] = 'YES'
LV = {'No Threat': 'No threat'}
d = gpd.read_file('drt/d.shp'); d['geometry'] = d.geometry.simplify(60, preserve_topology=True); d = d.to_crs(4326)
dist = d.DIST_NAME.replace({'Nkhatabay': 'Nkhata Bay'})
D = gpd.GeoDataFrame({'district': dist, 'region': d.REG_NAME, 'risk': d.Descriptio.replace(LV), 'risk_class': d['D-Risk_CL'].astype(int)}, geometry=d.geometry, crs=4326)
D.to_file('drv_drought_risk.geojson', driver='GeoJSON'); print('drought risk', D.risk.value_counts().to_dict())
# ---- IPC
c = pd.read_csv('/mnt/user-data/uploads/25784801-IPC_October_2026_to_April_2027Sheet1.csv', thousands=',')
c = c.rename(columns={'District (standard spelling)': 'district'})
num = lambda s: pd.to_numeric(s.astype(str).str.replace(',', ''), errors='coerce')
I = pd.DataFrame({'district': c.district.str.strip(), 'area_phase': c['Area phase'].str.strip(), 'phase': c['Area phase'].str.extract(r'(\d)')[0].astype(int),
                  'population_analysed': num(c['Population analysed']).astype('Int64'),
                  **{f'phase{i}_people': num(c[f'Phase {i} #']).astype('Int64') for i in range(1, 6)},
                  **{f'phase{i}_pct': num(c[f'Phase {i} %']) for i in range(1, 6)},
                  'people_in_phase_3_or_worse': num(c['Phase 3+ #']).astype('Int64'), 'pct_in_phase_3_or_worse': num(c['Phase 3+ %'])})
I['area_phase_label'] = I.phase.map({1: 'Phase 1, minimal', 2: 'Phase 2, stressed', 3: 'Phase 3, crisis', 4: 'Phase 4, emergency', 5: 'Phase 5, famine'})
miss = set(I.district) - set(D.district); print('IPC districts without a polygon:', miss, '| polygons without IPC:', set(D.district) - set(I.district))
P = D[['district', 'geometry']].merge(I, on='district', how='inner'); P = gpd.GeoDataFrame(P, geometry='geometry', crs=4326)
P.to_file('drv_ipc_projection.geojson', driver='GeoJSON')
Pt = P.copy(); Pt['geometry'] = P.to_crs(32736).representative_point().to_crs(4326); Pt.to_file('drv_ipc_p3_points.geojson', driver='GeoJSON')
print('IPC', len(P), P.area_phase.value_counts().to_dict(), 'P3 total', int(P.people_in_phase_3_or_worse.sum()))
# ---- DTM sites
s = pd.read_excel('dtm_sites.xlsx', 'Sites')
S = pd.DataFrame({'site_name': s['Site name'], 'site_type': s['Site type'], 'district': s.District, 'ta': s.TA, 'gvh': s.GVH,
  'occupied_now': s['Occupied now'], 'households_now': s['Households now'].astype('Int64'), 'people_now': s['People now'].astype('Int64'), 'occupancy_figures_from': s['Occupancy figures from'],
  'utilisation_status': s['Utilisation status'], 'site_listed_from': s['Site listed from'], 'capacity_households': s['Capacity (households)'].astype('Int64'),
  'physical_condition': s['Physical condition'], 'floods_or_cut_off': s['Floods or cut off']})
G = gpd.GeoDataFrame(S, geometry=gpd.points_from_xy(s.Longitude, s.Latitude), crs=4326)
for t, n in [('Collective site', 'drv_sites_collective'), ('Government-managed evacuation centre', 'drv_sites_evac')]:
    G[G.site_type == t].to_file(n + '.geojson', driver='GeoJSON'); print(t, (G.site_type == t).sum())
