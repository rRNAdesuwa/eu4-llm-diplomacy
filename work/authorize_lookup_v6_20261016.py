from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/war-peace-api-lookup-v6-root-authorization-20261016-r2'
LIMIT = 8 * 1024 * 1024
reads = []
pins = {}
objects = {}

expected = {
 'work/reports/war-peace-api-lookup-v6-plan-20261016-r2/plan.json': (6338, '5c01dca5b49738fa099484e8bd93886f89d0bcb5d1d1fc24bf5acb6f2d02ff81'),
 'work/reports/war-peace-api-lookup-v6-plan-20261016-r2/manifest.json': (6526, '271c8daf02b8a30a7c9fd913dac3407a686cccded75f0db5644f9ddbb6596155'),
 'work/reports/war-peace-api-lookup-v6-plan-independent-review-20261016-r2/findings.json': (4707, 'dbd27562f95e85c951a8ab487fb3a0bcfb4bd0c6525ea7ef630a8c4a9b6cf6ab'),
 'work/reports/war-peace-api-lookup-v6-plan-independent-review-20261016-r2/manifest.json': (10026, '5cc68caf6281bb58224e1d0794b574986703c0c1fa1db17cf7c2c0e289e48cae'),
 'work/reports/war-peace-api-20261016-r80-actual-independent-review-r3/findings.json': (9252, '81bb504dd809001a9a1549f094e9b9889013808607d16be7e176748ae61d7e18'),
 'work/reports/war-peace-api-20261016-r80-actual-independent-review-r3/manifest.json': (15918, '91ed106282413b91fbc5d34a2cd096c7f41f1569a2df4ab0bf33ffa0c571a9c4'),
 'work/reports/war-peace-api-20261016-r81-actual-independent-review/findings.json': (10070, '88b77deb6932d216717adcff1edebd5eecfce6ddf1bc0137c0c1fcbec5302847'),
 'work/reports/war-peace-api-20261016-r81-actual-independent-review/manifest.json': (14590, '10d2348d4c5d1292576f5e05f04e55e5816d32bfb6b7d281ad4d2a847a68a703'),
 'work/reports/war-peace-api-20261016-r81-actual-independent-review/lookup-source-roles.json': (1522, 'ab5a636933ed3e0e5a55591dcc588456fb1159b6c118c7f1e91c719d8f5a47ca'),
 'work/candidates/war-peace-api-lookup-1375-v5/index.json': (185792, 'a8b70f547513def34f88c1dd19e73e573c63fe209aeced61f397db8b22556e6c'),
 'work/candidates/war-peace-api-lookup-1375-v5/data-manifest.json': (14774, '39efa19ba26675647379f6be182b26be727762d5eaf906f0be822b7ca0dba69c'),
 'work/candidates/war-peace-api-lookup-1375-v5/war_peace_lookup.py': (3602, '653530b8d60e789f33786819e43de7d057142de5c75c6841469d2802928a9da6'),
 'work/candidates/war-peace-api-lookup-1375-v5/query_engine.py': (16583, 'ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466'),
}

