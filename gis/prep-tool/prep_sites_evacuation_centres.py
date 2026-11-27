import pandas as pd, json, math, re, difflib
w=json.load(open('/home/claude/src24/ws24_full.json'))
adm3={}
for l in w['layers']:
    if l['name'].startswith('Traditional Authorities (TAs), administrative'):
        for p in l['props']: adm3[p['adm3_pcode']]=(p['ta'],p['district'])
TGT=['Blantyre','Blantyre City','Chikwawa','Dowa','Mangochi','Mulanje','Nsanje','Phalombe']
d=pd.read_excel('sites.xlsx',sheet_name=0,dtype=str)
d=d[d['grp_C/SITE8'].notna()]
BT={'school':'School','church':'Church','community_centre':'Community centre or public building','clinic':'Health facility','open_space':'Open space','private':'Private property','mosque':'Mosque','other':'Other'}
USE={'current':'In use as a site now','historical':'Used in past emergencies, not now','never':'Never used yet'}
COND={'good':'Good','fair':'Fair','poor':'Poor','very_poor':'Very poor'}
FL={'yes':'Yes','partly':'Partly','no':'No'}
EV={'freddy_2023':'Cyclone Freddy 2023','ana_2022':'Tropical Storm Ana 2022','idai_2019':'Cyclone Idai 2019','floods_2015':'Floods 2015','other':'Other events'}
ORDER=list(EV)
def dist(s): return {'blantyre_city':'Blantyre City'}.get(s, s.replace('_',' ').title())
def num(v):
    try: x=float(v); return None if math.isnan(x) else int(round(x))
    except: return None
feats=[]
for _,r in d.iterrows():
    ta_code=str(r['grp_A/SITE4']); pc='MW'+ta_code[2:] if ta_code.startswith('TA') else None
    ta,dd=adm3.get(pc,(None,None)); di=dist(r['grp_A/SITE3'])
    ev=str(r['grp_C/SITE14']).split() if isinstance(r['grp_C/SITE14'],str) else []
    ev=[EV[e] for e in ORDER if e in ev]
    bt=BT.get(r['grp_C/SITE8a'],'Other'); spec=r['grp_C/SITE8b'] if isinstance(r['grp_C/SITE8b'],str) else ''
    sid=r['grp_B/SITE_ID'] if isinstance(r['grp_B/SITE_ID'],str) and r['grp_B/SITE_ID'].startswith('MWI-SITE') else ''
    p={'site_name':str(r['grp_B/SITE_NAME_FINAL']).strip(),
       'site_type':'Government-led evacuation centre' if r['grp_C/SITE8']=='evac_centre' else 'Collective site',
       'building_type':bt,'building_type_details':spec.strip(),
       'district':di,'ta':ta or '', 'adm3_pcode':pc or '',
       'village':str(r['grp_A/SITE6']).strip() if isinstance(r['grp_A/SITE6'],str) else '',
       'use_status':USE.get(r['grp_C/SITE11'],''),
       'idp_households_now':num(r['grp_C/SITE12']) or 0,'idp_people_now':num(r['grp_C/SITE13']) or 0,
       'capacity_households':num(r['grp_C/SITE15']),
       'physical_condition':COND.get(r['grp_C/SITE9'],''),
       'floods_or_cut_off':FL.get(r['grp_C/SITE16'],''),
       'emergencies_used_in':'; '.join(ev),'used_cyclone_freddy_2023':'Yes' if 'Cyclone Freddy 2023' in ev else 'No',
       'dtm_site_id':sid,'mapping_date':str(r['grp_A/META1'])[:10],
       'recorded_in':'DTM site and evacuation centre mapping','location_from':'GPS taken at the site',
       'girls_now':None,'boys_now':None,'women_now':None,'men_now':None,'older_women_now':None,'older_men_now':None,
       'idps_came_from_district':'','main_reason_idps_left':'','idps_arrived_year':None}
    lat,lon=float(r['grp_B/_SITE7_latitude']),float(r['grp_B/_SITE7_longitude'])
    feats.append({'type':'Feature','geometry':{'type':'Point','coordinates':[round(lon,6),round(lat,6)]},'properties':p})
print('mapping', len(feats))
# GVH key informant sites
g=pd.read_excel('gvh.xlsx',sheet_name=0,dtype=str); st=pd.read_excel('gvh.xlsx',sheet_name='st_repeat',dtype=str)
col=lambda df,pre:[c for c in df.columns if c.startswith(pre)][0]
c3=col(st,'IDP_ST3.'); co=col(st,'IDP_ST3_oth'); c4=col(st,'IDP_ST4.'); 
keep=st[(st[c3].isin(['Collective centre','Government-led evacuation centre']))|((st[c3]=='Other')&(st[co].fillna('').str.lower().str.contains('collective')))]
gi=g.set_index('_index')
BT2={'School or other educational facility':'School','Religious facility (church, mosque)':'Church or mosque','Community / public building':'Community centre or public building'}
def hav(a,b): 
    R=6371; la1,lo1,la2,lo2=map(math.radians,[a[1],a[0],b[1],b[0]]); return 2*R*math.asin(math.sqrt(math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2))
