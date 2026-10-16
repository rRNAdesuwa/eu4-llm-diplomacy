"""Root production decision after the fixed complete non-author source review."""
from pathlib import Path, PurePosixPath
import copy
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUTREL = 'work/reports/peace-current-pending-v2-production-review-20261016-r1'
OUT = ROOT / OUTREL
CAND = 'work/candidates/peace-current-pending-observer-1375-v2/'
REV = 'work/reports/peace-current-pending-v2-independent-review-20261016-r1/'
LIMIT = 16 * 1024 * 1024
events = []
before = {}

def pin(b):
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}

def read(rel, phase):
    p = PurePosixPath(rel)
    assert not p.is_absolute() and '..' not in p.parts and p.as_posix() == rel
    path = ROOT / rel
    assert path.resolve().is_relative_to(ROOT.resolve())
    assert path.stat().st_size <= 4194304
    b = path.read_bytes()
    events.append({'path': rel, 'phase': phase, **pin(b)})
    assert sum(x['bytes'] for x in events) + 2097152 < LIMIT
    return b

fixed = {
 REV+'findings.json': (6951, '62e95ab8af0fda65f43a89f23365e8893753b2c7e07b36b8ff4c818ddd936b82'),
 REV+'manifest.json': (28991, 'dc10f5c559b49b38ceb6fa8303460731b4d0fc2d9850044aff0eff7eafac9a6b'),
 REV+'verification.json': (605, '70c54a8ac44cb7be8fd51cdcb8ea1cee6a36cf59c6e5f8d6a4a3495cdd41eaeb'),
 REV+'completion.json': (2862, '40076ace4dd359e8a3c01b04b736f138f1f5e5b004f4554943180a128b61c5b6'),
 REV+'publication-manifest.json': (3611, '370150d169ff2fcbd70b7138bd6b60e86fbe34bec8bc2be5715a2c29f30f5349'),
 CAND+'source-manifest.json': (8428, '6a4c081d3709d734eee90b9c19f9da535620cd56665e4fcb02cc6270871ab2a0'),
 CAND+'source-manifest.draft.json': (8428, '6a4c081d3709d734eee90b9c19f9da535620cd56665e4fcb02cc6270871ab2a0'),
 CAND+'peace_current_pending.py': (24249, '94faa085cc982230717f42b43b24bd777a26493a0cf18d2dc3c2cbfc23a7491d'),
}
assert not OUT.exists()
for rel, (n, h) in fixed.items():
    b = read(rel, 'fixed_before')
    assert pin(b) == {'bytes': n, 'sha256': h}, rel
    before[rel] = b
