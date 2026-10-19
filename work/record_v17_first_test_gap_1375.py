"""Preserve a stopped research run with its genuine missing preflight evidence."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.native import lab_protocol_v17_1375 as lab

PID, CREATION = 22784, '01dd56bf28902f93'
EXPECTED_LOG = '1bf543437f138ac1e32d65eae5d29d54656a3f8f4f9d1b99ab15a3d77d8e73bf'


def descriptor(path, maximum=2 * 1024 * 1024):
    raw = lab.read_bounded(path, maximum)
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    session = lab.OUTPUT / f'session-{PID}-{CREATION}'
    exit_path = lab.OUTPUT / 'exit-observation-22784-r2.json'
    exited = json.loads(lab.read_bounded(exit_path, 65536))
    assert exited['pid'] == PID and exited['creation'] == CREATION
    assert exited['exit_observed'] is True and exited['exit_code'] == 0
    metadata = lab.read_session_metadata(session, PID, CREATION)
    evidence = lab.read_evidence(session, metadata)
    assert evidence['log_sha256'] == EXPECTED_LOG
    assert evidence['last_sequence'] == 11 and set(evidence['requests']) == set(range(1, 12))
    assert evidence['pending'] is False and evidence['lease_pending'] is False
    assert evidence['latest_frame']['session_frozen'] is False
    inventory = {p.name: descriptor(p) for p in sorted(session.iterdir())}
    assert len(inventory) <= 128
    requests = []
    for seq, request in evidence['requests'].items():
        assert type(request['complete']) is dict
        records = request['records']
        assert all(r.get('freeze_session', False) is False
                   and r.get('ownership_uncertain', False) is False
                   and r.get('exception', 0) == 0 for r in records)
        requests.append({'sequence': seq, 'request': request['request'],
                         'complete': request['complete'],
                         'last_native': records[-1],
                         'lease_complete': request.get('lease_complete')})
    comparisons = {}
    for label in ('offer-fleet', 'revoke-fleet', 'insult'):
        path = lab.OUTPUT / f'{label}-comparison-{PID}.json'
        value = json.loads(lab.read_bounded(path, 65536))
        assert value['observed_effect'] is True and value['runtime_verified'] is False
        comparisons[label] = {'input': descriptor(path), 'observed_selected_transition': True,
                              'promoted': False}
    assert inventory == {p.name: descriptor(p) for p in sorted(session.iterdir())}
    report = {'schema_version': 1, 'purpose': 'stopped_v17_research_run_with_preflight_gap',
              'pid': PID, 'creation': CREATION, 'exit': descriptor(exit_path),
              'status': 'preserved_research_evidence_audit_incomplete',
              'missing_evidence': 'Independent complete after-stages RO diagnostic before fixture/request1',
              'retrospective_substitute_created': False, 'session_files': inventory,
              'requests': requests, 'selected_comparisons': comparisons,
              'latest_frame': evidence['latest_frame'],
              'preflight_approved': False, 'runtime_verified': False,
              'capability_promoted': False, 'production_ready': False}
    output = lab.OUTPUT / 'first-test-preflight-gap-22784.json'
    with output.open('x', encoding='utf-8', newline='\n') as dst:
        json.dump(report, dst, indent=2); dst.write('\n')
    print(json.dumps({'output': str(output), 'sha256': descriptor(output)['sha256'],
                      'requests': len(requests), 'selected_transitions': len(comparisons),
                      'preflight_approved': False}))


if __name__ == '__main__':
    main()
