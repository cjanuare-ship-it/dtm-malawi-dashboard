# Run next to the BSA Excel export, the DCCMS JFM shapefiles (rain/, dry/) and the cyclone shapefile (cyc/).
# Writes the GeoJSON layers used by the Flood and Drought tabs. Key informant names, phone numbers,
# enumerator names and free-text notes are never read into the outputs.
"""Flood / Drought tab layers from the BSA preliminary file (13 Nov 2026), DCCMS JFM risk maps and cyclone tracks 2000-2026.
No names of key informants, enumerators or phone numbers are carried over."""
import pandas as pd, numpy as np, geopandas as gpd, json, gzip, base64, os, shapely
from shapely.geometry import LineString, shape
os.environ['SHAPE_RESTORE_SHX'] = 'YES'
m = pd.read_excel('bsa.xlsx', sheet_name=0)  # the BSA export, renamed bsa.xlsx
m = m[m['META6. Assessment location - district (ADM2)'].notna()].copy()
def col(code, sub=None):
    cs = [c for c in m.columns if str(c).startswith(code + '.') or str(c).startswith(code + ' ')]
    cs = [c for c in cs if (str(c).endswith('/' + sub) if sub else '/' not in str(c))]
    return cs[0]
num = lambda s: pd.to_numeric(s, errors='coerce').where(lambda x: ~x.isin([-999, -99, -9999]))
st = pd.read_excel('bsa.xlsx', 'st_repeat')
stc = lambda code: [c for c in st.columns if str(c).startswith(code + '.')][0]
st['st6'] = num(st[stc('IDP_ST6')]); st['st9'] = st[stc('IDP_ST9')]; st['st10'] = st[stc('IDP_ST10.1')]
st_sum = st.groupby('_parent_index').st6.sum(min_count=1)
st_drought = st[st.st9 == 'Drought'].groupby('_parent_index').st6.sum(min_count=1)
st_year = st.sort_values('st6', ascending=False).groupby('_parent_index').st10.first()

g = pd.DataFrame(index=m.index)
name = m[col('META8')].where(m[col('META8')] != 'Not listed (specify)', m[col('META8_oth')])
g['gvh'] = name.fillna('(unnamed)').astype(str).str.strip()
g['ta'] = m[col('META7')]; g['district'] = m[col('META6')]; g['region'] = m[col('META5')]; g['adm3_pcode'] = m['adm3_pcode']
g['assessment_date'] = pd.to_datetime(m[col('META1')], errors='coerce').dt.strftime('%Y-%m-%d')
g['households'] = num(m[col('POP1')]); g['population'] = num(m[col('POP2')])
# displacement now
g['idp_host_families'] = num(m[col('IDP_HF2')])
g['idp_in_sites'] = m['_index'].map(st_sum)
g['idp_total'] = g[['idp_host_families', 'idp_in_sites']].sum(axis=1, min_count=1)
yr = num(m[col('IDP_HF6.1')]).where(lambda x: x > 1900)
g['idp_arrival_year'] = yr.fillna(m['_index'].map(st_year))
g['most_idps_arrived_2023'] = np.where(g.idp_arrival_year == 2023, 'Yes', np.where(g.idp_total > 0, 'No', None))
g['idp_cause_host_families'] = m[col('IDP_HF5')]
# hazards
g['most_damaging_hazard'] = m[col('HAZ2')]
g['flood_most_damaging'] = np.where(m[col('HAZ2')] == 'Flood', 'Flood', np.where(m[col('HAZ2')].notna(), 'Another hazard', None))
g['last_affected'] = m[col('HAZ3')]
fl = m[col('HAZ7.1')]
g['flood_events_5y'] = fl.map({'2 times': '2 times', '3 times': '3 times', '4 times': '4 times', '5 or more times': '5 or more times'}).fillna('Not recurrent (0–1)')
g['flood_events_n'] = fl.map({'2 times': 2, '3 times': 3, '4 times': 4, '5 or more times': 5})
haz2, haz3 = m[col('HAZ2')], m[col('HAZ3')]
g['drought_status'] = np.select([(haz2 == 'Drought') & (haz3 == 'Ongoing now'), (haz2 == 'Drought') & (haz3 == 'In the last 12 months')],
                                ['Drought ongoing now', 'Drought in the last 12 months'], 'Earlier, or drought not the main hazard')
