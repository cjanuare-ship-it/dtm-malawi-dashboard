#!/usr/bin/env python3
"""
Prepare the RE2CLID dashboard layers as GeoJSON, ready to add to the GIS workspace by hand.

  python prep_dashboard_layers.py <input folder> <output folder>

The input folder holds the layers as GeoJSON (as exported from the workspace, or newer versions with the
same field names). The script:
  1. pools every Group Village Headman (GVH) point layer into one GVH table (joined on adm3_pcode + gvh);
  2. builds "Dashboard summary by district" and "Dashboard summary by TA": one row per district / TA with
     every figure the Dashboard side panels show (counts, totals, and yes/asked pairs for percentages so
     they add up correctly from TA to district to all districts);
  3. adds the matching summary fields to the district-level and TA-level layers;
  4. adds ready-made class fields for styling (for example idp_total_class).
Only the standard library is used.
"""
import json, os, re, sys, math, collections

def load(folder):
    L = {}
    for fn in sorted(os.listdir(folder)):
        if fn.lower().endswith(('.geojson', '.json')) and not fn.endswith('_style.json'):
            try: d = json.load(open(os.path.join(folder, fn), encoding='utf-8'))
            except Exception: continue
            if isinstance(d, dict) and d.get('type') == 'FeatureCollection': L[fn] = d
    return L
def fields(fc): return set().union(*[set(f['properties'] or {}) for f in fc['features'][:50]]) if fc['features'] else set()
def num(v):
    try: x = float(v); return None if math.isnan(x) or x in (-999, -99) else x
    except (TypeError, ValueError): return None
def rnd(x): return None if x is None else int(math.floor(x + 0.5))

def gvh_table(L):
    """one row per GVH, merging the fields of every GVH point layer"""
    rows = collections.OrderedDict()
    for fc in L.values():
        if not {'gvh', 'adm3_pcode'} <= fields(fc): continue
        if not fc['features'] or (fc['features'][0].get('geometry') or {}).get('type') != 'Point': continue
        for f in fc['features']:
            p = f['properties']; k = (p.get('adm3_pcode'), p.get('gvh'))
            r = rows.setdefault(k, {}); r.update({a: b for a, b in p.items() if b is not None or a not in r})
    return list(rows.values())

def layer_with(L, *need):
    for fn, fc in L.items():
        if set(need) <= fields(fc): return fc
    return None

# percentages pooled from the TA indicator layer: (yes field to write, percent field, base count field)
POOLED = [('roads_cut_yes', 'flood_disrupts_roads_pct', 'flood_disrupts_n', 'roads_cut_asked'),
          ('housing_poor_yes', 'housing_poor_or_worse_pct', 'housing_n', 'housing_asked'),
          ('ews_receive_yes', 'ews_receives_warning_pct', 'ews_n', 'ews_receive_asked'),
          ('ews_in_time_yes', 'ews_warning_in_time_pct', 'ews_in_time_n', 'ews_in_time_asked'),
          ('ews_safe_place_yes', 'ews_evacuation_place_pct', 'ews_evac_n', 'ews_safe_place_asked'),
          ('drought_water_yes', 'drought_disrupts_water_pct', 'drought_disrupts_n', 'drought_water_asked'),
          ('livelihood_poor_yes', 'livelihood_poor_or_worse_pct', 'livelihood_n', 'livelihood_asked'),
          ('coping_not_enough_yes', 'coping_not_sufficient_pct', 'coping_suff_n', 'coping_asked')]
TA_SUMS = [('gvhs_drought_main_displacement', 'gvhs_drought_main_displacement'), ('idps_drought_total', 'idps_drought_displaced_total'),
           ('idps_drought_host_families', 'idps_host_families_drought'), ('idps_drought_sites', 'idps_sites_drought')]

def ta_inputs(L):
    fc = layer_with(L, 'adm3_pcode', 'flood_disrupts_roads_pct')
    out = {}
    if not fc: return out
    for f in fc['features']:
        p = f['properties']; r = {}
        for yes, pf, nf, asked in POOLED:
            v, b = num(p.get(pf)), num(p.get(nf))
            if v is not None and b: r[yes] = rnd(v * b / 100); r[asked] = int(b)
        for k, src in TA_SUMS: r[k] = num(p.get(src))
        out[p['adm3_pcode']] = r
    return out

