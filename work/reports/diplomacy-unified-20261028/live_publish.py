import sys, os, json, time
sys.path.insert(0, os.getcwd())
from eu4harness import common_diplomacy as cd

req = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
layout = cd.Layout()
api = cd.open_api(layout)
backend = api._execution()
tried = {item['command']['request_id'] for item in backend._intents(backend.session(api.identity))}
if req['request_id'] in tried:
    print(json.dumps({'refused': 'request_id_already_attempted', 'request_id': req['request_id']}))
    raise SystemExit(0)
normalized = api.validate(req)
submission = api.submit_batch([normalized], ttl_ms=60000)
print(json.dumps({'phase': 'submit', 'result': submission}, ensure_ascii=False, default=str))
states = []
deadline = time.time() + 90
last = None
while time.time() < deadline:
    try:
        status = api.status(req['request_id'])
    except Exception as error:
        print(json.dumps({'phase': 'status_error', 'error': type(error).__name__ + ': ' + str(error)}))
        break
    state = status.get('status') or status.get('native_state')
    if state != last:
        states.append({'t': round(time.time(), 1), 'status': state, 'reason': status.get('reason')})
        print(json.dumps({'phase': 'status', 'status': state, 'reason': status.get('reason')}))
        last = state
    if state in ('dispatched', 'rejected', 'dispatch_unknown'):
        break
    time.sleep(3)
out = {'request': normalized, 'submission': submission, 'status_states': states, 'final': last}
path = 'work/reports/diplomacy-unified-20261028/live-' + req['request_id'] + '.json'
open(path, 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=1, default=str))
print(json.dumps({'written': path, 'final': last}))
