from pathlib import Path
import hashlib, json, subprocess, sys, time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/support-heir-current-controller-source-independent-review-20261016-r1'
original = ROOT / 'work/review_support_controller_20261016.py'
replacement = ROOT / 'work/review_support_controller_20261016_r2.py'

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def save(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
    return pin(raw)

raw = original.read_bytes()
failure_raw = (OUT / 'reviewer-seal-failure-r1.json').read_bytes()
failure = json.loads(failure_raw)
assert pin(raw) == failure['source_pin']
assert failure['controller_extra_false_claims'] == ['Frida_called', 'automatic_retry']
assert failure['candidate_extra_false_claims'] == []
text = raw.decode('utf-8')
changes = [
    (" assert set(flags)==set(literal(cli,'FALSE_FLAGS'))",
     " assert set(literal(cli,'FALSE_FLAGS'))<=set(flags)\n assert set(flags)-set(literal(cli,'FALSE_FLAGS'))=={'Frida_called','automatic_retry'}"),
    (" explicit=i['explicit_before_bytes']",
     " failed_raw=(OUT/'reviewer-seal-failure-r1.json').read_bytes();failed=json.loads(failed_raw)\n owned_reads.append({'path':(OUT/'reviewer-seal-failure-r1.json').relative_to(ROOT).as_posix(),'bytes':len(failed_raw)})\n prior_review_upper=failed['failed_attempt_owned_read_upper_bytes']+failed['repair_inspection_read_bytes']\n explicit=i['explicit_before_bytes']"),
    ("  'precision_notes':['Before/after hashes",
     "  'reviewer_failure':{'retained_pin':{'path':(OUT/'reviewer-seal-failure-r1.json').relative_to(ROOT).as_posix(),**pin(failed_raw)},'own_failed_seal_runs':1,'author_fault':False,'correction':'Candidate false flags are a subset; controller adds only Frida_called/automatic_retry, both required false.'},\n  'precision_notes':['Before/after hashes"),
    ("'source_upper_bytes':explicit+2097152", "'prior_review_upper_bytes':prior_review_upper,'source_upper_bytes':explicit+prior_review_upper+2097152"),
    (" assert explicit+2097152<33554432", " assert explicit+prior_review_upper+2097152<33554432"),
    ("'source_upper':explicit+2097152", "'source_upper':explicit+prior_review_upper+2097152"),
    ("Source readiness does not authorize live capture", "The first reviewer seal failed on an overstrict equality check of false-flag sets; its exact source and stderr are retained, and the corrected check accepts only the two additional false claims. No author file or case was changed or rerun. Source readiness does not authorize live capture"),
]
for old, new in changes:
    assert text.count(old) == 1, old
    text = text.replace(old, new, 1)
new_raw = text.encode()
with replacement.open('xb') as stream:
    stream.write(new_raw)
save(OUT / 'reviewer-repair-r2.json', {
    'schema': 'EU4-SUPPORT-CONTROLLER-REVIEWER-CONTINUATION/1',
    'original_source_pin': pin(raw), 'replacement_source_pin': pin(new_raw),
    'failed_seal_record_pin': pin(failure_raw),
    'changes': [{'old': old, 'new': new} for old, new in changes],
    'source_repair_only': True, 'author_changed_or_executed': False,
    'prior_failure_and_inspection_charged_in_final_upper': True,
    'repair_reads_under_manual_allowance': len(raw) + len(failure_raw),
    'new_cases_or_old_tests_reexecuted': False,
})
start = time.perf_counter()
completed = subprocess.run([sys.executable, '-B', str(replacement), 'seal'], cwd=ROOT, capture_output=True)
for name, value in [('reviewer-r2.stdout', completed.stdout), ('reviewer-r2.stderr', completed.stderr)]:
    with (OUT / name).open('xb') as stream:
        stream.write(value)
receipt = {'schema': 'EU4-SUPPORT-CONTROLLER-REVIEWER-R2-RUN/1',
           'source_pin': pin(new_raw), 'exit_code': completed.returncode,
           'elapsed_ms': int((time.perf_counter() - start) * 1000),
           'stdout': pin(completed.stdout), 'stderr': pin(completed.stderr),
           'direct_child_collected': True, 'author_executions': 0,
           'old_tests_or_newcases_executed': 0, 'process_or_game_access': 0}
save(OUT / 'reviewer-r2-receipt.json', receipt)
print(json.dumps(receipt))
print(completed.stdout.decode('utf-8', errors='replace'))
if completed.returncode:
    print(completed.stderr.decode('utf-8', errors='replace'))
raise SystemExit(completed.returncode)
