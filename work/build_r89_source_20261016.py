from pathlib import Path
import ast, ctypes, hashlib, json, sys

ROOT = Path(__file__).resolve().parents[1]
BASE = 'work/reports/war-peace-api-20261016-r89-c9d60-source/'
OUT = ROOT / BASE
GRANT = 'work/reports/war-peace-api-20261016-r89-root-source-authorization/authorization.json'
GRANT_PIN = {'bytes': 9647, 'sha256': 'c6e844b1d6f8e635d673caab18c5c2eade3c7faa2fa8109810f3bb95f003f012'}
RECEIPT = 'work/reports/war-peace-api-20261016-r89-root-source-authorization/receipt.json'
RECEIPT_PIN = {'bytes': 7712, 'sha256': '42d43b23744c8f811b075c53ca85e46238c9867f8ccef46c4c043962d3d0fb5c'}

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def memory():
    class C(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong)] + [(n, ctypes.c_size_t) for n in ['peakRSS', 'RSS', 'peakPaged', 'paged', 'peakNP', 'NP', 'committed', 'peakCommitted']]
    value = C(); value.cb = ctypes.sizeof(value)
    get = ctypes.windll.kernel32.GetCurrentProcess; get.restype = ctypes.c_void_p
    assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(get()), ctypes.byref(value), value.cb)
    assert max(value.RSS, value.committed) <= 805306368
    return {'RSS': value.RSS, 'commit': value.committed, 'peakRSS': value.peakRSS, 'peakCommit': value.peakCommitted}

