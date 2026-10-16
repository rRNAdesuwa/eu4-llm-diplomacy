from pathlib import Path
import hashlib, json

ROOT = Path(__file__).resolve().parents[1]
BASE = 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/'
OUT = ROOT / (BASE + 'actual-sealed-r1')
ir = (OUT / 'extended-intake.json').read_bytes(); intake = json.loads(ir)
reads = [{'path': (OUT / 'extended-intake.json').relative_to(ROOT).as_posix(), 'bytes': len(ir)}]

def cached(relative, parse=True):
    path = ROOT / intake['snapshots'][relative]; raw = path.read_bytes()
    assert {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} == intake['source_pins'][relative]
    reads.append({'path': path.relative_to(ROOT).as_posix(), 'bytes': len(raw)})
    return json.loads(raw) if parse else raw.decode()

capture = cached(BASE + 'capture.json'); launcher = cached(BASE + 'launcher-receipt.json')
claim = cached(BASE + 'claim.json'); source = cached(BASE + 'source-manifest.json')
auth = cached(BASE + 'run-authorization.json')
result = {'rows': capture['analysis']['instructions'], 'analysis_without_rows': {k: v for k, v in capture['analysis'].items() if k != 'instructions'},
          'sourcefile_first_last': [capture['source_file_reads'][0], capture['source_file_reads'][-1]],
          'sparse_reads': capture['sparse_reads'], 'whole_PE_reads': capture['full_PE_authentication_reads'],
          'launcher_job': launcher['job'], 'claim': claim,
          'root_tool_witness': cached('work/reports/war-peace-api-20261016-r87-root-actual-authorization/exec-tool-witness.json'),
          'producer_stdout': cached(BASE + 'producer.stdout.txt', False),
          'producer_stderr': cached(BASE + 'producer.stderr.txt', False),
          'original_source_list': list(intake['source_pins']),
          'review_fields': {}, 'reads': reads}
for label in ['upstream_R86_full_review', 'root_raw_frontier_review', 'source_peer_review']:
    value = cached(auth[label]['findings']['path'])
    result['review_fields'][label] = {k: v for k, v in value.items() if k in ['sealed', 'passed', 'blocking_findings', 'scope'] or k.startswith('subject_')}
result['root_acceptance'] = cached(auth['upstream_R86_root_acceptance']['path'])
result['reads'] = reads; result['read_bytes'] = sum(v['bytes'] for v in reads)
with (OUT / 'inspection.json').open('xb') as stream:
    stream.write((json.dumps(result, indent=2, sort_keys=True) + '\n').encode())
for r in result['rows']:
    print(json.dumps({k: v for k, v in r.items() if k in ['rva', 'raw_hex', 'bytes', 'mnemonic', 'op_str', 'size', 'registers_read', 'registers_written', 'regs_read', 'regs_write']}))
print(json.dumps({k: result[k] for k in ['sparse_reads', 'whole_PE_reads', 'launcher_job', 'root_tool_witness', 'producer_stdout', 'producer_stderr', 'review_fields', 'root_acceptance', 'read_bytes']}))
print(json.dumps({'row_keys': list(result['rows'][0]), 'source_read_event_keys': list(capture['source_file_reads'][0]),
                  'parent_read_event_keys': list(launcher['parent_source_reads'][0]), 'claim_keys': list(claim),
                  'analysis': result['analysis_without_rows'], 'original_source_list': result['original_source_list']}))
