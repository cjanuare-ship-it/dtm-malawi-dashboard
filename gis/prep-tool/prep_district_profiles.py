"""Layers and district profiles from IOM's public 'District Profiles RE2CLID' ArcGIS service (owner kpolyakova_IOM),
downloaded as one JSON bundle. Rebuilds the Arcade profile logic of the ArcGIS dashboard in Python."""
import json, re, geopandas as gpd, pandas as pd, numpy as np
from shapely.geometry import shape
b = json.load(open('/home/claude/arcgis_in/bundle.json'))
def gdf(k):
    g = gpd.GeoDataFrame.from_features(b[k]['geojson']['features'], crs=4326)
    if g.geom_type.iloc[0] in ('Polygon', 'MultiPolygon'): g['geometry'] = g.geometry.simplify(0.0022, preserve_topology=True)  # about 250 m, enough for district maps
    return g
def num(s): return pd.to_numeric(pd.Series(s).astype(str).str.replace(r'[\s,%]', '', regex=True).replace({'None': None, 'nan': None, '': None}), errors='coerce')
LV = {'No Threat': 0, 'Moderate': 1, 'Severe': 2, 'Extreme': 3}
def risk_layer(k, name):
    g = gdf(k); o = gpd.GeoDataFrame({'district': g.DIST_NAME, 'region': g.REG_NAME, 'risk': g.Descriptio.replace({'No Threat': 'No threat'}), 'risk_class': g.Descriptio.map(LV).astype('Int64')}, geometry=g.geometry, crs=4326)
    o.to_file(f'ag/{name}.geojson', driver='GeoJSON'); return g.set_index('DIST_NAME').Descriptio
ond = risk_layer('dp_8', 'rain_ond'); jfm = risk_layer('dp_9', 'rain_jfm'); drt = risk_layer('dp_13', 'drought_risk'); dj = risk_layer('dp_14', 'dry_jfm'); do = risk_layer('dp_15', 'dry_ond')
D = gdf('dp_8')[['DIST_NAME', 'REG_NAME', 'geometry']].rename(columns={'DIST_NAME': 'district', 'REG_NAME': 'region'})
# IPC: centroid points in the service -> district polygons coloured by area phase (standard IPC scale)
def ipc(k, pre, name):
    g = gdf(k); c = lambda f: g[pre + f] if pre + f in g else g[f]
    t = pd.DataFrame({'district': c('ADM2_EN'), 'area_phase': c('Area_Phase'), 'phase': c('Area_Phase').str.extract(r'(\d)')[0].astype(float).astype('Int64'),
                      'population': num(c('Total_Pop')).astype('Int64'), 'p3plus_people': num(c('P3plus_People')).astype('Int64'), 'p3plus_pct': num(c('P3plus_Pct')),
                      **{f'p{i}_people': num(c(f'P{i}_People')).astype('Int64') for i in range(1, 6)}})
    o = D.merge(t, on='district', how='left'); gpd.GeoDataFrame(o, geometry='geometry', crs=4326).to_file(f'ag/{name}.geojson', driver='GeoJSON'); return t.set_index('district')
ic = ipc('dp_11', '', 'ipc_current'); ip = ipc('dp_12', 'Oct_26___March_2027_IPC_csv_', 'ipc_projection')
pop = gdf('dp_4'); P = pop.set_index('ADM2_EN').TotalPop
gpd.GeoDataFrame({'district': pop.ADM2_EN, 'population_2023': pop.TotalPop.round().astype('Int64'), 'female': num(pop.F_TL).astype('Int64'), 'male': num(pop.M_TL).astype('Int64')}, geometry=pop.geometry, crs=4326).to_file('ag/population.geojson', driver='GeoJSON')
s = gdf('dp_7'); keep = ['SITE_NAME', 'DISTRICT', 'TA_STA', 'GVH', 'FIRST_EVENT_YEAR', 'LAST_EVENT_YEAR', 'N_EVENTS', 'EVENTS', 'MAX_IDPS', 'MAX_IDP_HH', 'RECURRENCE_CLASS', 'SITE_TYPE_LATEST', 'SITE_CLASS_LATEST', 'ACCESS_LATEST', 'FLOOD_HAZARD_EXPOSURE', 'CURRENT_STATUS_VALIDATED']
S = s[keep + ['geometry']].copy(); S.columns = [c.lower() for c in keep] + ['geometry']; S['max_idps'] = num(S.max_idps).astype('Int64')
S['site_events'] = np.select([S.n_events >= 3, S.n_events == 2], ['Highly recurrent (3+ events)', 'Recurrent (2 events)'], 'Historical (1 event)')
S = S.rename(columns={'ta_sta': 'ta'}); S.to_file('ag/historical_sites.geojson', driver='GeoJSON')
dd = gdf('b6f7_19'); DD = gpd.GeoDataFrame({'ta': dd.adm3_name, 'district': dd.adm2_name, 'adm3_pcode': dd.adm3_pcode, 'drought_idps_2024': dd.DTM_Recorded_IDPs.astype('Int64'), 'drought_locations_2024': dd.Drought_Displacement_Locations.astype('Int64'), 'survey_round': dd.Survey_Round}, geometry=dd.geometry, crs=4326)
DD = DD[DD.drought_idps_2024.fillna(0) > 0]
DDp = DD.copy(); DDp['geometry'] = DD.to_crs(32736).representative_point().to_crs(4326); DDp.to_file('ag/drought_idps_2024.geojson', driver='GeoJSON')  # one circle per TA
cyc = gdf('dp_6')
def rain_narr(o, j):
    if not j: return f'Extreme rainfall risk during October–December is classified as {o}.'
    if o == j: return f'Extreme rainfall risk remains {o} across both October–December and January–March.'
    up = LV.get(j, 0) > LV.get(o, 0)
    return f'Risk {"increases" if up else "decreases"} from {o} during October–December to {j} during January–March' + (', indicating more extreme rainfall later in the rainy season.' if up else '.')
