import sys, json, collections, os
sys.path.insert(0, os.getcwd())
sys.path.insert(0, 'work/candidates/v32-parameterized-tag-1375')
from unified_api import UnifiedDiplomacyAPI
from bridge.diplomacy_operations import catalog
api = UnifiedDiplomacyAPI()
caps = api.capabilities()
rows = catalog(api)['actions']
print('rows', len(rows))
cnt = collections.Counter()
for r in rows:
    cnt[r.get('route','ordinary_tag')] += 1
print('routes', dict(cnt))
fields = collections.Counter()
for r in rows:
    for f in r.get('parameter_fields', []): fields[f]+=1
print('field union', len(fields))
print(json.dumps(dict(sorted(fields.items())), indent=1))
empty = [r['action'] for r in rows if not r.get('parameter_fields')]
noprof = [r['action'] for r in rows if not r.get('effect_profile')]
print('empty fields', len(empty), empty[:10])
print('no profile', len(noprof), noprof[:10])