def bsa_stats(g, tin):
    """every assessment figure the panels show, for one group of GVH rows and the TA rows in the same scope"""
    s = collections.OrderedDict()
    S = lambda f: sum(num(r.get(f)) or 0 for r in g)
    C = lambda pred: sum(1 for r in g if pred(r))
    n = len(g); s['gvhs_assessed'] = n
    s['households'] = rnd(S('households')); s['population'] = rnd(S('population'))
    s['idp_total'] = rnd(S('idp_total')); s['idp_host_families'] = rnd(S('idp_host_families')); s['idp_in_sites'] = rnd(S('idp_in_sites'))
    s['gvhs_with_idps'] = C(lambda r: (num(r.get('idp_total')) or 0) > 0)
    s['gvhs_with_idps_host_families'] = C(lambda r: (num(r.get('idp_host_families')) or 0) > 0)
    s['gvhs_with_idps_in_sites'] = C(lambda r: (num(r.get('idp_in_sites')) or 0) > 0)
    s['gvhs_idps_arrived_2023'] = C(lambda r: r.get('most_idps_arrived_2023') == 'Yes')
    s['gvhs_flood_most_damaging'] = C(lambda r: r.get('flood_most_damaging') == 'Flood')
    s['flood_most_damaging_pct'] = round(100 * s['gvhs_flood_most_damaging'] / n, 1) if n else None
    s['gvhs_flooded_5plus'] = C(lambda r: r.get('flood_events_5y') == '5 or more times')
    s['gvhs_drought_now'] = C(lambda r: r.get('drought_status') == 'Drought ongoing now')
    s['gvhs_drought_12m'] = C(lambda r: r.get('drought_status') == 'Drought in the last 12 months')
    s['gvhs_drought_now_or_12m'] = s['gvhs_drought_now'] + s['gvhs_drought_12m']
    most = lambda f: C(lambda r: bool(re.match(r'^(Most|Severe)', str(r.get(f) or ''))))
    s['gvhs_food_most_struggle'] = most('food_market_difficulty'); s['gvhs_food_asked'] = C(lambda r: r.get('food_market_difficulty') not in (None, ''))
    s['gvhs_water_most_lack'] = most('drinking_water_difficulty'); s['gvhs_water_asked'] = C(lambda r: r.get('drinking_water_difficulty') not in (None, ''))
    for yes, pf, nf, asked in POOLED:
        a = sum(t.get(yes) or 0 for t in tin if t.get(asked)); b = sum(t.get(asked) or 0 for t in tin)
        s[yes] = a if b else None; s[asked] = b if b else None; s[yes.replace('_yes', '_pct')] = round(100 * a / b, 1) if b else None
    for k, _ in TA_SUMS:
        vals = [t.get(k) for t in tin if t.get(k) is not None]; s[k] = rnd(sum(vals)) if vals else None
    return s

IDP_CLASSES = [(0, 0, 'None reported'), (1, 100, '1 – 100'), (101, 500, '101 – 500'), (501, 1000, '501 – 1,000'), (1001, 2000, '1,001 – 2,000'), (2001, 1e12, 'Over 2,000')]
TA_CLASSES = [(0, 0, 'None reported'), (1, 1000, '1 – 1,000'), (1001, 5000, '1,001 – 5,000'), (5001, 10000, '5,001 – 10,000'), (10001, 20000, '10,001 – 20,000'), (20001, 1e12, 'Over 20,000')]
def klass(v, cls):
    v = num(v) or 0
    for a, b, t in cls:
        if a <= v <= b: return t
    return None

def main(src, dst):
    os.makedirs(dst, exist_ok=True); L = load(src)
    g = gvh_table(L); tin = ta_inputs(L)
    prof = layer_with(L, 'district', 'rain_jfm') or layer_with(L, 'district', 'target')
    taL = layer_with(L, 'adm3_pcode', 'flood_disrupts_roads_pct') or layer_with(L, 'adm3_pcode', 'ta', 'gvhs_assessed')
    by_d = collections.defaultdict(list); by_t = collections.defaultdict(list)
    for r in g: by_d[r.get('district')].append(r); by_t[r.get('adm3_pcode')].append(r)
    tas_of = collections.defaultdict(list)
    for f in taL['features']: tas_of[f['properties']['district']].append(f['properties']['adm3_pcode'])
    # district summary: hazard profile fields + assessment figures
    dist = {}
    for f in prof['features']:
        p = dict(f['properties']); d = p['district']
        if by_d.get(d): p.update(bsa_stats(by_d[d], [tin.get(t, {}) for t in tas_of[d]])); p['target_tas'] = len(tas_of[d])
        dist[d] = p
    dfc = {'type': 'FeatureCollection', 'name': 'Dashboard summary by district', 'features': [{'type': 'Feature', 'properties': dist[f['properties']['district']], 'geometry': f['geometry']} for f in prof['features']]}
    # TA summary
    tafc = {'type': 'FeatureCollection', 'name': 'Dashboard summary by TA', 'features': []}
    tarow = {}
    for f in taL['features']:
        p0 = f['properties']; t = p0['adm3_pcode']; p = collections.OrderedDict([('adm3_pcode', t), ('ta', p0.get('ta')), ('district', p0.get('district'))])
        p.update(bsa_stats(by_t.get(t, []), [tin.get(t, {})])); p['idp_total_class'] = klass(p['idp_total'], TA_CLASSES); tarow[t] = p
        tafc['features'].append({'type': 'Feature', 'properties': p, 'geometry': f['geometry']})
    allrow = bsa_stats(g, list(tin.values()))
    json.dump(dfc, open(os.path.join(dst, 'dashboard_summary_by_district.geojson'), 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(tafc, open(os.path.join(dst, 'dashboard_summary_by_ta.geojson'), 'w', encoding='utf-8'), ensure_ascii=False)
    return L, g, dist, tarow, allrow, dfc, tafc

if __name__ == '__main__':
    if len(sys.argv) < 3: print(__doc__); sys.exit(1)
    main(sys.argv[1], sys.argv[2]); print('done')