def save(name, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode()
    with (OUT / name).open('xb') as stream:
        stream.write(raw)
    return {'path': (OUT / name).relative_to(ROOT).as_posix(), **pin(raw)}

def start():
    reads = []
    def read(relative, expected):
        path = ROOT / relative; assert path.stat().st_size <= 4194304
        memory(); raw = path.read_bytes(); assert pin(raw) == expected
        reads.append({'phase': 'source_build_before', 'path': relative, **pin(raw)})
        return raw
    grant_raw = read(GRANT, GRANT_PIN); receipt_raw = read(RECEIPT, RECEIPT_PIN)
    grant = json.loads(grant_raw); receipt = json.loads(receipt_raw)
    OUT.mkdir(exist_ok=False); (OUT / 'build-snapshots').mkdir()
    save('source-build-claim.json', {'schema': 'EU4-R89-SOURCE-BUILD-CLAIM/1', 'source_author': '/root/war_api',
                                    'source_build_grant': {'path': GRANT, **GRANT_PIN}, 'actual_authorized': False,
                                    'PE_engine_decoder_game_access': 0, 'source_limit': 33554432, 'retained_limit': 16777216})
    for name, value in [('grant.json', grant_raw), ('root-receipt.json', receipt_raw)]:
        with (OUT / 'build-snapshots' / name).open('xb') as stream:
            stream.write(value)
    save('source-build-intake.json', {'schema': 'EU4-R89-SOURCE-BUILD-INTAKE/1', 'reads': reads,
                                     'source_bytes': sum(v['bytes'] for v in reads), 'memory': memory(),
                                     'actual_authorized': False, 'PE_engine_decoder_game_access': 0})
    print(json.dumps({'grant': grant, 'root_receipt_keys': list(receipt), 'source_bytes': sum(v['bytes'] for v in reads)}))

def collect():
    grant_raw = (OUT / 'build-snapshots' / 'grant.json').read_bytes(); assert pin(grant_raw) == GRANT_PIN
    grant = json.loads(grant_raw)
    prior_raw = (OUT / 'source-build-intake.json').read_bytes(); prior = json.loads(prior_raw)
    reads = list(prior['reads']); snapshots = {GRANT: (OUT / 'build-snapshots' / 'grant.json').relative_to(ROOT).as_posix(),
                                             RECEIPT: (OUT / 'build-snapshots' / 'root-receipt.json').relative_to(ROOT).as_posix()}
    pins = {GRANT: GRANT_PIN, RECEIPT: RECEIPT_PIN}
    for relative, expected in grant['fixed_inputs'].items():
        path = ROOT / relative; assert path.stat().st_size <= 4194304
        assert relative.startswith('work/') and not relative.startswith('work/deps/') and not relative.endswith(('.exe', '.dll'))
        memory(); raw = path.read_bytes(); assert pin(raw) == expected, relative
        target = OUT / 'build-snapshots' / (f'{len(snapshots):03d}-' + path.name)
        with target.open('xb') as stream:
            stream.write(raw)
        reads.append({'phase': 'source_build_before', 'path': relative, **expected})
        pins[relative] = expected; snapshots[relative] = target.relative_to(ROOT).as_posix()
        assert sum(v['bytes'] for v in reads) < 33554432
    result = {'schema': 'EU4-R89-SOURCE-BUILD-INPUTS/1', 'original_pins': pins, 'snapshots': snapshots,
              'reads': reads, 'source_bytes': sum(v['bytes'] for v in reads),
              'owned_intake_reads': len(grant_raw) + len(prior_raw), 'memory': memory(), 'PE_engine_decoder_game_access': 0}
    save('source-build-inputs.json', result)
    selected = {}
    for name in ['produce.py', 'cfg_core.py', 'runtime_contract.py', 'launch_once.py']:
        relative = 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/' + name
        selected[relative] = (ROOT / snapshots[relative]).read_bytes().decode()
    relative = 'work/reports/war-peace-api-20261016-r86-cc220-actual-source/produce.py'
    text = (ROOT / snapshots[relative]).read_bytes().decode(); lines = text.splitlines()
    selected['R86_metadata_donor_lines245_326'] = '\n'.join(f'{n+1}: {line}' for n, line in enumerate(lines) if 244 <= n <= 325)
    print(json.dumps({'source_bytes': result['source_bytes'], 'files': len(pins), 'selected_text': selected}))

def assemble():
    ir = (OUT / 'source-build-inputs.json').read_bytes(); inputs = json.loads(ir)
    reads = []; owned_reads = [{'path': (OUT / 'source-build-inputs.json').relative_to(ROOT).as_posix(), 'bytes': len(ir)}]
    originals = dict(inputs['original_pins']); snapshots = dict(inputs['snapshots'])
    def cached(relative):
        path = ROOT / snapshots[relative]; raw = path.read_bytes(); assert pin(raw) == originals[relative]
        owned_reads.append({'path': path.relative_to(ROOT).as_posix(), 'bytes': len(raw)})
        return raw
    def extra(relative, expected):
        if relative in originals:
            assert originals[relative] == expected
            return cached(relative)
        path = ROOT / relative; assert path.stat().st_size <= 4194304
        assert relative.startswith('work/') and not relative.startswith('work/deps/') and not relative.endswith(('.exe', '.dll'))
        memory(); raw = path.read_bytes(); assert pin(raw) == expected, relative
        reads.append({'phase': 'source_build_before', 'path': relative, **expected})
        target = OUT / 'build-snapshots' / (f'{len(snapshots):03d}-' + path.name)
        with target.open('xb') as stream:stream.write(raw)
        originals[relative] = expected; snapshots[relative] = target.relative_to(ROOT).as_posix()
        return raw
    donor_base = 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/'
    full_base = 'work/reports/war-peace-api-20261016-r87-actual-independent-review/'
    full_findings = {'path': full_base + 'findings.json', 'bytes': 12526, 'sha256': 'dd62d0fb531ecaccc51d4812ad317b92a04bf121580f5be35b8d65d4abd458e0'}
    full_manifest = {'path': full_base + 'manifest.json', 'bytes': 30861, 'sha256': '26997cc636afbe1940b8037fca028d85fd70ac2175e5856fbb6c2d94a2424bfd'}
    review = json.loads(extra(full_findings['path'], {k: full_findings[k] for k in ('bytes', 'sha256')}))
    extra(full_manifest['path'], {k: full_manifest[k] for k in ('bytes', 'sha256')})
    assert review['sealed'] is True and review['passed'] is True and review['blocking_findings'] == []
    keys = ['subject_actual_manifest', 'subject_capture_pin', 'subject_contract_pin', 'subject_owned_pin', 'subject_selected_pin']
    upstream = {key: review[key] for key in keys}
    for value in upstream.values():
        assert set(value) == {'path', 'bytes', 'sha256'}
        extra(value['path'], {k: value[k] for k in ('bytes', 'sha256')})
    grant = json.loads(cached(GRANT)); old_manifest = json.loads(cached(donor_base + 'source-manifest.json'))
    job_path = 'work/candidates/frida-entry-observer-1375-v1/job_tree.py'
    job_pin = old_manifest['actual_source_pins'][job_path]
    extra(job_path, job_pin)
    producer = cached(donor_base + 'produce.py').decode(); tree = ast.parse(producer)
    helpers = ['require', 'save', 'digest', 'charge', 'read_source', 'stream_pin', 'memory_guard', 'source_guard', 'raw_write_review']
    functions = {node.name: ast.get_source_segment(producer, node) for node in tree.body if isinstance(node, ast.FunctionDef)}
    old_cfg = cached(donor_base + 'cfg_core.py').decode(); new_cfg = old_cfg
    substitutions = [('BEGIN = 0xcc266', 'BEGIN = 0xc9d60'), ('END = 0xcc366', 'END = 0xc9e60'),
                     ('SEEDS = (0xcc266, 0xcc32c)', 'SEEDS = (0xc9d60,)'),
                     ("'seed_semantics': {'0xcc266': 'normal_sequential_frontier', '0xcc32c': 'hypothetical_syntactic_target_not_normal_from_cc220'}",
                      "'seed_semantics': {'0xc9d60': 'direct_CALL_encoding_target_not_safe_callable_proof'}"),
                     ("'normal_reachability_from_R86_proved_by_this_worklist'", "'actual_CALL_callee_reachability_proved_by_this_worklist'")]
    for before, after in substitutions:
        assert new_cfg.count(before) == 1; new_cfg = new_cfg.replace(before, after, 1)
    with (OUT / 'cfg_core.py').open('xb') as stream:stream.write(new_cfg.encode())
    rt = (OUT / 'runtime-template.py.inc').read_bytes().decode()
    rt = rt.replace('__UPSTREAM_SUBJECTS__', repr(upstream)).replace('__UPSTREAM_REVIEW_PAIR__', repr({'findings': full_findings, 'manifest': full_manifest}))
    with (OUT / 'runtime_contract.py').open('xb') as stream:stream.write(rt.encode())
    cfg_pin = pin(new_cfg.encode()); runtime_pin = pin(rt.encode()); meta_raw = (OUT / 'metadata_core.py').read_bytes(); meta_pin = pin(meta_raw)
    cfg_function = functions['cfg'].replace("begin==0xcc266", "begin==0xc9d60").replace('Exact raw dual-seed window', 'Exact raw single-seed window').replace('_r87_cfg', '_r89_cfg')
    header = producer[:producer.index('def require(')]
    header = header.replace('R87 fixed dual continuation window. Source-only; no actual grant exists.', 'R89 fixed direct-CALL prefix. Source-only; no actual grant exists.')
    header = header.replace('ENTRY=0xcc266', 'ENTRY=0xc9d60').replace("R86='work/reports/war-peace-api-20261016-r86-cc220-actual-source/'", "R87='" + donor_base + "'")
    lines = header.splitlines(True)
    header = ''.join(('CFG_PIN=' + repr(cfg_pin) + '\n') if line.startswith('CFG_PIN=') else ('CONTRACT_PIN=' + repr(runtime_pin) + '\n') if line.startswith('CONTRACT_PIN=') else line for line in lines)
    header += 'META_PIN=' + repr(meta_pin) + '\n\n'
    main_raw = (OUT / 'main-template.py.inc').read_bytes()
    bottom = producer[producer.index("if __name__=='__main__':"):].replace('EU4-R87', 'EU4-R89')
    new_producer = header + '\n\n'.join(functions[name] for name in helpers) + '\n\n' + cfg_function + '\n\n' + main_raw.decode() + '\n' + bottom
    with (OUT / 'produce.py').open('xb') as stream:stream.write(new_producer.encode())
    old_launch = cached(donor_base + 'launch_once.py').decode()
    launch = old_launch.replace('_r87', '_r89').replace('EU4-R87', 'EU4-R89')
    launch = '\n'.join(('CONTRACT_PIN=' + repr(runtime_pin)) if line.startswith('CONTRACT_PIN=') else line for line in launch.splitlines()) + '\n'
    with (OUT / 'launch_once.py').open('xb') as stream:stream.write(launch.encode())
    parsed = ast.parse(new_producer)
    current = {node.name: node for node in parsed.body if isinstance(node, ast.FunctionDef)}
    original = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    reuse = {}
    for name in helpers:
        segment = ast.get_source_segment(new_producer, current[name])
        assert segment == functions[name] and ast.dump(current[name], include_attributes=False) == ast.dump(original[name], include_attributes=False)
        reuse[name] = {'text_equal': True, 'AST_equal': True, 'segment_pin': pin(segment.encode())}
    captured = json.loads(cached(donor_base + 'capture.json')); raw_owned = json.loads(cached(donor_base + 'owned-code.json'))
    rows = captured['analysis']['instructions']; matches = [(index, row) for index, row in enumerate(rows) if row['rva'] == '0xcc305']
    assert len(matches) == 1
    index, call = matches[0]; machine = bytes.fromhex(call['bytes']); assert machine.hex() == 'e856daffff'
    displacement = int.from_bytes(machine[1:], 'little', signed=True); assert 0xcc30a + displacement == 0xc9d60
    assert bytes.fromhex(raw_owned['raw_hex'])[0x9f:0xa4] == machine
    seed = {'schema': 'EU4-R89-DIRECT-CALL-PREFIX-SEED/1', 'fixed_raw_window': grant['fixed_raw_window'],
            'seed_semantics': grant['seed_semantics'], 'metadata_policy': grant['metadata_policy'], 'gap_policy': grant['gap_policy'],
            'caller_capture_pin': upstream['subject_capture_pin'], 'caller_owned_pin': upstream['subject_owned_pin'],
            'caller_contract_pin': upstream['subject_contract_pin'], 'upstream_full_review': {'findings': full_findings, 'manifest': full_manifest},
            'call_site_rva': '0xcc305', 'raw_call': machine.hex(), 'signed_rel32': displacement, 'next_rva': '0xcc30a', 'target_rva': '0xc9d60',
            'call_row_pointer': '/analysis/instructions/' + str(index), 'owned_raw_byte_offset': 0x9f,
            'caller_GP_assignment_rows': rows[index - 4:index + 1],
            'preCALL_register_sources': {'RCX': 'MOV RCX,RBX; opaqueC fromR87/R86 entryRCX under normal/nonvolatile conditions',
                                        'RDX': 'MOV RDX,RSI; opaqueS from unknown950b0 postRAX, retained under normal/nonvolatile conditions',
                                        'R8': 'MOV R8,R12; selected count-shaped local arithmetic, not proven units/type',
                                        'R9': 'MOV R9,RDI; selected capacity-shaped local arithmetic, not proven allocator contract',
                                        'RAX_XMM_flags': 'No new binding at these MOVs; prior unknown callee effects remain unknown'},
            'callee_entry_RSP': 'CallerF-8 from implicit CALL push. F=Q87-0x48 from fixed R86/R87 contract, henceQ89=Q87-0x50 only under its normal stack/alias premises.',
            'firstappend_subset': 'Only conditional C three-zero header andD0 with no necessary header/stack/alias mutation gives GP(C,S,1,1). This is not a universal or dynamic precondition.',
            'R88_cache_inventory_witness_only': 'No exact body in two explicitly checked caches; not global repository absence. No large cache reread here.',
            'actual_authorized': False, 'native_ready': False, 'callable': False, 'ownership_transfer_verified': False}
    save('entry-seed.json', seed)
    save('budget.json', {'schema': 'EU4-R89-SOURCE-AND-FUTURE-BUDGET/1', 'source': grant['source_limits'], 'Job': grant['Job'],
                         'future_target_limits': grant['future_target_limits'], 'metadata_policy': grant['metadata_policy'],
                         'code_bytes_fixed_before_any_metadata': 256, 'decoder_unique_bytes': 256, 'lookahead_upper': 3840,
                         'PE_separate_bill': 'Two complete38462504B SHA streams=76925008; plus actual diagnostic0..384B and fixed256B if valid. No header/unwind/callee/data reads.',
                         'new_cases_max': 4, 'new_cases_each_runs': 1, 'old_cases_or_tests': 0,
                         'actual_authorized': False, 'parent_and_child_source_partition': '2MiB plus30MiB, combined32MiB; conditional estimate is not a universal source bound.'})
    save('source-delta.json', {'schema': 'EU4-R89-SOURCE-DELTA/1', 'nine_helpers': reuse, 'cfg_literal_substitutions': [{'old': a, 'new': b} for a, b in substitutions],
                               'metadata_core': 'New bounded diagnostic-only29+3 pure byte callback algorithm; no extent selection/fallback.',
                               'main': 'New fixed single CALL seed, cached mapping, diagnostic metadata, fixed256 acquisition and R89 gate identities; all changes require new peer.',
                               'upstream_full_subjects_from_actual_frozen_findings': upstream, 'upstream_actual_review_already_passed': True,
                               'source_build_grant': {'path': GRANT, **GRANT_PIN}, 'actual_authorized': False,
                               'legacy_R86_exact_extent_8192_2048_gate_inherited': False})
    new_files = ['metadata_core.py', 'cfg_core.py', 'runtime_contract.py', 'produce.py', 'launch_once.py', 'cases_child.py']
    for name in new_files:
        value = (OUT / name).read_bytes(); ast.parse(value.decode(), filename=name)
    save('assembled-inputs.json', {'schema': 'EU4-R89-ASSEMBLED-INPUTS/1', 'original_pins': originals, 'snapshots': snapshots,
                                  'prior_original_reads': inputs['reads'], 'new_original_reads': reads, 'owned_reads': owned_reads,
                                  'source_bytes': inputs['source_bytes'] + inputs['owned_intake_reads'] + sum(v['bytes'] for v in reads) + sum(v['bytes'] for v in owned_reads),
                                  'new_component_pins': {name: pin((OUT / name).read_bytes()) for name in new_files},
                                  'upstream_subjects': upstream, 'upstream_review_pair': {'findings': full_findings, 'manifest': full_manifest},
                                  'job_source': {'path': job_path, **job_pin}, 'engine_metadata_only': old_manifest['decoder_expected_witness_pins'],
                                  'memory': memory(), 'syntax_AST_only': True, 'candidate_modules_executed': 0, 'PE_engine_decoder_game_access': 0})
    print(json.dumps({'components': new_files, 'upstream_subjects': upstream, 'nine_helpers': len(reuse), 'originals': len(originals),
                      'producer': pin(new_producer.encode()), 'runtime': runtime_pin, 'cfg': cfg_pin, 'metadata': meta_pin, 'actual_authorized': False}))

def freeze():
    ar = (OUT / 'assembled-inputs.json').read_bytes(); assembled = json.loads(ar)
    gr = (OUT / 'build-snapshots' / 'grant.json').read_bytes(); assert pin(gr) == GRANT_PIN; grant = json.loads(gr)
    original_pins = assembled['original_pins']; actual = dict(original_pins); reads = []
    paths = ['produce.py', 'cfg_core.py', 'metadata_core.py', 'runtime_contract.py', 'launch_once.py', 'cases_child.py',
             'run_cases_once.py', 'entry-seed.json', 'budget.json', 'source-delta.json', 'PROTOCOL.md', 'main-template.py.inc', 'runtime-template.py.inc']
    paths = [BASE + value for value in paths] + [Path(__file__).resolve().relative_to(ROOT).as_posix()]
    for relative in paths:
        path = ROOT / relative; assert path.stat().st_size <= 4194304
        raw = path.read_bytes(); memory(); reads.append({'phase': 'new_source_freeze', 'path': relative, **pin(raw)})
        if relative.endswith('.py'):
            ast.parse(raw.decode(), filename=relative)
        actual[relative] = pin(raw)
    for relative, expected in original_pins.items():
        path = ROOT / relative; assert path.stat().st_size <= 4194304
        raw = path.read_bytes(); memory(); assert pin(raw) == expected, relative
        reads.append({'phase': 'original_source_build_after', 'path': relative, **expected})
    assert len(actual) <= 64
    metadata = assembled['engine_metadata_only']; assert len(metadata) == 38 and not set(actual) & set(metadata)
    actual_total = sum(v['bytes'] for v in actual.values()); engine_total = sum(v['bytes'] for v in metadata.values())
    conditional_parent = 2 * actual_total + 2 * 131072 + 262144
    conditional_child = 4 * actual_total + 2 * engine_total + 2 * 131072 + 2097152
    assert conditional_parent < 2097152 and conditional_child < 31457280
    explicit = assembled['source_bytes'] + len(ar) + len(gr) + sum(v['bytes'] for v in reads)
    upper = explicit + 1048576
    assert upper < 33554432
    save('source-preparation.json', {'schema': 'EU4-R89-SOURCE-PREPARATION/1', 'source_build_grant': {'path': GRANT, **GRANT_PIN},
                                    'source_reads': reads, 'prior_source_account': assembled['source_bytes'], 'owned_assembly_and_grant_bytes': len(ar) + len(gr),
                                    'explicit_source_bytes': explicit, 'manual_tool_component_reads_allowance': 1048576, 'source_upper': upper,
                                    'original_before_after_equal': True, 'original_pins_count': len(original_pins),
                                    'actual_source_count': len(actual), 'actual_source_bytes_per_pass': actual_total,
                                    'engine38_metadata_expected_bytes': engine_total, 'engine_bodies_opened': 0,
                                    'future_source_conditional_estimate': {'parent': conditional_parent, 'child': conditional_child,
                                        'parent_allowances': 'Two131072B late-review/acceptance groups plus262144B capture.',
                                        'child_allowances': 'Two131072B late-review/acceptance groups plus2MiB locked-loader allowance.',
                                        'universal_bound_proved': False, 'larger_actual_receipts_or_loader_IO_can_refuse': True},
                                    'new_cases_pending': True, 'old_cases_or_tests': 0, 'unexpected_preparation_failures': 0,
                                    'syntax_AST_only_no_module_execution': True, 'PE_engine_decoder_game_access': 0, 'memory': memory()})
    manifest = {'schema': 'EU4-R89-FIXED-PREFIX-SOURCE/1', 'sealed': True, 'stage': 'source_frozen_before_four_new_cases_and_peer',
                'entry_rva': '0xc9d60', 'entry_semantics': 'Retained direct CALL target; not safe native callable proof',
                'fixed_raw_window': grant['fixed_raw_window'], 'seed_semantics': grant['seed_semantics'],
                'metadata_policy': grant['metadata_policy'], 'gap_policy': grant['gap_policy'],
                'source_build_authorization': {'path': GRANT, **GRANT_PIN},
                'actual_source_pins': actual, 'actual_source_count': len(actual), 'source_pins': {**actual, **metadata},
                'decoder_expected_witness_pins': metadata, 'engine_metadata_count': 38, 'engine_files_opened_in_preparation': False,
                'actual_authorized': False, 'native_ready': False, 'callable': False, 'reader_adoption_allowed': False,
                'selected_effect_verified': False, 'ownership_transfer_verified': False, 'world_lease': False,
                'atomic_snapshot': False, 'authorizes_retry': False}
    value = save('source-manifest.json', manifest)
    print(json.dumps({'source_manifest': value, 'source_upper': upper, 'actual_source_count': len(actual),
                      'actual_source_bytes_per_pass': actual_total, 'engine_metadata_only_count': 38,
                      'conditional_parent': conditional_parent, 'conditional_child': conditional_child,
                      'actual_authorized': False, 'all_preparation_shells_collected': True}))

if __name__ == '__main__':
    assert len(sys.argv) == 2 and sys.argv[1] in ['start', 'collect', 'assemble', 'freeze']
    {'start': start, 'collect': collect, 'assemble': assemble, 'freeze': freeze}[sys.argv[1]]()
