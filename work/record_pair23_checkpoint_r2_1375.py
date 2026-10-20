"""One-use, file-only V23 completed-audit checkpoint. No process/native access."""
import hashlib, importlib.util, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/runtime/pair23-checkpoint-r2-20261012a'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def put(path, data):
    with path.open('xb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())

def main():
    assert sys.flags.isolated == 1
    OUT.mkdir(exist_ok=False)
    runner_path = ROOT / 'work/run_pair23_session_1375.py'
    spec = importlib.util.spec_from_file_location('pair23_root_recorder', runner_path)
    runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
    client = runner.verified_client()
    manifest = client.manifest()
    identity = client.identity(runner.PID, runner.CREATION,
        'f9f96b8607268273594fcf942afdb94d', manifest)
    result = client.inspect(identity)  # file-only; never load, publish, or census
    assert result['complete'] is True and result['terminal'] is False
    assert result['pending_native_call'] is None and len(result['results']) == 6
    encoded = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode('ascii')
    put(OUT / 'completed-audit.json', encoded)
    rows = result['rows']
    native = [r for r in rows if r['event'] == 'native_call_begin']
    returns = [r for r in rows if r['event'] == 'native_call_return']
    assert len(native) == len(returns)
    assert all(r['normal'] is True and r['exception'] == 0 for r in returns)
    assert all(r['known_cleanup_complete'] is True and r['owned_live'] == 0
               and r['quarantined'] == 0 and r['submitted'] is False
               for r in result['results'])
    initial = json.loads((runner.OUT / 'initial.json').read_bytes())
    premature = json.loads((runner.OUT / 'final.json').read_bytes())
    assert initial['equal'] is True and premature['equal'] is True
    early = json.loads((runner.OUT / 'inspect.stdout').read_bytes())
    assert early['complete'] is False
    report = dict(schema='EU4PAIR23CHECKPOINT/1', identity=identity,
        complete_no_send_lifecycles=True, native_calls=len(native),
        native_returns=len(returns), audit_rows=len(rows),
        outcomes=[dict(sequence=r['sequence'], status=r['status'], reason=r['reason'],
                       calls=r['adapter_call_attempts'], issued=r['owned_issued'],
                       live=r['owned_live'], cleanup=r['known_cleanup_complete'])
                  for r in result['results']],
        initial_and_premature_selected_samples_equal=initial['passes']==premature['passes'],
        final_json_is_premature=True, completed_batch_final_effects_sample=False,
        effects_not_resampled=True, gameplay_effects_verified=False,
        sender_called=False, production_ready=False,
        observations='First inspect was incomplete. final.json was taken without a completed-audit guard; it is retained as a premature sample, not completed-batch evidence. This checkpoint only rereads files.',
        completed_audit_sha256=sha(encoded), recorder_sha256=sha(Path(__file__).read_bytes()),
        initial_sha256=sha((runner.OUT/'initial.json').read_bytes()),
        premature_sample_sha256=sha((runner.OUT/'final.json').read_bytes()),
        early_audit_sha256=sha((runner.OUT/'inspect.stdout').read_bytes()))
    put(OUT / 'report.json', (json.dumps(report, indent=2, sort_keys=True)+'\n').encode('ascii'))
    print(json.dumps(report, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
