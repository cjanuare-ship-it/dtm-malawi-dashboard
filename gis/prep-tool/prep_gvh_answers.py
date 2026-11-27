"""Per-GVH answer fields for the Dashboard side panels, from the BSA preliminary file (same definitions as the TA indicators).
Each field is Yes / No, or empty when the question was not asked or not answered, so a panel line can show the share of GVHs answering Yes."""
import pandas as pd, numpy as np, json
m = pd.read_pickle('main.pkl'); m = m[m['META6. Assessment location - district (ADM2)'].notna()].copy()
def col(code, sub=None):
    cs = [c for c in m.columns if str(c).startswith(code + '.') or str(c).startswith(code + ' ')]
    cs = [c for c in cs if (str(c).endswith('/' + sub) if sub else '/' not in str(c))]
    return cs[0]
num = lambda s: pd.to_numeric(s, errors='coerce').where(lambda x: ~x.isin([-999, -99, -9999]))
st = pd.read_excel('bsa.xlsx', 'st_repeat'); stc = lambda code: [c for c in st.columns if str(c).startswith(code + '.')][0]
st['st6'] = num(st[stc('IDP_ST6')]); st['st9'] = st[stc('IDP_ST9')]
st_drought = st[st.st9 == 'Drought'].groupby('_parent_index').st6.sum(min_count=1)
yn = lambda yes, asked: pd.Series(np.where(~asked, None, np.where(yes, 'Yes', 'No')), index=m.index, dtype=object)
g = pd.DataFrame(index=m.index)
name = m[col('META8')].where(m[col('META8')] != 'Not listed (specify)', m[col('META8_oth')]); g['gvh'] = name.fillna('(unnamed)').astype(str).str.strip(); g['adm3_pcode'] = m['adm3_pcode']
i31 = m[col('INF3.1')].notna(); g['floods_cut_roads'] = yn(m[col('INF3.1', 'Roads / bridges')] == 1, i31)
i32 = m[col('INF3.2')].notna(); g['drought_disrupts_water'] = yn(m[col('INF3.2', 'Water supply')] == 1, i32)
s2 = m[col('SHELT2')].str.split(' - ').str[0]; g['houses_poor_or_worse'] = yn(s2.isin(['Poor condition', 'Very poor condition']), s2.notna())
l3 = m[col('LIV3')].str.split(' - ').str[0]; g['livelihood_poor_or_worse'] = yn(l3.isin(['Poor', 'Very poor']), l3.notna())
c3 = m[col('COP3')]; g['coping_not_enough'] = yn(c3 == 'No, for most households (50% or more)', c3.notna())
f1 = m[col('FOOD1')]; g['food_most_struggle'] = yn(f1.isin(['Most households face difficulties (50% or more)', 'Food markets are inaccessible to all households']), f1.notna())
w1 = m[col('WAT1')]; g['water_most_lack'] = yn(w1.isin(['Most households face difficulties (50% or more)', 'No households are able to obtain sufficient drinking water']), w1.notna())
hf2, hf5 = num(m[col('IDP_HF2')]), m[col('IDP_HF5')]
g['idps_drought_host_families'] = hf2.where(hf5 == 'Drought', 0).fillna(0).astype(int)
g['idps_drought_sites'] = m['_index'].map(st_drought).fillna(0).astype(int)
g['idps_drought_total'] = g.idps_drought_host_families + g.idps_drought_sites
lat = m['gps_lat'].fillna(m['village_lat']); lon = m['gps_lon'].fillna(m['village_lon']); ok = lat.notna() & lon.notna() & (lat != 0)
out = g[ok].reset_index(drop=True)
json.dump(out.where(pd.notna(out), None).to_dict('records'), open('/home/claude/export/gvh_flags.json', 'w'))
print(len(out), out.drop(columns=['gvh', 'adm3_pcode']).apply(lambda s: s.value_counts(dropna=False).to_dict() if s.dtype == object else int(s.sum())).to_dict())