g['drought_events_5y'] = m[col('HAZ7.2')]
four = {'No significant difficulties reported': '1 None', 'Some households face difficulties (less than 50%)': '2 Some households (<50%)',
        'Most households face difficulties (50% or more)': '3 Most households (50%+)', 'Food markets are inaccessible to all households': '4 Severe: markets inaccessible to all',
        'No households are able to obtain sufficient drinking water': '4 Severe: no household has enough water', "Don't know": "Don't know"}
g['food_market_difficulty'] = m[col('FOOD1')].map(four).str.replace(r'^\d ', '', regex=True)
g['drinking_water_difficulty'] = m[col('WAT1')].map(four).str.replace(r'^\d ', '', regex=True)
g['livelihood_conditions'] = m[col('LIV3')].str.split(' - ').str[0]
g['housing_condition'] = m[col('SHELT2')].str.split(' - ').str[0]
g['coping_strategies_used'] = m[col('COP1')]
g['early_warning_received'] = m[col('EWS1')]; g['warning_in_time'] = m[col('EWS5')]; g['evacuation_place_known'] = m[col('EWS9')]; g['active_vcpc'] = m[col('EWS11')]
g['hazard_most_displacement'] = m[col('HD2')]
lat = m['gps_lat'].fillna(m['village_lat']); lon = m['gps_lon'].fillna(m['village_lon'])
ok = lat.notna() & lon.notna() & (lat != 0)
G = gpd.GeoDataFrame(g[ok].reset_index(drop=True), geometry=gpd.points_from_xy(lon[ok], lat[ok]), crs=4326)
for c in G.columns:
    if c != 'geometry' and G[c].dtype == float and (G[c].dropna() % 1 == 0).all(): G[c] = G[c].astype('Int64')
G.to_file('out_gvh.geojson', driver='GeoJSON')
print('GVH points', len(G), 'of', len(m), '| idp_total>0', (G.idp_total > 0).sum(), '| arrived 2023', (G.most_idps_arrived_2023 == 'Yes').sum())

# ---------- TA indicators (% of GVHs assessed in each TA)
mm = m.copy(); mm['_ta'] = g['ta']; mm['_district'] = g['district']; mm['_pc'] = g['adm3_pcode']
def multi(code, sub): return mm[col(code, sub)]
SERV = [('roads', 'Roads / bridges'), ('water', 'Water supply'), ('health', 'Health services'), ('schools', 'Schools'), ('markets', 'Markets'), ('electricity', 'Electricity / energy'), ('telecom', 'Telecommunications'), ('none', 'None')]
rows = []
for pc, d in mm.groupby('_pc'):
    r = {'adm3_pcode': pc, 'ta': d._ta.iloc[0], 'district': d._district.iloc[0], 'gvhs_assessed': len(d)}
    def pct(mask, base):
        n = int(base.sum()); return (round(100 * (mask & base).sum() / n, 1) if n else None), n
    for code, key in [('INF3.1', 'flood'), ('INF3.2', 'drought')]:
        base = d[col(code)].notna()
        for k, lab in SERV:
            r[f'{key}_disrupts_{k}_pct'], r[f'{key}_disrupts_n'] = pct(d[col(code, lab)] == 1, base)
    e1 = d[col('EWS1')]; b = e1.notna()
    r['ews_receives_warning_pct'], r['ews_n'] = pct(e1 == 'Yes', b)
    r['ews_sometimes_pct'], _ = pct(e1 == 'Sometimes', b)
    e5 = d[col('EWS5')]; r['ews_warning_in_time_pct'], r['ews_in_time_n'] = pct(e5 == 'Yes', e5.notna())
    e9 = d[col('EWS9')]; r['ews_evacuation_place_pct'], r['ews_evac_n'] = pct(e9 == 'Yes', e9.notna())
    e11 = d[col('EWS11')]; r['ews_active_vcpc_pct'], r['ews_vcpc_n'] = pct(e11 == 'Yes', e11.notna())
    s2 = d[col('SHELT2')].str.split(' - ').str[0]; b = s2.notna()
    for k, lab in [('good', 'Good condition'), ('fair', 'Fair condition'), ('poor', 'Poor condition'), ('very_poor', 'Very poor condition')]:
        r[f'housing_{k}_pct'], r['housing_n'] = pct(s2 == lab, b)
    r['housing_poor_or_worse_pct'], _ = pct(s2.isin(['Poor condition', 'Very poor condition']), b)
    l3 = d[col('LIV3')].str.split(' - ').str[0]; b = l3.notna()
    for k, lab in [('good', 'Good'), ('fair', 'Fair'), ('poor', 'Poor'), ('very_poor', 'Very poor')]:
        r[f'livelihood_{k}_pct'], r['livelihood_n'] = pct(l3 == lab, b)
    r['livelihood_poor_or_worse_pct'], _ = pct(l3.isin(['Poor', 'Very poor']), b)
    c1 = d[col('COP1')]; b = c1.notna() & (c1 != "Don't know")
    r['coping_most_households_pct'], r['coping_n'] = pct(c1 == 'Yes, most households (50% or more)', b)
    r['coping_some_households_pct'], _ = pct(c1 == 'Yes, some households (less than 50%)', b)
    r['coping_none_pct'], _ = pct(c1 == 'No', b)
    c3 = d[col('COP3')]; r['coping_not_sufficient_pct'], r['coping_suff_n'] = pct(c3 == 'No, for most households (50% or more)', c3.notna())
    hd2 = d[col('HD2')]; r['gvhs_drought_main_displacement'] = int((hd2 == 'Drought').sum()); r['gvhs_flood_main_displacement'] = int((hd2 == 'Flood').sum())
    hf2, hf5 = num(d[col('IDP_HF2')]), d[col('IDP_HF5')]
    r['idps_host_families_drought'] = int(hf2[hf5 == 'Drought'].sum()); r['idps_host_families_flood'] = int(hf2[hf5 == 'Flood'].sum())
    r['idps_sites_drought'] = int(d['_index'].map(st_drought).fillna(0).sum())
    r['idps_drought_displaced_total'] = r['idps_host_families_drought'] + r['idps_sites_drought']
    r['idps_now_total'] = int((hf2.fillna(0) + d['_index'].map(st_sum).fillna(0)).sum())
    rows.append(r)
