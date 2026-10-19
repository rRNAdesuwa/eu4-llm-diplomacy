from pathlib import Path
import ast
import ctypes
import hashlib
import json
import sys
import difflib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/peace-current-pending-v2-textconfig-source-peer-20261016-r1'
SUB = 'work/reports/peace-current-pending-v2-live-controller-20261016-r2/'
MANIFEST = SUB + 'source-manifest.json'
MP = {'bytes': 8861, 'sha256': '803d619df53c33b8698e78283c3ad223a61319c87b4a40ccaae732997d225127'}

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def memory_guard():
    class PMC(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong),
                    ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
    counters = PMC(); counters.cb = ctypes.sizeof(counters)
    process = ctypes.windll.kernel32.GetCurrentProcess
    process.restype = ctypes.c_void_p
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(process()), ctypes.byref(counters), counters.cb)
    assert ok, 'reviewer memory query failed'
    assert counters.WorkingSetSize <= 768 * 1024 * 1024, 'reviewer software memory guard'
    return {'working_set_bytes': counters.WorkingSetSize, 'peak_working_set_bytes': counters.PeakWorkingSetSize}

def save(path, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + '\n').encode()
    with path.open('xb') as f: f.write(raw)
    return pin(raw)

def intake():
    OUT.mkdir(parents=True, exist_ok=False)
    snapshots = OUT / 'source-snapshots'; snapshots.mkdir()
    ledger = []
    def read(rel, expected, label):
        p = ROOT / rel
        assert p.stat().st_size <= 4 * 1024 * 1024
        raw = p.read_bytes()
        actual = pin(raw)
        ledger.append({'path': rel, 'phase': 'source_before', **actual})
        assert actual == expected, 'subject pin mismatch: ' + rel
        with (snapshots / label).open('xb') as f: f.write(raw)
        return raw
    mraw = read(MANIFEST, MP, 'source-manifest.json')
    manifest = json.loads(mraw)
    paths = [SUB + 'text_config_adapter.py', SUB + 'runtime_contract.py', SUB + 'child.py',
             SUB + 'test_text_config_adapter.py', 'work/local_config.py',
             'work/reports/peace-current-pending-v2-live-controller-20261016-r1/child.py',
             manifest['build_authorization']['path']]
    source_pins = {MANIFEST: MP}
    labels = ['text_config_adapter.py', 'runtime_contract.py', 'child-r2.py',
              'test_text_config_adapter.py', 'local_config.py', 'child-r1.py', 'source-authorization.json']
    for rel, label in zip(paths, labels):
        expected = manifest['source_pins'][rel]
        raw = read(rel, expected, label)
        source_pins[rel] = expected
        if rel.endswith('.py'): ast.parse(raw.decode('utf-8-sig'), filename=rel)
        else: json.loads(raw)
    total = sum(x['bytes'] for x in ledger)
    assert total < 8 * 1024 * 1024
    save(OUT / 'intake.json', {'schema': 'EU4-TEXTCONFIG-NARROW-SOURCE-INTAKE/1',
         'subject_source_manifest': {'path': MANIFEST, **MP}, 'source_pins': source_pins,
         'source_reads': ledger, 'physical_source_before_bytes': total,
         'unlogged_preflight_manifest_read_bytes': 8861,
         'memory': memory_guard(), 'author_execution': False, 'real_env_access': False,
         'runtime_access': False, 'note': 'Eight exact source files only; no imported dependency body opened.'})
    print(json.dumps({'files': len(ledger), 'source_bytes': total, 'memory': memory_guard()}))

