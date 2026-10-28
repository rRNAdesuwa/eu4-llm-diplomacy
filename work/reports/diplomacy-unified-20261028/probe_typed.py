import sys, os, json
sys.path.insert(0, os.getcwd())
sys.path.insert(0, 'work/candidates/v32-parameterized-tag-1375')
from unified_api import UnifiedDiplomacyAPI
from bridge.diplomacy_operations import catalog
api = UnifiedDiplomacyAPI()
caps = api.capabilities()
for k in ['typed_confirm_tribute','typed_governor_choice','typed_war_context','typed_condottieri','typed_sell_ships','typed_rebels','typed_government','typed_war','typed_peace']:
    print('==',k)
    print(json.dumps(caps.get(k), ensure_ascii=False)[:1200])
print('== rows typed')
for r in catalog(api)['actions']:
    if r.get('route','ordinary_tag') not in ('ordinary_tag',):
        print(r['action'],'|',r.get('route'),'|',','.join(r.get('parameter_fields',[])))
