import sys, os, json, collections, traceback
sys.path.insert(0, os.getcwd())
sys.path.insert(0, 'work/candidates/v32-parameterized-tag-1375')
from unified_api import UnifiedDiplomacyAPI
from bridge.diplomacy_operations import catalog, query

api = UnifiedDiplomacyAPI()
rows = catalog(api)['actions']

DEFAULTS = {
 'actor':'FRA', 'target':'ENG', 'interest_percent':'5.000', 'rent_multiplier':'1.000',
 'duration_months':12, 'duration_years':10, 'province_id':169, 'price':10,
 'trade_power_percent':10, 'region_id':'france_region', 'area_id':'ile_de_france_area',
 'insult_id':'insult_rival', 'curia_treasury':True, 'accept':True, 'faction_id':'00000001_00000001',
 'army_id':'00000001_00000001', 'fleet_id':'00000001_00000001', 'third_country':'PRO', 'beneficiary':'FRA',
 'taker':'FRA', 'enemy':'SAV', 'enabled':True, 'focus':'aggressive', 'tribute':'cash',
 'subject_type':'vassal', 'play_as_released':False, 'name':'Test', 'adjective':'Testish',
 'parent_request_id':'offline-parent', 'event_instance_id':1, 'event_id':(1<<32)|0x35,
 'option_index':0, 'casus_belli':'cb_conquest', 'call_allies':False, 'war_goal_province':169,
 'terms':[], 'war':{'attacker_leader':'FRA','defender_leader':'ENG'},
}

def params_for(row):
    action, route, fields = row['action'], row.get('route'), row.get('parameter_fields', [])
    if action == 'offer_peace':
        return {'actor':'FRA','target':'ENG','direction':'demand','terms':[]}
    if action == 'declare_war':
        return {'actor':'FRA','target':'ENG','call_allies':False,'casus_belli':'cb_conquest','war_goal_province':169}
    if route == 'typed_government':
        return {'actor':'FRA'}
    if route == 'typed_war_context':
        return {'actor':'FRA','target':'ENG','war':{'attacker_leader':'FRA','defender_leader':'ENG'}}
    p = {}
    for f in fields:
        if f == 'amount':
            p[f] = '100.000' if action == 'give_subsidies' else 100
            continue
        if f == 'direction':
            p[f] = 'demand' if action == 'offer_peace' else 'increase'
        elif f == 'war':
            p[f] = {'attacker_leader':'FRA','defender_leader':'ENG'}
        else:
            p[f] = DEFAULTS.get(f)
    return p

records = []
for i, row in enumerate(rows):
    action = row['action']
    params = params_for(row)
    req = {'request_id': 'offline-%03d' % i, 'action': action, 'parameters': params}
    rec = {'action': action, 'route': row.get('route'), 'parameter_fields': row.get('parameter_fields'),
           'effect_profile': bool(row.get('effect_profile')), 'sample_parameters': params}
    try:
        res = query(api, req)
        rec['query_ok'] = True
        rec['parameters_valid'] = res.get('parameters_valid')
        rec['native_preview'] = res['contract'].get('native_preview')
    except Exception as e:
        rec['query_ok'] = False
        rec['error'] = type(e).__name__ + ': ' + str(e)
    records.append(rec)

by_route = collections.Counter(r['route'] for r in records)
fails = [r for r in records if not r['query_ok']]
summary = {
 'action_count': len(records),
 'by_route': dict(by_route),
 'query_ok': len(records) - len(fails),
 'query_failed': len(fails),
 'missing_effect_profile': [r['action'] for r in records if not r['effect_profile']],
 'native_preview_true': sum(1 for r in records if r.get('native_preview')),
}
out = {'schema':'EU4DIPLOMACYOFFLINECOVERAGE/1','summary':summary,'actions':records}
path = 'work/reports/diplomacy-unified-20261028/offline-coverage.json'
with open(path,'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
for r in fails[:25]:
    print('FAIL', r['action'], '|', r['route'], '|', r['error'][:180])
