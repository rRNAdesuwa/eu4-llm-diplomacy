from pathlib import Path
import ctypes, hashlib, json, sys

ROOT = Path(__file__).resolve().parents[1]
BASE = 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/'
AUTH = 'work/reports/war-peace-api-20261016-r87-root-actual-authorization/'
OUT = ROOT / (BASE + 'actual-sealed-r1')
LIMIT = 16777216

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def decode(raw):
    def pairs(values):
        result = {}
        for k, v in values:
            assert k not in result, 'duplicate JSON key'
            result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))

def memory():
    class C(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong)] + [(n, ctypes.c_size_t) for n in ['peakRSS', 'RSS', 'peakPaged', 'paged', 'peakNP', 'NP', 'committed', 'peakCommitted']]
    c = C(); c.cb = ctypes.sizeof(c)
    get = ctypes.windll.kernel32.GetCurrentProcess; get.restype = ctypes.c_void_p
    assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(get()), ctypes.byref(c), c.cb)
    assert max(c.RSS, c.committed) <= 805306368
    return {'RSS': c.RSS, 'commit': c.committed, 'peakRSS': c.peakRSS, 'peakCommit': c.peakCommitted}

def save(name, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode()
    with (OUT / name).open('xb') as stream:
        stream.write(raw)
    return {'path': (OUT / name).relative_to(ROOT).as_posix(), **pin(raw)}

def intake():
    OUT.mkdir(exist_ok=False)
    (OUT / 'snapshots').mkdir()
    save('author-seal-claim.json', {'schema': 'EU4-R87-RETAINED-SEAL-CLAIM/1', 'executor': '/root/war_api',
                                  'actual_already_executed_by': '/root', 'new_producer_runs': 0, 'source_limit': LIMIT,
                                  'retained_limit': LIMIT, 'native_ready': False})
    initial = {
        BASE + 'source-manifest.json': {'bytes': 26330, 'sha256': 'e40ccf4eba10b12b7d626f0fc00b1bcdac50972d1a0a35559ba3756b64694817'},
        BASE + 'capture.json': {'bytes': 140752, 'sha256': '0f4ab901823ec893da60ebdeb9d237c1feec469cf67f4bed223b660a070955ec'},
        BASE + 'owned-code.json': {'bytes': 1099, 'sha256': 'dd4d12d21f9903eacfbcaeb1e6769e8ebb8f1bf98715cfdc6f0e0ea7bc125a69'},
        BASE + 'launcher-receipt.json': {'bytes': 26964, 'sha256': 'b5386af3613ed128d1aed7bcf26b2282ba7a49999e6ee10cf82db99ff659ee13'},
        BASE + 'run-authorization.json': {'bytes': 6091, 'sha256': 'e987bf04dd347227af77bcf0db5cf850b9d953bc208f95652c5df16375014439'},
        AUTH + 'authorization-copy.json': {'bytes': 6091, 'sha256': 'e987bf04dd347227af77bcf0db5cf850b9d953bc208f95652c5df16375014439'},
    }
    additional = [BASE + n for n in ['claim.json', 'launcher-claim.json', 'producer.stdout.txt', 'producer.stderr.txt', 'produce.py', 'runtime_contract.py', 'cfg_core.py', 'launch_once.py', 'entry-seed.json', 'budget.json', 'PROTOCOL.md']]
    additional += [AUTH + 'exec-tool-witness.json', AUTH + 'receipt.json']
    values = {}; snapshots = {}; reads = []
    def read(relative, expected=None):
        assert relative.startswith((BASE, AUTH)) and '..' not in Path(relative).parts
        path = ROOT / relative
        assert path.stat().st_size <= 4194304
        memory()
        raw = path.read_bytes(); value = pin(raw)
        if expected is not None:
            assert value == expected, relative
        reads.append({'phase': 'source_before', 'path': relative, **value})
        assert sum(v['bytes'] for v in reads) < LIMIT
        name = f'{len(snapshots):03d}-' + path.name
        target = OUT / 'snapshots' / name
        with target.open('xb') as stream:
            stream.write(raw)
        snapshots[relative] = target.relative_to(ROOT).as_posix()
        values[relative] = raw
    for relative, expected in initial.items():
        read(relative, expected)
    for relative in additional:
        if relative not in values:
            read(relative)
    source = decode(values[BASE + 'source-manifest.json'])
    capture = decode(values[BASE + 'capture.json'])
    owned = decode(values[BASE + 'owned-code.json'])
    launcher = decode(values[BASE + 'launcher-receipt.json'])
    authorization = decode(values[BASE + 'run-authorization.json'])
    result = {'schema': 'EU4-R87-RETAINED-SEAL-INTAKE/1', 'reads': reads,
              'source_pins': {v['path']: {k: v[k] for k in ('bytes', 'sha256')} for v in reads},
              'snapshots': snapshots, 'source_read_bytes': sum(v['bytes'] for v in reads),
              'memory': memory(), 'new_producer_runs': 0, 'PE_engine_decoder_game_access': 0}
    save('intake.json', result)
    def shape(value):
        if isinstance(value, dict):
            return {k: ('dict:' + str(len(v)) if isinstance(v, dict) else 'list:' + str(len(v)) if isinstance(v, list) else v) for k, v in value.items()}
        return str(type(value))
    print(json.dumps({'source': shape(source), 'capture': shape(capture), 'owned': owned,
                      'launcher': shape(launcher), 'auth': authorization,
                      'source_read_bytes': result['source_read_bytes']}))

def extend():
    intake_raw = (OUT / 'intake.json').read_bytes()
    prior = decode(intake_raw)
    snapshots = dict(prior['snapshots']); pins = dict(prior['source_pins']); reads = list(prior['reads'])
    owned_reads = [{'path': (OUT / 'intake.json').relative_to(ROOT).as_posix(), 'bytes': len(intake_raw)}]
    def cached(relative):
        path = ROOT / snapshots[relative]; raw = path.read_bytes()
        assert pin(raw) == pins[relative]
        owned_reads.append({'path': path.relative_to(ROOT).as_posix(), 'bytes': len(raw)})
        return decode(raw)
    source = cached(BASE + 'source-manifest.json')
    capture = cached(BASE + 'capture.json')
    authorization = cached(BASE + 'run-authorization.json')
    selected = dict(source['actual_source_pins'])
    assert len(selected) == 32 and len(source['decoder_expected_witness_pins']) == 38
    for key in ['upstream_R86_full_review', 'root_raw_frontier_review', 'source_peer_review']:
        for reference in authorization[key].values():
            selected[reference['path']] = {k: reference[k] for k in ('bytes', 'sha256')}
    for key in ['upstream_R86_root_acceptance', 'source_build_authorization']:
        reference = authorization[key]
        selected[reference['path']] = {k: reference[k] for k in ('bytes', 'sha256')}
    selected[BASE + 'author-manifest.json'] = {'bytes': 18004, 'sha256': '4f63afb7554b9348e9303ce914b4ce1ceca695d82b8c5fe77c0f74899c32b930'}
    for relative, expected in selected.items():
        if relative in pins:
            assert pins[relative] == expected
            continue
        assert relative.startswith('work/') and '..' not in Path(relative).parts
        assert not relative.startswith('work/deps/') and not relative.endswith('.exe') and not relative.endswith('.dll')
        path = ROOT / relative
        assert path.stat().st_size <= 4194304
        memory(); raw = path.read_bytes(); assert pin(raw) == expected, relative
        reads.append({'phase': 'source_before', 'path': relative, **expected})
        assert sum(v['bytes'] for v in reads) + sum(v['bytes'] for v in owned_reads) < LIMIT
        target = OUT / 'snapshots' / (f'{len(snapshots):03d}-' + path.name)
        with target.open('xb') as stream:
            stream.write(raw)
        snapshots[relative] = target.relative_to(ROOT).as_posix(); pins[relative] = expected
    extended = {'schema': 'EU4-R87-RETAINED-SEAL-EXTENDED-INTAKE/1', 'source_pins': pins,
                'snapshots': snapshots, 'reads': reads, 'owned_reads': owned_reads,
                'source_before_bytes': sum(v['bytes'] for v in reads), 'owned_read_bytes': sum(v['bytes'] for v in owned_reads),
                'engine_metadata_only_count': 38, 'engine_bodies_opened': 0, 'memory': memory()}
    save('extended-intake.json', extended)
    analysis = capture['analysis']
    rows = analysis.get('rows')
    print(json.dumps({'analysis_keys': list(analysis), 'analysis_scalars': {k: v for k, v in analysis.items() if not isinstance(v, (dict, list))},
                      'rows': rows, 'edges': analysis.get('edges'), 'metadata': capture['metadata'],
                      'seed_containment': capture['seed_containment'], 'flat_source_count': len(pins),
                      'source_before_bytes': extended['source_before_bytes'], 'owned_read_bytes': extended['owned_read_bytes']}))

def seal():
    ir = (OUT / 'extended-intake.json').read_bytes(); intake = decode(ir)
    owned_reads = [{'path': (OUT / 'extended-intake.json').relative_to(ROOT).as_posix(), 'bytes': len(ir)}]
    def raw(relative):
        path = ROOT / intake['snapshots'][relative]; value = path.read_bytes()
        assert pin(value) == intake['source_pins'][relative]
        owned_reads.append({'path': path.relative_to(ROOT).as_posix(), 'bytes': len(value)})
        return value
    def data(relative):
        return decode(raw(relative))
    def reference(relative):
        return {'path': relative, **intake['source_pins'][relative]}
    source = data(BASE + 'source-manifest.json'); capture = data(BASE + 'capture.json')
    owned = data(BASE + 'owned-code.json'); auth = data(BASE + 'run-authorization.json')
    claim = data(BASE + 'claim.json'); launch_claim = data(BASE + 'launcher-claim.json')
    launcher = data(BASE + 'launcher-receipt.json')
    tool = data(AUTH + 'exec-tool-witness.json')
    assert raw(BASE + 'run-authorization.json') == raw(AUTH + 'authorization-copy.json')
    assert auth['schema'] == 'EU4-R87-FIXED-DUAL-SEED-ROOT-AUTHORIZATION/1'
    assert auth['sealed'] is True and auth['single_attempt'] is True and auth['root_explicit_start_received'] is True
    assert capture['authorization_pin'] == launcher['authorization_pin'] == claim['authorization_pin'] == pin(raw(BASE + 'run-authorization.json'))
    assert capture['source_manifest'] == launcher['source_manifest'] == claim['source_manifest'] == pin(raw(BASE + 'source-manifest.json'))
    assert capture['source_pins'] == claim['source_pins'] == source['source_pins']
    assert len(source['actual_source_pins']) == 32 and len(source['decoder_expected_witness_pins']) == 38
    subjects = {'source_manifest': 'source-manifest.json', 'producer_pin': 'produce.py', 'entry_seed_pin': 'entry-seed.json', 'cfg_core_pin': 'cfg_core.py', 'launcher_pin': 'launch_once.py'}
    for name, filename in subjects.items():
        assert auth[name] == pin(raw(BASE + filename))
    review_subjects = {'subject_source_manifest': 'source-manifest.json', 'subject_producer': 'produce.py', 'subject_entry_seed': 'entry-seed.json', 'subject_cfg_core': 'cfg_core.py', 'subject_launcher': 'launch_once.py'}
    for label in ['upstream_R86_full_review', 'root_raw_frontier_review', 'source_peer_review']:
        review = data(auth[label]['findings']['path'])
        assert review['sealed'] is True and review['passed'] is True and review['blocking_findings'] == []
        assert capture['review_pins'][label] == auth[label]
        if label != 'upstream_R86_full_review':
            for key, filename in review_subjects.items():
                assert review[key] == pin(raw(BASE + filename))
    acceptance = data(auth['upstream_R86_root_acceptance']['path'])
    assert acceptance['sealed'] is True and acceptance['accepted'] is True
    assert acceptance['subject_full_review'] == auth['upstream_R86_full_review']['findings']
    assert capture['review_pins']['upstream_R86_root_acceptance'] == auth['upstream_R86_root_acceptance']
    assert auth['fixed_raw_window'] == capture['fixed_raw_window'] == owned['fixed_raw_window']
    assert auth['seed_semantics'] == capture['seed_semantics']
    assert capture['cc32c_normal_reachable_from_R86'] is False
    window = bytes.fromhex(owned['raw_hex']); base = int(owned['fixed_raw_window']['begin'], 16)
    assert len(window) == 256 and owned['bytes'] == 256 and owned['sha256'] == hashlib.sha256(window).hexdigest() == '0e0232ea5a990dd7eb716e0cbc028745dae59d3f1b0a851469075c29ec291a7a'
    assert base == 0xcc266 and int(owned['fixed_raw_window']['end_exclusive'], 16) == base + 256
    analysis = capture['analysis']; rows = analysis['instructions']; by_rva = {int(r['rva'], 16): r for r in rows}
    occupied = set(); row_checks = []
    for row in sorted(rows, key=lambda r: int(r['rva'], 16)):
        site = int(row['rva'], 16); value = bytes.fromhex(row['bytes'])
        assert window[site - base:site - base + len(value)] == value
        positions = set(range(site, site + len(value))); assert not occupied & positions
        occupied.update(positions)
        row_checks.append({'rva': row['rva'], 'bytes': row['bytes'], 'mnemonic': row['mnemonic'], 'operands': row['operands'], 'raw_exact': True})
    assert len(rows) == 61 and len(occupied) == 210 and occupied == set(range(base, 0xcc338))
    assert analysis['decoded_unique_bytes'] == 210 and analysis['local_normal_CFG_closed'] is False and analysis['whole_function_closed'] is False
    assert analysis['undecoded_owned_intervals'] == [['0xcc338', '0xcc366']]
    assert analysis['decoder_input_total_bytes'] == sum(v['bytes'] for v in analysis['lookahead_inputs']) == 915
    lookahead_positions = set()
    for value in analysis['lookahead_inputs']:
        lookahead_positions.update(range(int(value['rva'], 16), int(value['rva'], 16) + value['bytes']))
    assert len(lookahead_positions) == analysis['decoder_input_unique_bytes'] == 224
    assert 915 - 224 == analysis['decoder_overlap_bytes'] == 691
    calls = []; branches = []
    for edge in analysis['edges']:
        row = by_rva[int(edge['site'], 16)]; machine = bytes.fromhex(row['bytes']); site = int(edge['site'], 16)
        assert edge['callee_followed'] is False
        if edge['kind'] == 'call':
            assert machine[0] == 0xe8 and len(machine) == 5
            displacement = int.from_bytes(machine[1:], 'little', signed=True)
            assert site + 5 + displacement == int(edge['target_rva'], 16)
            calls.append({'site': edge['site'], 'raw_call': row['bytes'], 'signed_rel32': displacement, 'target_rva': edge['target_rva'], 'callee_body_followed': False})
        else:
            assert len(machine) == 2 and machine[0] in [0x76, 0x75, 0x77, 0xeb]
            displacement = int.from_bytes(machine[1:], 'little', signed=True)
            assert site + 2 + displacement == int(edge['target_rva'], 16)
            branches.append({'site': edge['site'], 'kind': edge['kind'], 'raw': row['bytes'], 'target_rva': edge['target_rva'], 'fallthrough': edge['fallthrough']})
    assert len(calls) == 6 and len({v['target_rva'] for v in calls}) == 5 and len(branches) == 5
    assert [r['rva'] for r in rows if r['mnemonic'] == 'ret'] == ['0xcc32b']
    assert sorted(r['rva'] for r in rows if r['mnemonic'] == 'int3') == ['0xcc331', '0xcc337']
    fixed_ops = {0xcc266: '48897c2458', 0xcc272: '4c89642460', 0xcc28c: '4889742450', 0xcc299: '4c89742420',
                 0xcc2aa: '48890ce8', 0xcc30a: '488b742450', 0xcc30f: '498bc6', 0xcc312: '4c8b742420',
                 0xcc317: '488b7c2458', 0xcc31c: '4c8b642460', 0xcc321: '4883c428', 0xcc32b: 'c3'}
    for site, machine in fixed_ops.items():
        assert by_rva[site]['bytes'] == machine
    metadata = capture['metadata']; assert len(metadata) == 9
    previous_end = None
    for record in metadata:
        value = bytes.fromhex(record['raw_hex']); assert len(value) == 12
        begin, end, unwind = [int.from_bytes(value[n:n+4], 'little') for n in (0, 4, 8)]
        assert begin == int(record['begin_rva'], 16) < end == int(record['end_exclusive'], 16)
        assert unwind == int(record['unwind_rva_unfollowed'], 16)
        if previous_end is not None:
            assert previous_end <= begin
        previous_end = end
    assert [r['index'] for r in metadata] == list(range(1251, 1260))
    assert metadata[2]['raw_hex'] == '66c20c008cc20c0028dddc01' and metadata[6]['raw_hex'] == '2cc30c0032c30c0080dddc01'
    assert capture['metadata_valid'] is True and capture['metadata_issues'] == []
    assert all(v['seed_pdata_gap'] is False for v in capture['seed_containment'].values())
    sparse_sum = sum(v['bytes'] for v in capture['sparse_reads']); assert sparse_sum == 108 + 256
    assert capture['metadata_physical_bytes'] == 108 and len(capture['sparse_reads']) == 10
    whole_sum = sum(v['bytes_read'] for v in capture['full_PE_authentication_reads'])
    assert whole_sum == 76925008 and all(v['completed'] is True and v['sha256'] == capture['game_sha256'] for v in capture['full_PE_authentication_reads'])
    assert whole_sum + sparse_sum == capture['total_PE_physical_bytes'] == 76925372
    child_bytes = sum(v['bytes'] for v in capture['source_file_reads']); parent_bytes = sum(v['bytes'] for v in launcher['parent_source_reads'])
    assert child_bytes == capture['source_file_read_bytes'] == launcher['child_capture_source_bytes'] == 17772050
    assert parent_bytes == launcher['parent_source_bytes'] == 1058487 and child_bytes + parent_bytes == 18830537 < 33554432
    assert child_bytes < 31457280 and parent_bytes < 2097152
    assert len(capture['source_file_reads']) == 233 and len(launcher['parent_source_reads']) == 86
    job = launcher['job']
    assert launcher['passed'] is True and launcher['failure'] is None and launcher['all_shells_collected'] is True
    assert job['exit_code'] == 0 and job['error'] is None and job['direct_child_collected'] is True
    assert job['job_active_processes_final'] == 0 and job['job_total_processes'] == 2
    assert job['peak_job_commit'] == 25493504 and job['memory_limit'] == 805306368
    assert job['existing_target_game_assigned_to_job'] is False and job['completed_command_descendants_terminated'] is False
    assert capture['normal_target_context_exit'] is True and capture['source_engine_before_after_equal'] is True and capture['commit_after_target_close_and_final_guards'] is True
    assert capture['own_process_job_membership_observed'] is True and capture['hard_Job_limits_verified_here'] is False
    assert all(capture[k] == 0 for k in ['game_process_accesses', 'Frida_operations', 'native_game_calls', 'requests', 'tests'])
    assert tool['tool_result']['exit_code'] == 0 and tool['tool_result']['chunk_id'] == 'c57ad6'
    stdout = raw(BASE + 'producer.stdout.txt'); stderr = raw(BASE + 'producer.stderr.txt')
    assert not stderr and decode(stdout)['rows'] == 61
    old_owned = data('work/reports/war-peace-api-20261016-r86-cc220-actual-source/owned-code.json')
    old_machine = bytes.fromhex(old_owned['raw_hex'])
    assert len(old_machine) == 70 and old_machine == bytes.fromhex('405355415541574883ec28488b41084c8bfa488b11498bef482bea482bc24d8be848c1fd0348c1f80349b8ffffffffffffff1f488bd9493bc00f84cd000000488b4910482bca')
    flags = {'native_ready': False, 'callable': False, 'reader_adoption_allowed': False, 'selected_effect_verified': False,
             'world_lease': False, 'atomic_snapshot': False, 'authorizes_retry': False, 'ownership_transfer_verified': False,
             'whole_function_closed': False, 'further_actual_authorized': False}
    selected_pin = save('selected-cfg.json', {'schema': 'EU4-R87-AUTHOR-SELECTED-CFG/1', 'capture_pin': reference(BASE + 'capture.json'),
                                            'owned_code_pin': reference(BASE + 'owned-code.json'), 'instructions': rows,
                                            'analysis_retained_unchanged': {k: v for k, v in analysis.items() if k != 'instructions'}, **flags})
    replay_pin = save('raw-replay.json', {'schema': 'EU4-R87-AUTHOR-RAW-REPLAY/1', 'method': 'Retained byte slices, integer rel32/rel8/pdata and resource arithmetic; no decoder or PE/engine access.',
                                        'row_checks': row_checks, 'calls': calls, 'branches': branches,
                                        'decoded_positions': 210, 'owned_window_bytes': 256, 'remaining_undecoded_range': ['0xcc338', '0xcc366'],
                                        'metadata_rows': metadata, 'metadata_records': 9, 'metadata_bytes': 108,
                                        'decoder_attempts': 61, 'lookahead_total': 915, 'lookahead_unique': 224, 'lookahead_overlap': 691,
                                        'explicit_memory_stores': {'stack_homes': ['0xcc266', '0xcc272', '0xcc28c', '0xcc299'], 'selected_slot': ['0xcc2aa'], 'total': 5},
                                        'explicit_memory_reads': ['0xcc2a3', '0xcc2b1', '0xcc2b5', '0xcc2e6', '0xcc30a', '0xcc312', '0xcc317', '0xcc31c'],
                                        'LEA_is_memory_read': False, 'implicit_stack': 'Each static CALL site implicitly writes an8B return slot if executed. Four POP plus RET implicitly read40B on the normal epilogue; not counted as explicit stores/reads.', **flags})
    contract_pin = save('contract.json', {
        'schema': 'EU4-R87-CONDITIONAL-MACHINE-CONTRACT/1', 'sealed': True, 'author_preview_only': True, 'independent_actual_review_pending': True,
        'evidence_kind': 'ordinary locked Capstone5.0.7 capture; not REA EvidenceID or runtime execution',
        'subject_source_manifest': reference(BASE + 'source-manifest.json'), 'subject_capture_pin': reference(BASE + 'capture.json'),
        'subject_owned_pin': reference(BASE + 'owned-code.json'), 'selected_cfg_pin': selected_pin, 'raw_replay_pin': replay_pin,
        'raw_window': owned['fixed_raw_window'], 'window_is_function_extent': False,
        'scope': {'instructions': 61, 'unique_decoded_bytes': 210, 'normal_RET': '0xcc32b', 'INT3': ['0xcc331', '0xcc337'],
                  'static_CALL_sites': 6, 'unique_unfollowed_targets': 5, 'local_normal_CFG_closed_source_flag': False,
                  'cc266': 'normal sequential R86 frontier', 'cc32c': 'explicit hypothetical/syntactic seed; not normal sequentially reachable after the R86 SAR3 comparison',
                  'cc32c_current_pdata': 'record1257 covers6B; explicit gap exception was not needed in this actual capture'},
        'inherited_machine_state': {'C': 'R86 entryRCX, retained inRBX under normalcallee/nonvolatile conditions',
                                    'D': 'R86 entryRDX insertion-position-shaped opaque value, retained inR15',
                                    'E': 'R86 entryR8, retained inR13; raw QWORD payload is fresh-read atcc2a3',
                                    'F': 'Q-0x48, whereQ isR86 entryRSP; R87 is an inherited fragment, not independent Win64 entry',
                                    'RBP': 'SAR64((D-M64[C]) mod2^64,3)', 'entry_RAX': 'SAR64((M64[C+8]-M64[C]) mod2^64,3)',
                                    'entry_RCX': '(M64[C+0x10]-M64[C]) mod2^64', 'entry_RDX': 'M64[C]',
                                    'entry_R8': '0x1fffffffffffffff', 'R9_XMM_flags': 'No new formal contract; unknown or instruction-local only'},
        'normal_firstappend_selected_conditions': [
            'R86 entry has C with all three QWORD header values0 and D=0; the corresponding R86/R87 reads observe that state.',
            'C/E/stack are valid for all selected accesses; E is readable for8B atcc2a3. Every reached external callee returns normally with Win64 nonvolatile registers and RSP preserved.',
            'The opaque950b0 returnS is valid writable8B; its body/allocation semantics/extent are unverified. Any needed noalias between S/E/C and stack/return/homes, and no header or saved-slot mutation across external calls, are additional premises rather than derived guarantees.',
            'Fresh M64[C] and M64[C+8] remain0 throughcc2b5; no call or aliased explicit store has changed the header assumptions used for this selected path.'
        ],
        'normal_firstappend_steps': [
            {'sites': ['0xcc26b', '0xcc277', '0xcc27b', '0xcc287', '0xcc2c6', '0xcc2ca', '0xcc2d0', '0xcc2d7', '0xcc2d9'], 'fact': 'capCount0,size0,index0 implyR12=1 andRDI=1; JBE selectscc2c6, CMOVAE does not replace1, JA is false, thenJMPcc28c.'},
            {'site': '0xcc29e', 'raw_call': 'e80d8efcff', 'target': '0x950b0', 'arguments': {'RCX': '8', 'RDX': '0', 'R8': '0x1fffffffffffffff', 'R9_XMM': 'unknown'}, 'fact': 'Unknown callee; allocation candidate only, no allocator proof.'},
            {'sites': ['0xcc2a3', '0xcc2a7', '0xcc2aa', '0xcc2b8'], 'fact': 'LetS=postcallRAX. FreshV=M64[E] is written byMOV[S+8*index]=V; index0 givesM64[S]=V. RSI=S andR14=S+8*index. This is a raw payload store, not header update or ownership transfer.'},
            {'sites': ['0xcc2b1', '0xcc2b5', '0xcc2bf', '0xcc2c1', '0xcc2c4', '0xcc2f4'], 'target': '0x1a35750', 'arguments': {'RCX': 'S', 'RDX': '0', 'R8': '0', 'R9_XMM': 'unknown'}, 'fact': 'D0 equals freshend0, so selected path skipscc2e1. ZeroR8 does not prove no dereference, sideeffect or callback in the unexamined callee.'},
            {'sites': ['0xcc2f9', '0xcc2fc', '0xcc2ff', '0xcc302', '0xcc305'], 'raw_call': 'e856daffff', 'target': '0xc9d60', 'arguments': {'RCX': 'C', 'RDX': 'S', 'R8': '1', 'R9': '1', 'XMM': 'unknown'}, 'fact': 'Under the preceding normal/alias premises this exact GP tuple is presented. Header mutation, old/new allocation cleanup and ownership effects remain unknown.'}
        ],
        'normal_return_and_stack': {'preconditions': 'All reached callee normal/nonvolatile/RSP contract; valid stack/homes/return slot; no intervening alias or callee write corrupts saved values.',
                                    'save_sites': {'R14': 'cc299 M64[F+20]=R14', 'RDI': 'cc266 M64[F+58]=RDI', 'RSI': 'cc28c M64[F+50]=RSI', 'R12': 'cc272 M64[F+60]=R12'},
                                    'home_addresses': {'F+20': 'Q-28', 'F+50': 'Q+8', 'F+58': 'Q+10', 'F+60': 'Q+18'},
                                    'slot_result': 'cc30f MOVRAX,R14 occurs beforecc312 restoresR14. Thus the conditional normal epilogue returns the previously computed rawS+8*index; it does not return a newly read vector header or an acceptance code.',
                                    'restores': ['cc30a RSIfromF+50', 'cc312 R14fromF+20', 'cc317 RDIfromF+58', 'cc31c R12fromF+60', 'cc321 ADDRSP,28', 'cc325 POPR15', 'cc327 POPR13', 'cc329 POPRBP', 'cc32a POPRBX', 'cc32b RET'],
                                    'RSP': 'F+28 afterADD; fourPOP reachF+48=Q; RET readsM64[Q] and reachesQ+8.',
                                    'borrows_alive_proved': False},
        'general_branch_limits': ['The other path may make two1a35750 calls and uses fresh header reads; neither callee body is followed.',
                                  'INT3 after8f400/95050 does not establish that those callees never return or fully characterize exceptions.',
                                  'Source worklist flags remainlocalCFGfalse/wholefunctionfalse. The owned normal epilogue is conditional and does not certify every possible input or callee path.',
                                  'No world/class/definition/header lease, actual allocator extent, firstappend final header, complete C++ lifetime or native readiness is established.'],
        'next_single_gap': 'c9d60 atcc305 is the precise candidate for a separate future source-reviewed scope; no new acquisition is authorized here.', **flags})
    next_pin = save('next-scope-proposal.json', {'schema': 'EU4-R87-NEXT-SINGLE-GAP-PROPOSAL/1', 'source_only_proposal': True,
                                               'call_site': '0xcc305', 'raw_call': 'e856daffff', 'signed_rel32': -9642, 'target_candidate': '0xc9d60',
                                               'reason': 'Explicit final GP tuple C,S,1,1 on the selected empty-header path; header writes and allocation/ownership cleanup are unexamined.',
                                               'suggested_future_limits': {'exact_pdata_begin_required': True, 'metadata_records': 32, 'whole_extent_max': 8192, 'otherwise_prefix': 2048, 'no_callee_or_data_follow': True},
                                               'actual_authorized': False, 'source_build_authorized': False, **flags})
    resources_pin = save('resources.json', {'schema': 'EU4-R87-AUTHOR-ACTUAL-RESOURCES/1',
                                          'producer_source': {'events': 233, 'bytes': child_bytes, 'limit': 31457280},
                                          'launcher_source': {'events': 86, 'bytes': parent_bytes, 'limit': 2097152},
                                          'combined_explicit_source_bytes': 18830537, 'combined_limit': 33554432,
                                          'PE_separate': {'whole_EXE_SHA_streams': 2, 'whole_EXE_SHA_bytes': 76925008, 'pdata': 108, 'fixed_code': 256, 'total': 76925372},
                                          'decoder': {'instructions': 61, 'unique_decoded': 210, 'lookahead_total': 915, 'lookahead_unique': 224, 'overlap': 691},
                                          'Job_receipt': job, 'root_exec_witness_pin': reference(AUTH + 'exec-tool-witness.json'),
                                          'time_scope': {'outer_exec_tool_wall_seconds': tool['tool_result']['wall_time_seconds'], 'owned_Job_seconds': job['seconds'], 'HTTP_RTT_claimed': False},
                                          'retained_stdout_pin': reference(BASE + 'producer.stdout.txt'), 'retained_stderr_pin': reference(BASE + 'producer.stderr.txt'),
                                          'normal_target_close_and_source_postguards': 'Producer flags supported by frozen acquisition source and source-peer; retained launcher receipt supports owned Job collection. No independent game process observation.',
                                          'complete_OS_loader_IO_claimed': False, 'engine_body_reopened_in_author_seal': False,
                                          'root_prior_manual_source_reads_charged_to_this_seal': False, 'all_shells_collected': True, **flags})
    after = []
    for relative, expected in intake['source_pins'].items():
        path = ROOT / relative; assert path.stat().st_size <= 4194304
        memory(); value = path.read_bytes(); assert pin(value) == expected, relative
        after.append({'phase': 'source_after', 'path': relative, **expected})
    inspection_raw = (OUT / 'inspection.json').read_bytes(); inspection = decode(inspection_raw)
    owned_reads.append({'path': (OUT / 'inspection.json').relative_to(ROOT).as_posix(), 'bytes': len(inspection_raw)})
    explicit = intake['source_before_bytes'] + intake['owned_read_bytes'] + sum(v['bytes'] for v in owned_reads) + inspection['read_bytes'] + sum(v['bytes'] for v in after)
    source_upper = explicit + 2097152
    assert source_upper < LIMIT
    accounting_pin = save('accounting.json', {'schema': 'EU4-R87-RETAINED-SEAL-ACCOUNTING/1',
                                            'original_source_count': len(intake['source_pins']), 'source_before': intake['reads'], 'source_after': after,
                                            'extend_owned_reads': intake['owned_reads'], 'inspection_owned_reads': inspection['reads'], 'seal_owned_reads': owned_reads,
                                            'explicit_source_and_owned_read_bytes': explicit,
                                            'manual_sealer_sources_tool_reads_and_own_finalcheck_allowance': 2097152, 'source_upper_bytes': source_upper, 'source_limit': LIMIT,
                                            'retained_limit': LIMIT, 'all_source_before_after_equal': True, 'memory': memory(),
                                            'root_prior_reads_not_in_this_stage': True, 'OS_loader_IO_complete': False, 'new_producer_runs': 0, 'PE_engine_decoder_game_access': 0})
    report = '''# R87 retained actual author contract

The fixed256B window contains61 retained instructions/210 decoded bytes, six CALL sites to five unexamined targets, one normal RET and two INT3 terminals. The46B suffix remains owned and undecoded. Original localCFG/whole-function flags remain false. CC266 is the normal R86 sequential frontier; CC32C is only a hypothetical seed because the prior SAR3 value cannot satisfy that JE. Actual metadata covers both seeds; the authorized gap exception was not used.

For a valid stable three-zero header and D=0, the selected arithmetic gives size/index/capacity0 and requested count1. The unknown callee950b0 receives RCX8; allocation is only a candidate interpretation. Under normal callee/valid returned-address/noalias/header-stability premises, the explicit store writes the freshly read QWORD payload into S. The subsequent1a35750(S,0,0) is still an unexamined call, and c9d60(C,S,1,1) is the unresolved final header/ownership step. No completed vector update, allocation/cleanup contract or borrow lifetime is claimed.

The retained epilogue places the computed slot address in RAX before restoring R14. Saved RDI/RSI/R12 homes, R14 local, four POPs and RET restore RSP from F=Q-48 to Q+8 only under the stated normal ABI, valid-stack and no saved-slot mutation premises. These observations do not establish native readiness or any game effect.

Root performed the only acquisition. Producer and launcher source bills total18,830,537 bytes under32MiB; two whole-PE hashes,108B metadata and256B code total76,925,372 bytes in a separate account. The retained Job has two cumulative processes, active0, exit0, no error, direct child collected and peak25,493,504 bytes. Outer tool wall time and Job time are separate witnesses. This seal opened only fixed cached text/JSON, never PE/engine/decoder/game, and proposes c9d60 without authorizing another acquisition.
'''
    with (OUT / 'report.md').open('xb') as stream:
        stream.write(report.encode())
    local = {}
    for path in sorted(OUT.rglob('*')):
        if path.is_file():
            local[path.relative_to(ROOT).as_posix()] = pin(path.read_bytes())
    for path in [Path(__file__).resolve(), ROOT / 'work/inspect_r87_actual_20261016.py']:
        local[path.relative_to(ROOT).as_posix()] = pin(path.read_bytes())
    retained = sum(v['bytes'] for name, v in local.items() if name.startswith(OUT.relative_to(ROOT).as_posix() + '/'))
    retained_upper = retained + 262144
    assert retained_upper < LIMIT
    manifest_pin = save('actual-manifest.json', {'schema': 'EU4-R87-AUTHOR-RETAINED-ACTUAL-MANIFEST/1', 'sealed': True,
                                              'subject_source_manifest': reference(BASE + 'source-manifest.json'), 'subject_capture_pin': reference(BASE + 'capture.json'),
                                              'subject_owned_pin': reference(BASE + 'owned-code.json'), 'subject_contract_pin': contract_pin,
                                              'source_pins': intake['source_pins'], 'local_pins': local,
                                              'engine_metadata_witness_pins': source['decoder_expected_witness_pins'], 'engine_bodies_opened_in_this_seal': 0,
                                              'selected_cfg_pin': selected_pin, 'raw_replay_pin': replay_pin, 'resources_pin': resources_pin, 'accounting_pin': accounting_pin,
                                              'author_preview_only': True, 'independent_actual_review_pending': True, 'retained_upper_bytes': retained_upper,
                                              'source_upper_bytes': source_upper, 'all_shells_collected': True, **flags})
    delivery_pin = save('delivery.json', {'schema': 'EU4-R87-AUTHOR-ACTUAL-DELIVERY/1', 'sealed': True,
                                        'actual_manifest_pin': manifest_pin, 'capture_pin': reference(BASE + 'capture.json'), 'owned_code_pin': reference(BASE + 'owned-code.json'),
                                        'contract_pin': contract_pin, 'selected_cfg_pin': selected_pin, 'raw_replay_pin': replay_pin, 'resources_pin': resources_pin,
                                        'accounting_pin': accounting_pin, 'next_scope_proposal_pin': next_pin,
                                        'source_upper_bytes': source_upper, 'retained_upper_bytes': retained_upper,
                                        'author_claims_not_independent_acceptance': True, 'all_shells_collected': True, **flags})
    print(json.dumps({'manifest': manifest_pin, 'delivery': delivery_pin, 'contract': contract_pin, 'selected': selected_pin,
                      'replay': replay_pin, 'resources': resources_pin, 'accounting': accounting_pin, 'next_proposal': next_pin,
                      'source_upper': source_upper, 'retained_upper': retained_upper, 'all_shells_collected': True}))

if __name__ == '__main__':
    assert len(sys.argv) == 2 and sys.argv[1] in ['intake', 'extend', 'seal']
    {'intake': intake, 'extend': extend, 'seal': seal}[sys.argv[1]]()