def seal():
    intake_raw = (OUT / 'intake.json').read_bytes()
    intake = json.loads(intake_raw)
    snapshots = OUT / 'source-snapshots'
    names = ['source-manifest.json', 'text_config_adapter.py', 'runtime_contract.py', 'child-r2.py',
             'test_text_config_adapter.py', 'local_config.py', 'child-r1.py', 'source-authorization.json']
    raw = {name: (snapshots / name).read_bytes() for name in names}
    source_map = intake['source_pins']
    labels = {
        MANIFEST: 'source-manifest.json',
        SUB + 'text_config_adapter.py': 'text_config_adapter.py',
        SUB + 'runtime_contract.py': 'runtime_contract.py',
        SUB + 'child.py': 'child-r2.py',
        SUB + 'test_text_config_adapter.py': 'test_text_config_adapter.py',
        'work/local_config.py': 'local_config.py',
        'work/reports/peace-current-pending-v2-live-controller-20261016-r1/child.py': 'child-r1.py',
        'work/reports/peace-current-pending-v2-text-config-source-authorization-20261016-r1/authorization.json': 'source-authorization.json',
    }
    for path, label in labels.items():
        assert pin(raw[label]) == source_map[path]
    old, new = raw['child-r1.py'].decode(), raw['child-r2.py'].decode()
    tree_old, tree_new = ast.parse(old), ast.parse(new)
    functions_old = {n.name: n for n in tree_old.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    functions_new = {n.name: n for n in tree_new.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    same = [n for n in functions_old if ast.dump(functions_old[n], include_attributes=False) == ast.dump(functions_new[n], include_attributes=False)]
    changed = [n for n in functions_old if n not in same]
    assert same == ['require', 'pin', 'decode', 'read', 'save', 'bootstrap', 'game_meter_class']
    assert changed == ['main']
    assert ast.get_source_segment(old, functions_old['game_meter_class']) == ast.get_source_segment(new, functions_new['game_meter_class'])
    diff = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile='child-r1.py', tofile='child-r2.py'))
    diff_raw = diff.encode()
    assert (OUT / 'child-delta.diff').read_bytes() == diff_raw  # Exact R2 partial retained, not overwritten.
    a = raw['text_config_adapter.py'].decode()
    l = raw['local_config.py'].decode()
    c = raw['runtime_contract.py'].decode()
    assert 'r"^[A-Za-z_][A-Za-z0-9_]*$"' in a and 'r"^[A-Za-z_][A-Za-z0-9_]*$"' in l
    assert a.index('self.meter.before(') < a.index('raw = stream.read(size + 1)') < a.index('self.meter.charge(')
    assert a.index('require(actual == self.expected)') < a.index('text = raw.decode(') < a.index('            validate_text(text)') < a.index('result = VirtualText(')
    assert 'raise ValueError(REDACTED) from None' in a
    assert 'super().__init__(text, newline=None)' in a
    assert 'contract.ROOT / "local.env"' in a and 'reference["path"] == "local.env"' in a
    assert "EU4-PEACE-V2-CURRENT-STATUS-ONCE/2" in c
    assert "for field in ('subject_source_manifest','subject_controller_pin','subject_child_pin','subject_adapter_pin')" in c
    replay = {
        'schema': 'EU4-TEXTCONFIG-NARROW-STATIC-REPLAY/1',
        'method': 'Source text/AST only; no author import, execution, or fixture rerun.',
        'child_exact_AST_same': same, 'child_exact_AST_changed': changed,
        'game_meter_class_exact_text_same': True,
        'child_diff_pin': {'path': (OUT / 'child-delta.diff').relative_to(ROOT).as_posix(), **pin(diff_raw)},
        'observations': [
            {'file': 'text_config_adapter.py', 'lines': [22, 29], 'fact': 'Identical KEY regular expression, strip/comment/partition/strip-key acceptance to frozen local_config lines34-42; values are not interpreted or recorded.'},
            {'file': 'text_config_adapter.py', 'lines': [32, 66], 'fact': 'Decoded utf-8-sig text is placed in StringIO(newline=None); frozen consumer only requires context/read().splitlines(). No general TextIOWrapper API identity claimed.'},
            {'file': 'text_config_adapter.py', 'lines': [97, 148], 'fact': 'Path/mode/options, attempts, regular size and expected size checked; size+1 reserve precedes single binary read; charge then raw length/SHA pin precedes strict decode and grammar validation; binary closes before virtual return; failures use fixed message from None.'},
            {'file': 'text_config_adapter.py', 'lines': [150, 173], 'fact': 'Summary contains path/pin/counters only. Runtime derives fixed ROOT/local.env; constructor/open dependency injection is used in fictional tests, not exposed through the runtime CLI.'},
            {'file': 'runtime_contract.py', 'lines': [61, 100], 'fact': 'New /2 once grant, fixed selection, budgets, source manifest, controller/child/adapter triples and source-peer four subject agreement; config path local.env/max64KiB/exact raw pin is separately required.'},
            {'file': 'child-r2.py', 'lines': [138, 189], 'fact': 'Donor and adapter use authenticated state bytes via exact compile. Original GameMeter text/AST unchanged; new composition and text summary only. Candidate invocation, pre/post contract, control/RPM path and final IO fields retain prior source except explicit adapter delta.'},
        ],
        'test_source_only': {'case_functions': [n.name for n in ast.parse(raw['test_text_config_adapter.py']).body if isinstance(n, ast.FunctionDef) and n.name.startswith('case_')], 'cases_executed_here': 0,
            'coverage_read': ['UTF8sig BOM/unicode/newlines', 'full size+1 reserve/EOF', 'changed raw pin/size', 'alias/oversize/write/encoding/other text refusal', 'syntax/decode error redaction', 'close/16 limit', 'short/error reads', 'binary delegation/config routing'],
            'not_independently_replayed': ['Author receipts/8-case results', 'real env', 'full controller/Job/host/source graph', 'imported donor implementation']},
    }
    replay_pin = save(OUT / 'static-source-replay.json', replay)
    after = []
    for path, expected in source_map.items():
        p = ROOT / path
        assert p.stat().st_size <= 4 * 1024 * 1024
        value = p.read_bytes()
        assert pin(value) == expected, 'source changed after review: ' + path
        after.append({'path': path, 'phase': 'source_after', **pin(value)})
    source_before_after = intake['physical_source_before_bytes'] + sum(e['bytes'] for e in after)
    snapshot_prior_reads = 18868 + 30025 + 26512
    tracked_read_bytes = source_before_after + 8861 + snapshot_prior_reads + len(intake_raw) + sum(map(len, raw.values())) + 150024
    accounting = {
        'explicit_subject_before_after_bytes': source_before_after,
        'explicit_preflight_manifest_buffer_bytes': 8861,
        'prior_owned_snapshot_inspection_bytes': snapshot_prior_reads,
        'seal_intake_and_snapshot_reads_bytes': len(intake_raw) + sum(map(len, raw.values())),
        'tracked_source_and_owned_read_bytes': tracked_read_bytes,
        'reviewer_failed_seal_owned_reads_bytes': 150024,
        'manual_script_metadata_read_allowance_bytes': 262144,
        'source_read_upper_bytes': tracked_read_bytes + 262144,
        'source_stage_limit_bytes': 8388608,
        'retained_limit_bytes': 2097152,
        'scope': 'Explicit reviewer file bytes plus conservative own-source/manual allowance; not OS/import/cache IO or runtime meter acceptance.',
    }
    assert accounting['source_read_upper_bytes'] < 8388608
    findings = {
        'schema': 'EU4-TEXTCONFIG-NARROW-CODE-PEER/1', 'sealed': True, 'passed': True,
        'scope': 'specified_eight_source_files_adapter_privacy_equivalence_metering_only',
        'blocking_findings': [], 'limited_code_peer_ready': True, 'full_source_ready': False,
        'reviewer_failures_preserved': ['reviewer-seal-failure-r1/failure.json', 'reviewer-seal-failure-r2/failure.json'],
        'subject_source_manifest': {'path': MANIFEST, **MP},
        'subject_adapter_pin': {'path': SUB + 'text_config_adapter.py', **source_map[SUB + 'text_config_adapter.py']},
        'subject_contract_pin': {'path': SUB + 'runtime_contract.py', **source_map[SUB + 'runtime_contract.py']},
        'subject_child_pin': {'path': SUB + 'child.py', **source_map[SUB + 'child.py']},
        'subject_tests_pin': {'path': SUB + 'test_text_config_adapter.py', **source_map[SUB + 'test_text_config_adapter.py']},
        'source_pins': source_map, 'source_after': after,
        'result': 'No blocking source defect found in the specified adapter boundary. Requires separate complete controller/retained-case review and new runtime grant.',
        'precision_notes': [
            'Equivalence is limited to accepted pinned UTF8sig/strict/newline=None file and frozen Path.read_text().splitlines() consumption; not arbitrary file API/encoding equivalence.',
            'Raw configuration contents are intentionally never retained by this review. Only the local_config source code was read; real local.env was not statted, opened, hashed, decoded or imported.',
            'Physical reservation/charge call ordering is verified from adapter source. Imported donor before/charge implementation and current runtime accounting are outside these eight files; no end-to-end meter proof is claimed.',
            'Path policy proves lexical/resolved fixed path checks before this open, not atomic filesystem identity, ABA exclusion, concurrent mutation exclusion or all hardlink identity.',
            'Other binary paths delegate to existing GameMeter/donor; no imported donor/base body, controller body, RPM implementation, env values, PID or runtime source closure was read.',
            'The tests source describes eight fictional cases. They were neither executed nor their retained results authenticated here; Val owns the later fullsource/retained audit.',
        ],
        'roles': {'reviewer': '/root/war_api', 'source_author': '/root/diplomacy_static',
            'reviewer_historical_role': 'Reviewer/author of some prior offline RE and observer evidence, including R86 source-build author; not author of this adapter/controller profile.',
            'subsequent_full_peer': '/root/validation_audit'},
        'source_accounting': accounting, 'memory': memory_guard(),
        'all_shells_collected': True, 'author_code_executed': False, 'author_tests_executed': 0,
        'real_env_access': False, 'PID_process_access': False, 'PE_access': False, 'decoder_access': False,
        'native_game_calls': 0, 'game_data_writes': 0, 'new_requests': 0, 'Frida_called': False,
        'runtime_authorized': False, 'native_ready': False, 'world_lease': False, 'atomic_snapshot': False,
        'selected_effect_verified': False, 'authorizes_retry': False,
        'static_replay_pin': {'path': (OUT / 'static-source-replay.json').relative_to(ROOT).as_posix(), **replay_pin},
    }
    report = '''# Limited text configuration code peer\n\nNo blocking defect found in the eight selected source files. This is a narrow source peer result, not complete source-ready or runtime acceptance.\n\nThe adapter reserves full file size plus one before its single binary read, then charges returned bytes and checks the exact raw pin before UTF8sig/strict decoding. Its prevalidation uses the frozen KEY grammar and raises a fixed redacted exception from None. StringIO(newline=None) supplies the read/splitlines route required by the frozen parser; virtual reads do not call the physical meter. Limits remain 64KiB and sixteen snapshot attempts.\n\nRuntime derives ROOT/local.env internally and requires a separate new /2 once grant with exact configuration pin and four reviewed subjects. Fictional tests inject their own path/open dependencies. The old GameMeter implementation is text/AST identical in both child copies; only adapter composition, child IO schema and config summary change.\n\nThe imported donor, complete controller/host graph, retained eight cases, process identity, real environment and live accounting were not authenticated by this review. No author module was imported or executed, and no tests, PE, decoder, process or native operation ran. Complete source/retained review and a fresh root runtime grant remain required.\n\nAll reviewer shell commands exited. Exact source and read accounting are in findings.json and static-source-replay.json.\n'''
    with (OUT / 'report.md').open('xb') as f: f.write(report.encode())
    findings_pin = save(OUT / 'findings.json', findings)
    files = {}
    for p in sorted(OUT.rglob('*')):
        if p.is_file():
            value = p.read_bytes(); files[p.relative_to(ROOT).as_posix()] = pin(value)
    script = Path(__file__).resolve(); script_raw = script.read_bytes()
    files[script.relative_to(ROOT).as_posix()] = pin(script_raw)
    retained_bytes = sum(v['bytes'] for k, v in files.items() if k.startswith(OUT.relative_to(ROOT).as_posix() + '/'))
    assert retained_bytes + 65536 < 2097152
    manifest_pin = save(OUT / 'manifest.json', {'schema': 'EU4-TEXTCONFIG-NARROW-CODE-PEER-MANIFEST/1',
        'sealed': True, 'scope': findings['scope'], 'source_pins': source_map, 'local_pins': files,
        'retained_bytes_before_manifest': retained_bytes, 'retained_upper_bytes': retained_bytes + 65536,
        'full_source_ready': False, 'runtime_authorized': False, 'native_ready': False})
    print(json.dumps({'passed': True, 'limited_scope': True, 'findings': findings_pin, 'manifest': manifest_pin,
        'source_read_upper_bytes': accounting['source_read_upper_bytes'], 'retained_upper_bytes': retained_bytes + 65536,
        'memory': memory_guard(), 'all_shells_collected': True}))

if __name__ == '__main__':
    assert len(sys.argv) == 2 and sys.argv[1] in ('intake', 'seal')
    {'intake': intake, 'seal': seal}[sys.argv[1]]()
