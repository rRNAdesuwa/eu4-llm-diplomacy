"""File-only integration audit collection. Never publishes or opens EU4."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bridge.tag_command_backend import DEFAULT_MANIFEST, read, decode, encode
from bridge.tag_command_audit import recorded_snapshot

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session-file',type=Path,required=True)
    p.add_argument('--commands',type=Path,default=ROOT/'work/runtime/tag31-integration-20261012.commands.json')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--manifest',type=Path)
    args=p.parse_args()
    identity=decode(read(args.session_file,32768))['identity']
    snapshot=recorded_snapshot(args.manifest or DEFAULT_MANIFEST,identity)
    commands=decode(read(args.commands,65536))
    status=snapshot.status()
    audit=snapshot.raw
    rows=snapshot.rows
    outcomes=[snapshot.status(c['request_id']) for c in commands]
    report=dict(schema='EU4TAG31-INTEGRATION/1',file_only=True,identity=identity,
                planned=len(commands),native_results=len(status['results']),terminal=status['terminal'],
                audit_sha256=hashlib.sha256(audit).hexdigest(),
                states=dict(Counter(r['state'] for r in outcomes)),
                reasons=dict(Counter(r['native_result']['reason'] if r['native_result'] else 'no_result' for r in outcomes)),
                native_call_begins=sum(r['event']=='native_call_begin' for r in rows),
                native_exceptions=[r for r in rows if r['event']=='native_call_return' and (not r['normal'] or r['exception'])],
                nonplayer_dispatched=[r['command'] for r in outcomes if r['state']=='dispatched' and not r['binding']['actor_is_human_player']],
                gameplay_effects_verified=False,AI_acceptance_verified=False,
                results=outcomes,unknown_must_not_be_retried=True,
                evidence_only=True,source_pins_verified=False,partial_audit_tail=audit!=snapshot.complete)
    with args.output.open('xb') as f:f.write(encode(report))
    print(json.dumps({k:v for k,v in report.items() if k not in ('results','nonplayer_dispatched')}|{'nonplayer_dispatched_count':len(report['nonplayer_dispatched'])}))

if __name__=='__main__':main()
