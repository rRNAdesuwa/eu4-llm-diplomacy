from pathlib import Path
import hashlib, json, subprocess, sys, time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/actual-sealed-r1'
old = ROOT / 'work/seal_r87_actual_20261016.py'
new = ROOT / 'work/seal_r87_actual_20261016_r2.py'

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def save(name, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    with (OUT / name).open('xb') as stream:
        stream.write(raw)
    return pin(raw)

raw = old.read_bytes(); failure_raw = (OUT / 'seal-failure-r1.json').read_bytes(); failure = json.loads(failure_raw)
assert pin(raw) == failure['source_pin']
text = raw.decode()
changes = [
    ("        assert capture['review_pins'][label] == auth[label]",
     "        for fixed_review in auth[label].values():\n            assert capture['review_pins'][fixed_review['path']] == {k: fixed_review[k] for k in ('bytes', 'sha256')}"),
    ("    assert capture['review_pins']['upstream_R86_root_acceptance'] == auth['upstream_R86_root_acceptance']",
     "    fixed_acceptance = auth['upstream_R86_root_acceptance']\n    assert capture['review_pins'][fixed_acceptance['path']] == {k: fixed_acceptance[k] for k in ('bytes', 'sha256')}\n    assert len(capture['review_pins']) == 7"),
    ("    source_upper = explicit + 2097152",
     "    own_failure_raw = (OUT / 'seal-failure-r1.json').read_bytes(); own_failure = decode(own_failure_raw)\n    source_upper = explicit + own_failure['conservative_failed_seal_owned_read_upper'] + 2097152"),
    ("                                            'explicit_source_and_owned_read_bytes': explicit,",
     "                                            'explicit_source_and_owned_read_bytes': explicit,\n                                            'prior_failed_seal_upper': own_failure['conservative_failed_seal_owned_read_upper'],\n                                            'prior_failed_seal_pin': {'path': (OUT / 'seal-failure-r1.json').relative_to(ROOT).as_posix(), **pin(own_failure_raw)},\n                                            'failure_note': 'Own flat review-pin schema assumption failed before canonical writes; R2 changes only field mapping and accounting. No acquisition repeated.',"),
    ("    report = '''# R87 retained actual author contract",
     "    report = '''# R87 retained actual author contract\n\nThe first author sealer failed before canonical output on its own review-pins schema assumption. Exact failed source and tool stderr text are retained; R2 uses the actual flat path-to-pin mapping and charges a conservative failed-read upper. Producer/source/capture were unchanged and acquisition was not repeated."),
]
for before, after in changes:
    assert text.count(before) == 1, before
    text = text.replace(before, after, 1)
new_raw = text.encode()
with new.open('xb') as stream:
    stream.write(new_raw)
save('seal-r2-continuation.json', {'schema': 'EU4-R87-RETAINED-SEAL-CONTINUATION/1',
                                 'old_source_pin': pin(raw), 'new_source_pin': pin(new_raw), 'failed_record_pin': pin(failure_raw),
                                 'changes': [{'before': b, 'after': a} for b, a in changes],
                                 'exact_source_repair_reads_within_manual_allowance': len(raw) + len(failure_raw),
                                 'producer_or_decoder_reexecuted': False, 'canonical_sources_modified': False,
                                 'failed_reads_charged': True})
start = time.perf_counter()
completed = subprocess.run([sys.executable, '-B', str(new), 'seal'], cwd=ROOT, capture_output=True)
for name, value in [('seal-r2.stdout', completed.stdout), ('seal-r2.stderr', completed.stderr)]:
    with (OUT / name).open('xb') as stream:
        stream.write(value)
receipt = {'schema': 'EU4-R87-RETAINED-SEAL-R2-RUN/1', 'source_pin': pin(new_raw), 'exit_code': completed.returncode,
           'elapsed_ms': int((time.perf_counter() - start) * 1000), 'stdout': pin(completed.stdout), 'stderr': pin(completed.stderr),
           'direct_child_collected': True, 'actual_acquisition_reexecuted': False, 'PE_engine_decoder_game_access': 0}
save('seal-r2-receipt.json', receipt)
print(json.dumps(receipt)); print(completed.stdout.decode('utf-8', errors='replace'))
if completed.returncode:
    print(completed.stderr.decode('utf-8', errors='replace'))
raise SystemExit(completed.returncode)