T = pd.DataFrame(rows)
# TA boundaries: export the "Traditional Authorities (ADM3)" layer from the workspace as GeoJSON (layer menu > Export as GeoJSON)
A = gpd.read_file('adm3.geojson')[['adm3_pcode', 'geometry']].to_crs(4326)
TA = A.merge(T, on='adm3_pcode', how='inner')
TA.to_file('out_ta.geojson', driver='GeoJSON'); print('TA polygons', len(TA), 'of', len(T), 'TAs | missing', set(T.adm3_pcode) - set(TA.adm3_pcode))

# ---------- DCCMS JFM risk (Arc 1950 / UTM 36S -> WGS 84), simplified to 60 m
order = {'No Threat': 'No threat', 'Moderate': 'Moderate', 'Severe': 'Severe', 'Extreme': 'Extreme'}
for src, dst, cl in [('rain/r.shp', 'out_rain.geojson', 'RainRiskCL'), ('dry/d.shp', 'out_dry.geojson', 'D-S-RiskCL')]:
    d = gpd.read_file(src); d['geometry'] = d.geometry.simplify(60, preserve_topology=True); d = d.to_crs(4326)
    o = gpd.GeoDataFrame({'district': d.DIST_NAME, 'region': d.REG_NAME, 'risk_class': d[cl].astype(int), 'risk': d.Descriptio.map(order).fillna(d.Descriptio)}, geometry=d.geometry, crs=4326)
    o.to_file(dst, driver='GeoJSON'); print(dst, o.risk.value_counts().to_dict(), round(os.path.getsize(dst) / 1e6, 2), 'MB')

# ---------- cyclone tracks: one line per storm
c = gpd.read_file('cyc/c.shp'); c = c.sort_values(['SID', 'ISO_TIME'])
tr = []
for sid, d in c.groupby('SID'):
    pts = []
    for geom in d.geometry:
        for xy in geom.coords:
            if not pts or (abs(pts[-1][0] - xy[0]) > 1e-9 or abs(pts[-1][1] - xy[1]) > 1e-9): pts.append(xy)
    nm = str(d.NAME.iloc[0]).strip(); nm = nm.title() if nm not in ('NOT_NAMED', 'UNNAMED') else 'Unnamed'
    tr.append({'name': nm, 'season': int(d.SEASON.iloc[0]), 'label': f'{nm} {int(d.SEASON.iloc[0])}', 'start': str(d.ISO_TIME.iloc[0])[:10], 'end': str(d.ISO_TIME.iloc[-1])[:10], 'sid': sid, 'geometry': LineString(pts) if len(pts) > 1 else None})
C = gpd.GeoDataFrame(tr, crs=4326); C = C[C.geometry.notna()]
C.to_file('out_cyclones.geojson', driver='GeoJSON'); print('cyclones', len(C), C.season.min(), C.season.max(), list(C.label)[:30])