review = json.loads(before[REV+'findings.json'])
draft = json.loads(before[CAND+'source-manifest.draft.json'])
assert before[CAND+'source-manifest.json'] == before[CAND+'source-manifest.draft.json']
assert review['sealed'] and review['passed'] and review['source_ready']
assert review['blocking_findings'] == [] and review['approved_for_current_readonly_status'] is False
assert review['production_approved'] is False and all(x is False for x in review['authority'].values())
graph = draft['source_pins']
assert len(graph) == 41
assert hashlib.sha256(json.dumps(graph, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest() == draft['source_graph_sha256']
assert draft['source_graph_sha256'] == review['subject_source_graph_sha256'] == '5df0dcb56da6629ebbe9f3585ff6f10d120d66d903354be05887dcea9dc67a82'
assert review['subject_cli_pin'] == graph[CAND+'peace_current_pending.py'] == pin(before[CAND+'peace_current_pending.py'])
assert not draft['sealed'] and not draft['runtime_capture_authorized']
assert draft['independent_source_review'] is None and draft['production_review'] is None
for key, value in review.items():
    if key.startswith('subject_') and isinstance(value, dict) and set(value) == {'path', 'bytes', 'sha256'}:
        rel = value['path']
        if rel not in before:
            before[rel] = read(rel, 'review_subject_before')
        assert pin(before[rel]) == {k: value[k] for k in ('bytes', 'sha256')}, key
for rel, expected in graph.items():
    assert set(expected) == {'bytes', 'sha256'} and 0 < expected['bytes'] <= 4194304
    if rel not in before:
        before[rel] = read(rel, 'graph_before')
    assert pin(before[rel]) == expected, rel
assert sum(p['bytes'] for p in graph.values()) == 3578401
old_cli = 'work/candidates/peace-current-pending-observer-1375-v1/peace_current_pending.py'
assert pin(before[old_cli]) == {'bytes': 23345, 'sha256': 'ac8c292d1320f776a6a8817f0158c275e624bcfe05f9a2dc51220e03532ba643'}
for rel, b in before.items():
    assert read(rel, 'fixed_and_graph_after') == b, rel

OUT.mkdir()
outputs = {}
def save(name, obj):
    rel = OUTREL + '/' + name
    b = (json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + '\n').encode()
    with (ROOT / rel).open('xb') as f:
        f.write(b)
    outputs[rel] = pin(b)
    return {'path': rel, **pin(b)}

with (OUT / 'subject-draft-manifest.json').open('xb') as f:
    f.write(before[CAND+'source-manifest.draft.json'])
outputs[OUTREL+'/subject-draft-manifest.json'] = pin(before[CAND+'source-manifest.draft.json'])
flags = {k: False for k in review['authority']}
findings = {
 'schema': 'EU4-PEACE-PENDING-V2-ROOT-PRODUCTION-REVIEW/1', 'sealed': True, 'passed': True,
 'blocking_findings': [], 'approved_for_current_readonly_status': True,
 'stage': 'CURRENT_READONLY_PROFILE_ACCEPTED_DISTINCT_ONCE_LIVE_AUTHORIZATION_REQUIRED',
 'subject_cli_pin': review['subject_cli_pin'], 'subject_source_graph_sha256': draft['source_graph_sha256'],
 'subject_draft_manifest': {'path': CAND+'source-manifest.draft.json', **pin(before[CAND+'source-manifest.draft.json'])},
 'independent_source_review': {'path': REV+'findings.json', **pin(before[REV+'findings.json'])},
 'source_decision': 'Accept exact 41-pin graph after complete137-pin non-author source/fake/delta review. Root independently hashes all41 direct files before/after; it does not recursively recertify delegated host or historical native evidence.',
 'scope': 'Current explicitly selected actor->target inbox presence in the guarded paused layout only. No dispatch, original request or effect proof.',
 'diagnostic_policy': 'One four-byte unknown scalar per sample, raw/i32/u32 retained and compared by existing full-sample equality; no value is treated as a native enum or universal Mod capability.',
 'preserved_guards': ['exact process path/PID/creation/rights/modules', 'disk SHA and8192B entry', '735B loaded code pre/post', 'typed roots/count1380/manualpause1', 'full table/typed countries/full handles', 'complete no-tombstone queue/header/link/vtable/marker/endpoint checks', 'two complete selected samples', 'normal exit/held None/final source and disk checks before commit'],
 'limits': [
  '4096 attempted RPM/512KiB requested/64KiB single includes entry and all host/code/table/queue attempts; oversize valid worlds returnunknown.',
  'Host215/11 contents and older nested verifiers are delegated frozen checks; this production decision is not a new full transitive source audit.',
  'Normal context exit and held.handle None do not independently verify OS CloseHandle return.',
  'Two passes and file/root equality are coherence checks, not atomicity, ABA exclusion, generation or world lease.',
  'Raw native ID0/duplicates/state values do not prove acceptance, rejection, completion, persistence or original request causality.',
  'Live controller and explicit-file IO budgets require a separate root once authorization and independently reviewed frozen entry; no runtime operation occurs in this production publication.',
  'General Mod compatibility and native meaning of233e064 remain unknown; only this structural profile is approved.'
 ],
 'first_failure_and_delta_preserved': True, 'six_new_fake_methods_not_repeated': True,
 'canonical_change': 'Only sealed/runtime authorization/review pointers/stage metadata; source_pins and graph digest unchanged. Frozen draft and author files remain historical.',
 'authority': flags,
 'operations': {'CLI': 0, 'tests': 0, 'game_process_UI': 0, 'PE_or_decoder': 0, 'native': 0, 'requests': 0, 'saves': 0, 'reloads': 0},
 'distinct_once_live_authorization_issued': False,
}
fp = save('findings.json', findings)
promoted = copy.deepcopy(draft)
promoted.update(sealed=True, runtime_capture_authorized=True,
 independent_source_review={'path': REV+'findings.json', **pin(before[REV+'findings.json'])},
 production_review=fp, stage='root_production_current_readonly_profile_accepted_live_validation_pending')
assert {k for k in draft if draft[k] != promoted[k]} == {'sealed', 'runtime_capture_authorized', 'independent_source_review', 'production_review', 'stage'}
assert promoted['source_pins'] == draft['source_pins']
canonical = (json.dumps(promoted, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
assert read(CAND+'source-manifest.json', 'canonical_prewrite') == before[CAND+'source-manifest.json']
(ROOT / (CAND+'source-manifest.json')).write_bytes(canonical)
assert read(CAND+'source-manifest.json', 'canonical_after') == canonical
assert read(CAND+'source-manifest.draft.json', 'draft_after') == before[CAND+'source-manifest.draft.json']
outputs[CAND+'source-manifest.json'] = pin(canonical)
statusrel = CAND+'REVIEW_STATUS.md'
assert not (ROOT / statusrel).exists()
status = ('SOURCE-READY and exact current-readonly-profile production accepted. Live validation remains pending; a separate once controller/IO authorization is required.\n\n'
 'Complete non-author review passed137 pins, six new fake cases, original budget failure and separate delta check/catalog. Root rehashed all41 direct source files before/after. Canonical metadata alone is promoted; draft/source/tests/old v1 and failure histories remain frozen.\n\n'
 'The unclassified4B scalar is retained raw and compared across both samples. Its native semantics and general Mod compatibility remain unknown. Current queue presence/absence proves no original effect, AI response, peace completion, persistence, lease or native callable API.\n\n'
 'Production findings: ../../reports/peace-current-pending-v2-production-review-20261016-r1/findings.json\n').encode()
with (ROOT / statusrel).open('xb') as f:
    f.write(status)
outputs[statusrel] = pin(status)
save('verification.json', {'passed': True, 'fixed_before_after': {r: pin(b) for r, b in before.items()}, 'direct_graph_pins': 41, 'graph_unchanged': True, 'canonical_only_five_metadata_keys_changed': True, 'read_events': events, 'explicit_read_bytes': sum(x['bytes'] for x in events), 'manual_allowance': 1048576, 'seal_reserve': 1048576, 'upper_bytes': sum(x['bytes'] for x in events)+2097152, 'limit_bytes': LIMIT})
manifest = save('manifest.json', {'schema': 'EU4-PEACE-V2-ROOT-PRODUCTION-DELIVERY/1', 'sealed': True, 'passed': True, 'local_pins': outputs.copy(), 'canonical': {'path': CAND+'source-manifest.json', **pin(canonical)}, 'source_graph_sha256': draft['source_graph_sha256'], 'distinct_once_live_authorization_issued': False, 'no_CLI_tests_game_PE_native_operations': True})
print(json.dumps({'passed': True, 'findings': fp, 'manifest': manifest, 'canonical': pin(canonical), 'source_graph': draft['source_graph_sha256'], 'upper_bytes': sum(x['bytes'] for x in events)+2097152}, ensure_ascii=True))
