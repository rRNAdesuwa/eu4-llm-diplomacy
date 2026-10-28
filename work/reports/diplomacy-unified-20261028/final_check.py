import sys, os, json
sys.path.insert(0, os.getcwd())
from eu4harness import common_diplomacy as cd
layout = cd.Layout(); api = cd.open_api(layout)
print(json.dumps({'identity': api.identity, 'api_actions': len(api.actions), 'backend_actions': len(api._execution().actions)}))
for rid in ('unified-live-loan-01','unified-live-infl-01'):
    try: print(rid, json.dumps(api.status(rid), ensure_ascii=False)[:400])
    except Exception as e: print(rid, 'ERR', type(e).__name__, e)
print('host_state', json.dumps(cd.host_state(api), ensure_ascii=False)[:400])
