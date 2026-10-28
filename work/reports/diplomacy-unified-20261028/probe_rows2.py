import sys, os, json
sys.path.insert(0, os.getcwd())
sys.path.insert(0, 'work/candidates/v32-parameterized-tag-1375')
from unified_api import UnifiedDiplomacyAPI
from bridge.diplomacy_operations import catalog
api = UnifiedDiplomacyAPI()
for r in catalog(api)['actions']:
    route = r.get('route') or r.get('route','ordinary_tag')
    if route != 'ordinary_tag':
        print(r['action'],'|',route,'|fields:',','.join(r.get('parameter_fields',[])),'|profile:',bool(r.get('effect_profile')))