def read(rel, phase):
    p = ROOT / rel
    n = p.stat().st_size
    assert n <= 4 * 1024 * 1024
    assert sum(x['bytes'] for x in reads) + n <= LIMIT - 4 * 1024 * 1024
    b = p.read_bytes()
    pin = {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
    assert (pin['bytes'], pin['sha256']) == expected[rel], rel
    reads.append({'path': rel, 'phase': phase, **pin})
    return b, pin

for rel in expected:
    b, pin = read(rel, 'before')
    pins[rel] = pin
    if rel.endswith('.json'):
        objects[rel] = json.loads(b)

plan = objects['work/reports/war-peace-api-lookup-v6-plan-20261016-r2/plan.json']
assert plan['planned_scope']['result_entry_count_if_ready'] == 60
assert plan['engine_wrapper_plan']['engine_sha256'] == expected['work/candidates/war-peace-api-lookup-1375-v5/query_engine.py'][1]
assert plan['future_verification_plan']['first_queries'] == ['check', 'catalog', 'lookup 0x993570', 'lookup 0x97bd30']
for label in ['war-peace-api-20261016-r80-actual-independent-review-r3', 'war-peace-api-20261016-r81-actual-independent-review', 'war-peace-api-lookup-v6-plan-independent-review-20261016-r2']:
    o = objects[f'work/reports/{label}/findings.json']
    assert o['sealed'] and o['passed'] and o['blocking_findings'] == []

r81 = objects['work/reports/war-peace-api-20261016-r81-actual-independent-review/findings.json']
roles = objects['work/reports/war-peace-api-20261016-r81-actual-independent-review/lookup-source-roles.json']['roles']
assert set(roles) == {'author_actual_manifest', 'author_contract', 'author_selected_evidence', 'independent_full_findings', 'independent_full_manifest'}
for role, subject in [('author_actual_manifest', 'subject_actual_manifest'), ('author_contract', 'subject_contract_pin'), ('author_selected_evidence', 'subject_selected_pin')]:
    assert roles[role] == r81[subject]
for role, name in [('independent_full_findings', 'findings.json'), ('independent_full_manifest', 'manifest.json')]:
    rel = 'work/reports/war-peace-api-20261016-r81-actual-independent-review/' + name
    assert roles[role] == {'path': rel, **pins[rel]}

for rel in expected:
    _, after = read(rel, 'after')
    assert after == pins[rel]

OUT.mkdir(exist_ok=False)
grant = {
 'schema': 'EU4-LOOKUP-V6-BOUNDED-BUILD-GRANT/1',
 'owner': '/root/war_api',
 'plan_revision': 2,
 'accepted_fixed_inputs': pins,
 'accepted_R81_five_roles': roles,
 'candidate_directory': 'work/candidates/war-peace-api-lookup-1375-v6',
 'allowed_work': [
  'Build and freeze the R2-plan offline lookup candidate once after exact current schema inspection.',
  'Keep original58 rows exactly equal; preserve every old generator field except evidence append, adding only later_checked_context and historical_base_scope.',
  'Add R75/R77 generator contexts and one machine-contract-only peace.generator_selector_callee at97bd30 from accepted R80/R81.',
  'Use exactly94 direct JSON sources: old74 plus R75/R77ten plus R80/R81ten; every source referenced from entry evidence.',
  'Reuse the exact existing v5 ea030 Python engine and96cap; no engine fork or logic change.',
  'Wrapper delta limited to frozen DATA_SHA, revision/help5to6 and necessary BASE path; preserve all logic AST.',
  'Seal source/data/manifest and recompute actual build/query budgets before first query batch.',
  'Run first four queries once each: check, catalog, lookup0x993570, lookup0x97bd30; retain all outputs, failures and resource receipts.',
 ],
 'exclusive_claim_required_before_build': True,
 'first_query_count_limit': 4,
 'no_repeat_on_failure': True,
 'limits': {'build_plus_seal_bytes': 33554432, 'first_query_batch_bytes': 67108864, 'ordinary_file_bytes': 4194304, 'software_memory_bytes': 805306368, 'one_GiB_stop': True},
 'required_precision': [
  'R80 historical partial/noRET and R79 bounded unknown remain frozen; later R81 context is explicit.',
  'A known machine CALL entry is not an authorized callable diplomacy API or proved whole function.',
  'No type, fullhandle, uniqueness, valid bounds, nonnegative count, termination, object lifetime, units, recipient or gameplay effect is proved.',
  'Aggregate32MiB engine bound is successful graph acceptance, not universal failed-read or OS IO ceiling.',
  'Preserve first-query Job/peak/read/accounting evidence without re-running prior fixtures or tests.',
 ],
 'excluded': ['PE or native decoder access', 'game queries or actions', 'Frida', 'native calls', 'old tests or fixtures', 'new parser or guard tests', 'R82 new source incorporation', 'public capability-map or acceptance publication', 'ZIP/release packaging', 'any change to frozen v1-v5 or prior reports'],
 'publication_condition': 'Non-author complete v6 source/data/first-receipt review and separate root acceptance are still required.',
 'user_context': {'current_EU4_state_reported': 'main_menu_or_loading', 'second_game_query_authorized_here': False},
 'authority': {'native_ready': False, 'callable': False, 'sender_authorized': False, 'selected_effect_verified': False, 'reader_adoption_allowed': False, 'world_lease': False, 'atomic_snapshot': False},
}

def write(name, obj):
    b = (json.dumps(obj, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / name).open('xb') as f:
        f.write(b)
    return {'path': str((OUT / name).relative_to(ROOT)).replace('\\', '/'), 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}

grantpin = write('authorization.json', grant)
receipt = {'schema': 'EU4-LOOKUP-V6-ROOT-GRANT-RECEIPT/1', 'passed': True, 'grant': grantpin, 'selected_pins_before_after_equal': True, 'reads': reads, 'manual_prior_schema_allowance_bytes': 2097152, 'seal_reserve_bytes': 2097152, 'upper_bytes': sum(x['bytes'] for x in reads) + 4194304, 'limit_bytes': LIMIT, 'PE_decoder_game_author_execution': 0, 'root_has_not_built_or_run_queries': True}
receiptpin = write('receipt.json', receipt)
print(json.dumps({'passed': True, 'authorization': grantpin, 'receipt': receiptpin}, ensure_ascii=True))