def dry_narr(r, o, j):
    s = f'Drought risk is classified as {r}.'
    if not o or not j: return s
    if o == j: return s + f' Dry-spell risk remains {o} across both seasons.'
    return s + f' Dry-spell risk {"increases" if LV.get(j, 0) > LV.get(o, 0) else "decreases"} from {o} during October–December to {j} during January–March.'
rows = []
dsum = DD.groupby('district')[['drought_idps_2024', 'drought_locations_2024']].sum()
for _, r in D.iterrows():
    d = r.district; ds = S[S.district == d]; tr = cyc[cyc.intersects(r.geometry)]
    names = []; [names.append(n.title()) for n in tr.NAME if n and n.title() not in names and n not in ('NOT_NAMED', 'UNNAMED')]
    seasons = {n.title(): int(se) for n, se in zip(tr.NAME, tr.SEASON) if n}
    o_, j_ = ond.get(d), jfm.get(d); di = dsum.loc[d] if d in dsum.index else None
    cur = ic.loc[d] if d in ic.index else None; prj = ip.loc[d] if d in ip.index else None
    nm = lambda v: 'No threat' if v == 'No Threat' else v
    rows.append({'district': d, 'region': r.region,
        'rain_ond': nm(o_), 'rain_jfm': nm(j_), 'rain_narrative': rain_narr(nm(o_), nm(j_)).replace('No Threat', 'No threat'),
        'population_2023': int(P.get(d)) if pd.notna(P.get(d)) else None,
        'historical_sites': len(ds), 'recurrent_sites': int((ds.n_events >= 2).sum()), 'recorded_idps_sites': int(ds.max_idps.fillna(0).sum()),
        'cyclone_count': len(names), 'cyclone_names': ', '.join(f'{n} ({seasons[n]})' for n in names),
        'cyclone_narrative': 'No cyclone track in the dataset crosses the district.' if not names else ('One cyclone track in the dataset crosses the district.' if len(names) == 1 else f'{len(names)} cyclone tracks in the dataset cross the district, a sign of repeated exposure.'),
        'drought_risk': nm(drt.get(d)), 'dry_ond': nm(do.get(d)), 'dry_jfm': nm(dj.get(d)), 'drought_narrative': dry_narr(nm(drt.get(d)), nm(do.get(d)), nm(dj.get(d))),
        'ipc_current_phase': None if cur is None else cur.area_phase, 'ipc_current_p3plus': None if cur is None or pd.isna(cur.p3plus_people) else int(cur.p3plus_people), 'ipc_current_p3plus_pct': None if cur is None or pd.isna(cur.p3plus_pct) else float(cur.p3plus_pct),
        'ipc_projection_phase': None if prj is None else prj.area_phase, 'ipc_projection_p3plus': None if prj is None or pd.isna(prj.p3plus_people) else int(prj.p3plus_people), 'ipc_projection_p3plus_pct': None if prj is None or pd.isna(prj.p3plus_pct) else float(prj.p3plus_pct),
        'drought_idps_2024': 0 if di is None else int(di.drought_idps_2024), 'drought_locations_2024': 0 if di is None else int(di.drought_locations_2024),
        'target': d in set(gdf('dp_1').adm2_name)})
PR = gpd.GeoDataFrame(rows, geometry=D.geometry.values, crs=4326); PR.to_file('ag/district_profiles.geojson', driver='GeoJSON')
for k, n in [('dp_1', 'target_districts'), ('dp_2', 'target_tas')]: pass
print(PR[PR.target][['district', 'rain_ond', 'rain_jfm', 'historical_sites', 'recurrent_sites', 'recorded_idps_sites', 'cyclone_count', 'drought_risk', 'ipc_current_phase', 'ipc_projection_phase', 'drought_idps_2024']].to_string())
print(PR[PR.district == 'Nsanje'].cyclone_names.iloc[0])
import os; print({f: round(os.path.getsize('ag/' + f) / 1e3) for f in os.listdir('ag')})
