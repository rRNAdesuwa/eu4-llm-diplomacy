"""Archive the v9 same-process experiment; requires all runtime evidence."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.protocol import parse_file
from local_config import user_data

native = ROOT / 'work/native'
runtime = ROOT / 'work/runtime'
events = [json.loads(line) for line in (native / 'probe.jsonl').read_text(
    encoding='utf-8').splitlines() if line.strip()]
install = next(e for e in reversed(events) if e['event']=='automated_diplomacy_installed')
assert install['version']==9
settlement = json.loads((runtime / 'automatic-cycle-settlement.json').read_text(encoding='utf-8'))
before = json.loads((runtime / 'v9-war-pair-before-peace.json').read_text(encoding='utf-8'))
assert before['pid']==settlement['pid']==install['pid']
assert all(c['pair_at_war'] for c in before['countries'])
assert settlement['both_pair_at_peace'] and settlement['player_slot']==189
assert any(e['event']=='test_winwars_fixture_applied' and e['player_restored'] for e in events)
assert any(e['event']=='llm_authorized_peace_execute_entry' and e['state_raw']==2
           and e['authorization']==2 for e in events)
parsed = parse_file(user_data() / 'logs/game.log')
ack = next(a.to_dict() for a in parsed.acks if a.request_id=='war_auto_01' and a.status=='applied')
observe_ack = next(a for a in parsed.acks if a.request_id=='war_observe' and a.status=='applied')
snapshot = next(s.to_dict() for s in reversed(parsed.snapshots)
                if s.snapshot_id=='live' and s.line_end < observe_ack.line)
assert all(snapshot['fields'][key]=='1' for key in ('ai','war','locked'))
report = {'version':9, 'pid':install['pid'], 'same_process':True,
          'dll_sha256':hashlib.sha256((native/'eu4_bridge_automated_diplomacy_v9.dll').read_bytes()).hexdigest(),
          'war_ack':ack, 'war_snapshot':snapshot, 'before_peace':before,
          'after_peace':settlement, 'native_authorization':2,
          'test_winwars':True, 'natural_war_acceptance':False,
          'manual_time_advance':True, 'save_reload_verified':False}
(runtime/'v9-cycle-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(runtime/'v9-cycle-native.jsonl').write_bytes((native/'probe.jsonl').read_bytes())
print(json.dumps({'same_process_cycle_verified':True,'pid':install['pid']}))
