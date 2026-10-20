"""Queue one experimental request after bounded read-only envoy preflight.

Requires the already installed authorization experiment. The DLL still checks
its live context, native validity, preview >=100 and authorization selftest.
This tool does not start/restart/inject into EU4 or invoke native methods.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--pid',type=int,required=True)
p.add_argument('--terms', choices=('whitepeace', 'gold'), default='whitepeace')
a=p.parse_args()
root=Path(__file__).parent
snapshot=root/'runtime'/f'guarded-{a.terms}-preflight-{a.pid}-{time.time_ns()}.json'
result=subprocess.run([sys.executable,'-B',str(root/'probe_pending_peace.py'),
                       '--pid',str(a.pid),'--output',str(snapshot)],
                      capture_output=True,text=True,timeout=30)
if result.returncode:
    raise SystemExit(result.stderr or result.stdout)
state=json.loads(snapshot.read_text(encoding='utf-8'))
countries=state['countries']
fra=next(x for x in countries if x['tag']=='FRA')
if countries[-1]['tag']!='POR':
    raise SystemExit('Stop: current player must be POR.')
if not fra.get('available_diplomat_count'):
    raise SystemExit('Stop: FRA has no confirmed available diplomat; no request queued.')
if state['current_raw_date']<=fra['last_sent_raw']:
    raise SystemExit('Stop: FRA native date guard has not cleared.')
if not state['fra_eng_command_date_guard']['passes']:
    raise SystemExit('Stop: FRA->ENG native command relation cooldown has not cleared.')
events=[json.loads(line) for line in (root/'native/probe.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
if not any(x.get('event')=='authorization_selftest_passed' for x in events):
    raise SystemExit('Stop: authorization selftest not found; no request queued.')
request_name = 'gold-peace.request' if a.terms == 'gold' else 'whitepeace.request'
with (root/'native'/request_name).open('x',encoding='ascii') as f:
    f.write(f'guarded {a.terms} diagnostic\n')
print(json.dumps({'queued':True,'terms':a.terms,'pid':a.pid,'available_diplomats':fra['available_diplomat_count'],
                  'snapshot':str(snapshot),'settlement_verified':False}))