norm=lambda s:re.sub(r'\b(camp|evacuation|centre|center|primary|school|church|ccap|the)\b','',re.sub(r'[^a-z ]',' ',s.lower())).split()
added=matched=0
for _,s in keep.iterrows():
    pr=gi.loc[s['_parent_index']]
    lat=float(pr['_META9. Record the GPS location_latitude']); lon=float(pr['_META9. Record the GPS location_longitude'])
    di=pr['META6. Assessment location - district (ADM2)']; pc=pr['adm3_pcode']; ta=adm3.get(pc,('',''))[0]
    gvh=pr['META8. Assessment location - GVH (ADM4)'] if isinstance(pr['META8. Assessment location - GVH (ADM4)'],str) and pr['META8. Assessment location - GVH (ADM4)']!='other' else pr.get('META8_oth. Name of the GVH (not on the list)','')
    name=str(s[col(st,'IDP_ST2.')]).strip()
    typ='Government-led evacuation centre' if s[c3]=='Government-led evacuation centre' else 'Collective site'
    ki={'girls_now':num(s[col(st,'IDP_ST7.1')]),'boys_now':num(s[col(st,'IDP_ST7.2')]),'women_now':num(s[col(st,'IDP_ST7.3')]),'men_now':num(s[col(st,'IDP_ST7.4')]),
        'older_women_now':num(s[col(st,'IDP_ST7.5')]),'older_men_now':num(s[col(st,'IDP_ST7.6')]),
        'idps_came_from_district':s[col(st,'IDP_ST8.2')] if isinstance(s[col(st,'IDP_ST8.2')],str) else '',
        'main_reason_idps_left':s[col(st,'IDP_ST9.')] if isinstance(s[col(st,'IDP_ST9.')],str) else '',
        'idps_arrived_year':num(s[col(st,'IDP_ST10.1')])}
    hh=num(s[col(st,'IDP_ST5.')]) or 0; pp=num(s[col(st,'IDP_ST6.')]) or 0
    # match a mapped site
    best=None
    for f in feats:
        P=f['properties']
        if P['recorded_in']!='DTM site and evacuation centre mapping' or P['district']!=di: continue
        dk=hav(f['geometry']['coordinates'],[lon,lat]); 
        if dk>4: continue
        a,b=' '.join(norm(name)),' '.join(norm(P['site_name']))
        sim=difflib.SequenceMatcher(None,a,b).ratio() if a and b else 0
        if sim>=.75 and (best is None or sim>best[0]): best=(sim,f)
    if best:
        P=best[1]['properties']; matched+=1; print('match',name,'->',P['site_name'],round(best[0],2))
        P.update(ki); P['recorded_in']='Both: site mapping and GVH assessment'
        if not P['idp_people_now'] and pp: P['idp_people_now']=pp; P['idp_households_now']=hh
        continue
    p={'site_name':name,'site_type':typ,'building_type':BT2.get(s[c4],'Other') if isinstance(s[c4],str) else ('Government-led evacuation centre' if typ.startswith('Gov') else 'Other'),'building_type_details':'',
       'district':di,'ta':ta,'adm3_pcode':pc,'village':gvh or '','use_status':'In use as a site now' if pp else '',
       'idp_households_now':hh,'idp_people_now':pp,'capacity_households':None,'physical_condition':'','floods_or_cut_off':'',
       'emergencies_used_in':'','used_cyclone_freddy_2023':'','dtm_site_id':'','mapping_date':str(pr['today'] if 'today' in pr else pr['start'])[:10],
       'recorded_in':'DTM GVH baseline assessment (key informants)','location_from':'GPS of the GVH where it was reported (approximate)'}
    p.update(ki); added+=1
    feats.append({'type':'Feature','geometry':{'type':'Point','coordinates':[round(lon,6),round(lat,6)]},'properties':p})
print('ki added',added,'matched',matched,'total',len(feats))
fc={'type':'FeatureCollection','features':[f for f in feats if f['properties']['district'] in TGT]}
print('in targets',len(fc['features']))
import collections
print(collections.Counter((f['properties']['district'],f['properties']['site_type']) for f in fc['features']))
print(collections.Counter(f['properties']['use_status'] for f in fc['features']))
print('no ta',[f['properties']['site_name'] for f in fc['features'] if not f['properties']['ta']])
json.dump(fc,open('/home/claude/export/collective_sites_evacuation_centres.geojson','w'),ensure_ascii=False)

# ---- then: Traditional Authority from the GPS point (OCHA ADM3) for the mapped sites
import geopandas as gpd, json
fc=json.load(open('/home/claude/export/collective_sites_evacuation_centres.geojson'))
a=gpd.read_file('/home/claude/data/cod/TCV_MAPs_CEA/geographic_maps/mwi_adm_nso_hotosm_20230405_shp/mwi_admbnda_adm3_nso_hotosm_20230405.shp')[['ADM3_EN','ADM3_PCODE','ADM2_EN','geometry']]
g=gpd.GeoDataFrame.from_features(fc['features'],crs=4326); j=gpd.sjoin(g,a,how='left',predicate='within')
n=0
for i,f in enumerate(fc['features']):
    P=f['properties']; r=j.iloc[i]
    if P['recorded_in'].startswith('DTM GVH'): continue
    dn=str(r.ADM2_EN).replace(' City','') if False else str(r.ADM2_EN)
    if r.ADM3_PCODE and dn==P['district'] and r.ADM3_PCODE!=P['adm3_pcode']: P['ta']=r.ADM3_EN; P['adm3_pcode']=r.ADM3_PCODE; n+=1
print('relocated',n)
json.dump(fc,open('/home/claude/export/collective_sites_evacuation_centres.geojson','w'),ensure_ascii=False)
