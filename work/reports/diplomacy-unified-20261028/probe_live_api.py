import sys, os, json
sys.path.insert(0, os.getcwd())
from eu4harness import common_diplomacy as cd
layout = cd.Layout()
api = cd.open_api(layout)
print('identity', json.dumps(api.identity))
print('api actions', len(api.actions), 'backend actions', len(api._execution().actions))
for a in ['subject.divert_trade','enforce_peace','offer_loan','influence_nation']:
    print(a, 'in api', a in api.actions, 'in backend', a in api._execution().actions)
samples = {
 'offer_loan': {'request_id':'probe-loan-1','action':'offer_loan','parameters':{'actor':'FRA','target':'BRI','amount':100,'interest_percent':'1.000','duration_months':12}},
 'influence_nation': {'request_id':'probe-infl-1','action':'influence_nation','parameters':{'actor':'FRA','target':'SAV'}},
 'enforce_peace': {'request_id':'probe-enforce-1','action':'enforce_peace','parameters':{'actor':'FRA','target':'ORD','war':{'attacker_leader':'ENG','defender_leader':'ORD'}}},
}
for name, req in samples.items():
    try:
        v = api.validate(req); print(name, 'validate OK', v)
    except Exception as e:
        print(name, 'validate FAIL', type(e).__name__, e)
