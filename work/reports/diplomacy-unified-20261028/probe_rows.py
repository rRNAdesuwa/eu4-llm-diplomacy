import sys, os, json
sys.path.insert(0, os.getcwd())
sys.path.insert(0, 'work/candidates/v32-parameterized-tag-1375')
from unified_api import UnifiedDiplomacyAPI
from bridge.diplomacy_operations import catalog
api = UnifiedDiplomacyAPI()
rows = catalog(api)['actions']
for r in rows:
    extra = [f for f in r.get('parameter_fields',[]) if f not in ('actor','target')]
    if extra or r.get('route') not in ('ordinary_tag',):
        print(r['action'], '|', r.get('route'), '|', ','.join(r.get('parameter_fields',[])), '| prof=', bool(r.get('effect_profile')))
