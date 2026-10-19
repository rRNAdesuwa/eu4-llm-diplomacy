"""Independent retained-file R80 review. No author code, PE or decoder execution."""
import ast
import collections
import ctypes
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import traceback

ROOT = Path(__file__).resolve().parent.parent
SUB = 'work/reports/war-peace-api-20261016-r80-unregistered-call-prefix/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r80-actual-independent-review-r2'
CAP = 4 * 1024 * 1024
LIMIT = 24 * 1024 * 1024
MANUAL = 1024 * 1024
TAIL = 2 * 1024 * 1024
MEM = 768 * 1024 * 1024
PRIOR_FAILED_STAGE_BYTES = 671038
GAME = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
HARD = {
 'actual-manifest.json': (17047, '4537f650656dab1ce8c9511f65ebe5211adc81c4f10c8a1daf8b0b47db62dc18'),
 'actual-contract.json': (5247, 'b73969a9eabc1c874998f38e29ea0911b050755b290c0188e9725a6563abe73c'),
 'capture.json': (78062, 'b02239c0a90e463e1ed14330634df1114e2c5f80370740143ea27d30cc7bfa01'),
 'owned-code.json': (698, '17ad37416b8798e5f5ffc40a482aa471637ace5e62da5030cc1b11144e7d7598'),
 'actual-selected-evidence.json': (15924, '6bd48ab81e3a493f7115d81585a6f3f4c02f926662b33b6b0cf5b2c485cb794a'),
 'actual-filecheck.json': (7011, 'ac1b350c800d813cc505ec8996756ad9146732a6f6fe57dcf8d85b7be8df79ef'),
 'actual-delivery.json': (3361, '3672d9d28a4963d306985146474651c20a8a99577b7166ddaecb607ae6053b03'),
 'actual-publication-accounting.json': (3052, '486a5a402bd0667c3d704153b784f6ed5eb381e53117ebcd90bd989f38bb3a6f'),
 'actual-completion.json': (1334, '9d9fc60c0e25b7e3a6d1ebad1a1c0b45082cd2868887a76cd706647c60f6a525'),
}
EXPECTED_ROWS = [
 (0x97bd30, '488b4118', 'mov', 'rax, qword ptr [rcx + 0x18]', 'A=M64[O+0x18]'),
 (0x97bd34, '4c8b4910', 'mov', 'r9, qword ptr [rcx + 0x10]', 'B=M64[O+0x10]'),
 (0x97bd38, '48c1e820', 'shr', 'rax, 0x20', 'RAX=A>>32'),
 (0x97bd3c, '480fbfd0', 'movsx', 'rdx, ax', 'I=sext16_to64(A.bits32..47)'),
 (0x97bd40, '488b05891b9c01', 'mov', 'rax, qword ptr [rip + 0x19c1b89]', 'G=M64[module+0x233d8d0]'),
 (0x97bd47, '49c1e920', 'shr', 'r9, 0x20', 'R9=B>>32'),
 (0x97bd4b, '488b8818010000', 'mov', 'rcx, qword ptr [rax + 0x118]', 'T=M64[G+0x118]'),
 (0x97bd52, '410fbfc1', 'movsx', 'eax, r9w', 'J=zext32_to64(sext16_to32(B.bits32..47))'),
 (0x97bd56, '4c8b04d1', 'mov', 'r8, qword ptr [rcx + rdx*8]', 'P=M64[T+8*I]'),
 (0x97bd5a, '488d14c0', 'lea', 'rdx, [rax + rax*8]', 'RDX=9*J modulo2^64; no memory read'),
 (0x97bd5e, '498b8010150000', 'mov', 'rax, qword ptr [r8 + 0x1510]', 'U=M64[P+0x1510]'),
 (0x97bd65, '4c8b04d0', 'mov', 'r8, qword ptr [rax + rdx*8]', 'R8=M64[U+72*J]'),
 (0x97bd69, '488b44d010', 'mov', 'rax, qword ptr [rax + rdx*8 + 0x10]', 'RAX=M64[U+72*J+0x10], not a return'),
]
JOURNAL = []
CACHE = {}
PINS = {}


def require(value, message):
    if not value:
        raise AssertionError(message)


def memory():
    class PMC(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong),
                    ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t),
                    ('PrivateUsage', ctypes.c_size_t)]
    p = PMC(); p.cb = ctypes.sizeof(p)
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.GetCurrentProcess.restype = ctypes.c_void_p
    a = ctypes.WinDLL('psapi', use_last_error=True)
    a.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    require(a.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(p), p.cb), 'self-memory query')
    require(p.PrivateUsage < MEM and p.PeakPagefileUsage < 1024**3, 'own software memory limit')
    return {'private_bytes': p.PrivateUsage, 'peak_pagefile_bytes': p.PeakPagefileUsage}


def digest(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def normalize(name):
    p = (ROOT / name).resolve()
    require(p.is_relative_to(ROOT), 'project-local admitted file')
    rel = p.relative_to(ROOT).as_posix()
    require(not rel.startswith('work/deps/') and p.name.lower() != 'eu4.exe', 'no engine/PE body')
    return rel


def read(name, phase, expected=None):
    rel = normalize(name); p = ROOT / rel
    size = p.stat().st_size
    require(size <= CAP, 'ordinary4MiB before read')
    charged = sum(e['bytes'] for e in JOURNAL)
    require(charged + size + PRIOR_FAILED_STAGE_BYTES + MANUAL + TAIL <= LIMIT, 'own24MiB preread upper')
    memory()
    raw = p.read_bytes(); pin = digest(raw)
    JOURNAL.append({'path': rel, 'phase': phase, **pin})
    require(len(raw) == size, 'file size changed during read')
    if expected is not None:
        require(pin == {k: expected[k] for k in ('bytes', 'sha256')}, 'exact pin: '+rel)
    return raw


def admit(name, pin):
    rel = normalize(name); pin = {k: pin[k] for k in ('bytes', 'sha256')}
    if rel in PINS:
        require(PINS[rel] == pin, 'conflicting flat pin')
    else:
        CACHE[rel] = read(rel, 'before', pin); PINS[rel] = pin
    return rel


def strict(raw):
    def pairs(items):
        obj = {}
        for k, v in items:
            require(k not in obj, 'duplicate JSON key'); obj[k] = v
        return obj
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))


def data(name):
    return strict(CACHE[normalize(name)])


def pin(name):
    rel = normalize(name)
    return {'path': rel, **PINS[rel]}


def save(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / name).open('xb') as f:
        f.write(raw)
    return digest(raw)


def all_false(obj):
    require(isinstance(obj, dict) and obj and all(v is False for v in obj.values()), 'authority false')


def function_lines(text, name):
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == name)
    return '\n'.join(text.splitlines()[node.lineno-1:node.end_lineno])


def review():
    OUT.mkdir(exist_ok=False)
    mem_before = memory()
    for name, (size, sha) in HARD.items():
        admit(SUB+name, {'bytes': size, 'sha256': sha})
    m = data(SUB+'actual-manifest.json')
    require(m['sealed'] is True and m['file_count'] == len(m['files']) == 49, '49 flat actual pins')
    require(m['before_after_sources_equal'] and m['decoder_witness_only_not_rehashed_by_sealer'], 'sealer source witness')
    all_false(m['authority'])
    for name, expected in m['files'].items():
        admit(name, expected)
    delivery = data(SUB+'actual-delivery.json')
    for name, expected in delivery['pins'].items():
        admit(SUB+name, expected)
    for field in ('command_receipts', 'publication_accounting'):
        admit(SUB+('actual-command-receipts.json' if field == 'command_receipts' else 'actual-publication-accounting.json'), delivery[field])
    completion = data(SUB+'actual-completion.json')
    for name, expected in completion['pins'].items():
        admit(SUB+name, expected)
    for previous in ('work/review_r80_actual_20261016.py', 'work/reports/war-peace-api-20261016-r80-actual-independent-review/failure.json'):
        previous_raw=read(previous,'reviewer_R1_failure_preservation')
        admit(previous,digest(previous_raw))
    own_name = Path(__file__).relative_to(ROOT).as_posix()
    own_raw = read(own_name, 'own_source_before'); PINS[own_name] = digest(own_raw); CACHE[own_name] = own_raw

    c = data(SUB+'capture.json'); o = data(SUB+'owned-code.json'); s = data(SUB+'actual-selected-evidence.json')
    contract = data(SUB+'actual-contract.json'); source = data(SUB+'source-manifest.json')
    auth = data(SUB+'run-authorization.json'); claim = data(SUB+'claim.json'); seed = data(SUB+'entry-seed.json')
    require(c['owned_code_pin'] == PINS[SUB+'owned-code.json'] and s['owned_pin'] == PINS[SUB+'owned-code.json'], 'owned binding')
    for field, name in [('capture_pin','capture.json'), ('owned_pin','owned-code.json'), ('selected_pin','actual-selected-evidence.json')]:
        require(contract[field] == PINS[SUB+name], 'contract component binding')
    require(s['capture_pin'] == PINS[SUB+'capture.json'], 'selected capture')
    require(c['source_manifest'] == o['source_manifest'] == auth['source_manifest'] == claim['source_manifest'] == PINS[SUB+'source-manifest.json'], 'base manifest binding')
    require(c['entry_seed_pin'] == auth['entry_seed_pin'] == PINS[SUB+'entry-seed.json'], 'entry binding')
    require(auth['producer_pin'] == PINS[SUB+'produce.py'] and c['authorization_pin'] == claim['authorization_pin'] == PINS[SUB+'run-authorization.json'], 'actual authorization bindings')
    require(auth['sealed'] and auth['root_explicit_start_received'] and auth['single_attempt'] and auth['sole_executor'] == 'diplomacy_static', 'once executor')
    require(auth['operation'] == 'one-fixed-known-CALL-prefix-64B' and auth['requested_bytes'] == 64, 'fixed once window')
    require(claim['automatic_retry'] is False and claim['cached_gap_valid'] and claim['mapping_valid'], 'exclusive claim scope')
    for label in ('root_raw_entry_review', 'source_peer_review', 'upstream_actual_review'):
        pair = auth[label]
        for expected in pair.values():
            require(PINS[normalize(expected['path'])] == {k:expected[k] for k in ('bytes','sha256')}, 'review exact flat admitted')
        findings = data(pair['findings']['path'])
        require(findings['sealed'] and findings['passed'] and findings['blocking_findings'] == [], 'review gate')
        if label != 'upstream_actual_review':
            require(findings['subject_source_manifest'] == PINS[SUB+'source-manifest.json'] and findings['subject_producer'] == PINS[SUB+'produce.py'] and findings['subject_entry_seed'] == PINS[SUB+'entry-seed.json'], 'new R80 three subject gate')
        else:
            for field, old in [('subject_actual_manifest','actual-manifest.json'),('subject_capture_pin','capture.json'),('subject_contract_pin','actual-contract.json'),('subject_selected_pin','actual-selected-evidence.json')]:
                rel = 'work/reports/war-peace-api-20261016-r79-null-selector-callee/'+old
                require(findings[field] == pin(rel), 'R79 fixed full subject witness')
    expected_reviews = {str((ROOT/v['path']).resolve()): {k:v[k] for k in ('bytes','sha256')} for group in (auth[x] for x in ('root_raw_entry_review','upstream_actual_review','source_peer_review')) for v in group.values()}
    require(c['three_review_pins'] == claim['three_review_pins'] == expected_reviews, 'capture exact three reviews')
    require(c['source_pins'] == claim['source_pins'] == source['source_pins'], 'source expected map stable')
    engines = source['decoder_expected_witness_pins']
    require(len(engines) == 38 and engines == c['decoder_expected_witness_pins'] == m['decoder_expected_witness_pins'], '38 metadata engine witnesses only')
    require(source['actual_source_pin_count'] == len(source['actual_source_pins']) == 26 and len(source['source_pins']) == 64, '26 actual plus38 engine')
    require(source['source_pins'] == source['actual_source_pins'] | engines, 'source split exact')
    for name, expected in source['actual_source_pins'].items():
        require(PINS[normalize(name)] == expected, 'actual subset currently read, no recursive closure')

    raw = bytes.fromhex(o['raw_hex']); require(len(raw) == o['bytes'] == 64 and hashlib.sha256(raw).hexdigest() == o['sha256'], 'owned64B raw digest')
    require(o['window'] == c['window'] == ['0x97bd30','0x97bd70'] and o['file_offset'] == 9941296, 'owned prefix mapping')
    require(raw == bytes.fromhex(''.join(x[1] for x in EXPECTED_ROWS)+'48c1'), 'all64 exact bytes')
    rows = c['analysis']['instructions']
    require(len(rows) == 13 and rows == s['retained_decoder_rows'], 'all retained decoder rows reused exact')
    require(len(s['all13_raw_reviewed_rows']) == 13, '13 manual rows')
    offset = 0; loads = []; manual_rows = []
    for actual, selected, (rva, code, mnemonic, operands, meaning) in zip(rows, s['all13_raw_reviewed_rows'], EXPECTED_ROWS):
        b = bytes.fromhex(code)
        require(rva == 0x97bd30+offset and raw[offset:offset+len(b)] == b, 'contiguous exact owned row')
        require((actual['rva'],actual['bytes'],actual['mnemonic'],actual['operands']) == (hex(rva),code,mnemonic,operands), 'manual opcode agrees retained text')
        require((selected['rva'],selected['raw_hex'],selected['mnemonic'],selected['operands']) == (hex(rva),code,mnemonic,operands), 'selected manual row binding')
        require(selected['explicit_memory_write'] is False and selected['implicit_stack_write'] is False and selected['runtime_observed'] is False, 'selected boundary flags')
        # 8B load direction follows raw8B opcode/modrm; 8D is address-only.
        if mnemonic == 'mov' and 'qword ptr' in operands:
            require(len(actual['memory_operands']) == 1, 'one memory operand')
            memop=actual['memory_operands'][0]
            require(memop['width_bytes'] == 8 and memop['read'] and not memop['write'], 'QWORD source direction')
            loads.append(hex(rva))
        elif mnemonic == 'lea':
            require(code == '488d14c0', 'LEA raw encoding')
        else:
            require(actual['memory_operands'] == [], 'register-only shift/sign extension')
        manual_rows.append({'rva':hex(rva),'bytes':code,'operation':meaning,'explicit_store':False})
        offset += len(b)
    require(offset == c['analysis']['decoded_unique_bytes'] == s['complete_decoded_instruction_bytes'] == 62 and len(loads) == 8, '62 complete /8 QWORD loads')
    partial = [{'kind':'undecodable_or_partial','rva':'0x97bd6e','raw_hex':'48c1'}]
    require(c['analysis']['edges'] == [] and c['analysis']['terminals'] == s['partial'] == partial, 'partial only terminal, no inferred effects')
    require(c['analysis']['undecoded_owned_intervals'] == [['0x97bd6e','0x97bd70']] and not c['analysis']['local_normal_CFG_closed'], 'not normal closed')
    require(s['semantic_memory_reads'] == {'qword_loads':8,'bytes_per_load':8,'total_instruction_read_widths':64,'not_additional_PE_or_runtime_reads':True,'LEA_excluded':True}, 'semantic vs acquisition read distinction')
    require(s['partial_owned_bytes'] == 2 and s['implicit_entry_CALL_stack_write_bytes'] == 8 and s['entry_CALL_is_prior_scope_not_a_new_prefix_instruction'], 'entry CALL write not omitted')
    require(s['new_instruction_decode_by_sealer'] == 0, 'retained sealer did not decode')
    disp = struct.unpack('<i', bytes.fromhex('891b9c01'))[0]
    require(0x97bd47+disp == 0x233d8d0, 'RIP MOV target arithmetic')
    require(s['RIP_arithmetic']['target_rva'] == '0x233d8d0' and s['RIP_arithmetic']['target_data_read'] is False, 'RIP data unacquired')
    caller = data('work/reports/war-peace-api-20261016-r69-generator-divisor-source/owned-code.json')
    callerraw = bytes.fromhex(caller['raw_hex']); calloff = 0x99358a-int(caller['window'][0],16)
    call = callerraw[calloff:calloff+5]
    require(call.hex() == 'e8a187feff' and 0x99358f+struct.unpack('<i',call[1:])[0] == 0x97bd30, 'old direct CALL entry seed')
    require(seed['stack_evidence']['callee_entry_RSP'] == 'F-8=S69-0x60 under valid normal CALL transfer', 'entry stack relation')
    require(seed['new_pdata_bytes'] == 0 and seed['unread_before_entry_bytes'] == 15 and seed['unread_after_window_bytes'] == 48, 'fixed gap partition')
    require(c['cached_previous'] == seed['cached_previous'] and c['cached_next'] == seed['cached_next'], 'exact cached descriptor binding')
    prev = c['cached_previous']; nxt = c['cached_next']
    require(prev['index'] == 19063 and nxt['index'] == 19064 and bytes.fromhex(prev['raw_hex']) == bytes.fromhex('90bc970021bd9700e4c0e701') and bytes.fromhex(nxt['raw_hex']) == bytes.fromhex('a0bd97003cbe97001898dc01'), 'cached neighbor exact raw')
    require(struct.unpack('<III',bytes.fromhex(prev['raw_hex'])) == (0x97bc90,0x97bd21,0x1e7c0e4) and struct.unpack('<III',bytes.fromhex(nxt['raw_hex'])) == (0x97bda0,0x97be3c,0x1dc9818), 'cached metadata widths')
    oldcap = data('work/reports/war-peace-api-20261016-r79-null-selector-callee/capture.json')
    require(oldcap['pdata_requests'][17] == prev and oldcap['pdata_requests'][19] == nxt, 'cached only, no new pdata')
    anchors = data('work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json')
    matches = [q for q in anchors['sections'] if int(q['rva'],16) <= 0x97bd30 and 0x97bd70 <= int(q['rva'],16)+q['raw_size']]
    require(len(matches) == 1 and matches[0]['name'] == '.text', 'unique cached text mapping')
    require(matches[0]['raw_file_offset']+0x97bd30-int(matches[0]['rva'],16) == 9941296, 'file offset cached arithmetic')

    mask64=(1<<64)-1
    width_examples=[]
    for low16 in (0,0x7fff,0x8000,0xffff):
        signed = low16 if low16<0x8000 else low16-0x10000
        I = signed & mask64; J = signed & 0xffffffff
        width_examples.append({'source_16bit':hex(low16),'signed_value':signed,'I_RDX64':hex(I),'J_RAX_after_EAX_write':hex(J),'second_index_9J':hex(9*J & mask64),'second_byte_displacement_72J':hex(72*J & mask64)})
    require(width_examples[-1]['I_RDX64'] == '0xffffffffffffffff' and width_examples[-1]['J_RAX_after_EAX_write'] == '0xffffffff', 'negative16 width counterexample')

    analysis=c['analysis']; looks=analysis['lookahead_inputs']
    coverage=set()
    for e in looks:
        start=int(e['rva'],16); require(0x97bd30<=start<0x97bd70 and start+e['bytes']<=0x97bd70, 'owned decoder input')
        coverage.update(range(start,start+e['bytes']))
    require(len(looks)==14 and sum(e['bytes'] for e in looks)==185 and len(coverage)==64 and 185-64==121, 'decoder lookahead overlap not PE reads')
    require((analysis['decoder_input_total_bytes'],analysis['decoder_input_unique_bytes'],analysis['decoder_overlap_bytes']) == (185,64,121), 'retained decoder bill')
    require(c['new_pdata_requests'] == [] and c['new_pdata_physical_bytes'] == 0 and c['new_header_data_literal_vtable_unwind_callee_bytes'] == 0, 'no new metadata/data')
    require(c['sparse_reads'] == [{'kind':'known_CALL_prefix','rva':'0x97bd30','end_exclusive':'0x97bd70','file_offset':9941296,'requested_bytes':64,'bytes':64,'complete':True}], 'single exact targeted read')
    require(c['full_PE_authentication_reads'] == [{'phase':phase,'bytes_read':38462504,'completed':True,'sha256':GAME} for phase in ('before','after')], 'two completed SHA witnesses')
    require(c['total_PE_physical_bytes'] == 38462504*2+64 == 76925072, 'separate PE bill')
    source_events=c['source_file_reads']; require(len(source_events)==158 and sum(e['bytes'] for e in source_events)==c['source_file_read_bytes']==17127251, 'source journal sum')
    expected_by_abs = {str((ROOT/n).resolve()):v for n,v in source['source_pins'].items()}
    expected_by_abs.update({str((ROOT/n).resolve()):v for n,v in PINS.items()})
    for e in source_events:
        require(e['path'] in expected_by_abs and e['bytes']==expected_by_abs[e['path']]['bytes'], 'completed source event size and known flat or engine metadata')
    source_phases=collections.Counter((e['phase'],e['operation']) for e in source_events)
    require(source_phases[('source_engine_before','streaming_engine_pin')]==38 and source_phases[('source_engine_after','streaming_engine_pin')]==38, 'engine witness prepost38')
    for phase in ('source_engine_before','source_engine_after'):
        observed={e['path']:e['bytes'] for e in source_events if e['phase']==phase and e['operation']=='streaming_engine_pin'}
        require(observed == {str((ROOT/n).resolve()):v['bytes'] for n,v in engines.items()}, 'engine event names/bytes metadata replay only')
    require(c['normal_target_context_exit'] and c['commit_after_target_close_and_final_guards'] and c['source_engine_before_after_equal'], 'normal close/postguards capture witness')
    require(c['R79_unknown_preserved'] and not c['known_function_extent'] and not c['whole_function_owned'] and c['decoder_loaded'], 'bounded prefix evidence level')
    for field in ('game_process_accesses','Frida_operations','native_game_calls','requests','tests'):
        require(c[field]==0, 'no runtime requests witness')
    all_false(contract['authority'])
    for field in contract['authority']:
        if field in c: require(c[field] is False, 'capture authority false')

    text=CACHE[SUB+'produce.py'].decode('utf-8'); guard=function_lines(text,'source_guard'); main=function_lines(text,'main')
    require(guard.index('raw_manifest=read_source') < guard.index('==expected_manifest_pin') < guard.index('json.loads(raw_manifest)') < guard.index('for name,expected in pins.items()'), 'single rawbuffer authorized pin before parse and engine')
    require(main.count('source_guard(base_pin)')==2, 'both guards same authorized base')
    require(main.index("for label in ('root_raw_entry_review'") < main.index('base,pins=source_guard(base_pin)') < main.index("with (ROOT.parent/'eu4.exe').open"), 'three gates before engine and PE')
    require(main.index("require(stream_pin(HERE/'source-manifest.json')==base_pin,'Manifest changed before") < main.index('base,pins=source_guard(base_pin)') < main.index("require(stream_pin(HERE/'source-manifest.json')==base_pin,'Manifest changed after"), 'initial external base checks')
    require(main.index("save('claim.json'") < main.index("with (ROOT.parent/'eu4.exe').open"), 'exclusive claim before target')
    require(main.index('TARGET_CONTEXT_NORMAL_EXIT=True') < main.index('_,post=source_guard(base_pin)') < main.index("save('capture.json',value)"), 'target context exit before postguards and publish')
    save_tree = ast.parse(function_lines(text,'save'))
    require(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='open' and n.args and isinstance(n.args[0],ast.Constant) and n.args[0].value in ('x','xb') for n in ast.walk(save_tree)), 'exclusive output writes (text x or binary xb)')
    require('No external target/address/path override' in main and 'Already claimed or failed; no retry' in main, 'fixed noarg no retry')

    cmd=data(SUB+'actual-command.json'); commands=data(SUB+'actual-command-receipts.json')
    require(cmd['exit_code']==0 and cmd['direct_child_collected'] and cmd['retry'] is False and cmd['hard_Job_installed'] is False and cmd['before']==cmd['after'], 'actual one child success/unchanged pins')
    for name, expected in cmd['before'].items(): require(expected==PINS[SUB+name], 'command source pin')
    require(cmd['argv'][-1]==SUB+'produce.py' and len(cmd['argv'])==3, 'single noarg invocation')
    require(commands['all_shells_collected'] and commands['actual_attempts']==1 and commands['retries']==0 and [e['exit_code'] for e in commands['commands']]==[0,0,0], 'collected actual/seal/check witnesses')
    require(completion['all_shells_collected'] and completion['commands_all_exit_zero'] and completion['actual_attempts']==1 and completion['retries']==0 and completion['publication_tool_receipt']['exit_code']==0, 'publication collection')
    for name in ('actual.stderr.txt','actual-seal.stderr.txt','actual-check.stderr.txt','actual-publication.stderr.txt'):
        require(CACHE[SUB+name]==b'', 'retained stderr empty')
    stdout=strict(CACHE[SUB+'actual.stdout.txt'])
    require(stdout['rows']==13 and stdout['code_bytes']==64 and stdout['source_journal_bytes']==17127251 and stdout['status']==c['status'], 'actual stdout consistent')
    filecheck=data(SUB+'actual-filecheck.json'); account=data(SUB+'actual-read-accounting.json'); publication=data(SUB+'actual-publication-accounting.json')
    require(filecheck['passed'] and filecheck['subject_manifest']==PINS[SUB+'actual-manifest.json'] and filecheck['file_count']==49 and sum(e['bytes'] for e in filecheck['read_events'])==filecheck['read_bytes']==613048, 'first author filecheck bill')
    require(sum(e['bytes'] for e in account['measured_read_events'])==account['measured_read_bytes']==1116974 and len(account['measured_read_events'])==90, 'seal measured completed reads')
    require(sum(e['bytes'] for e in publication['publication_read_events'])==publication['publication_measured_bytes']==147680, 'publication measured18')
    require(publication['seal_measured_bytes']==1116974 and publication['first_check_measured_bytes']==613048 and publication['manual_orchestration_allowance_bytes']==1048576, 'publication bill inputs')
    upper=1116974+613048+147680+1048576+114464
    require(upper==publication['successful_upper_with_remaining_publication_allowance_bytes']==3040742 and upper<16*1024*1024, 'retained successful conservative upper')
    require(completion['completion_measured_read_bytes']==11249 and completion['within_final_publication_reserve'], 'completion covered by remaining allowance')
    require(publication['producer_source_bytes_separate']==17127251 and publication['PE_SHA_plus_targeted_bytes_separate']==76925072 and publication['full_OS_IO_claim'] is False, 'source PE retained separated')
    require(contract['resources']['producer_calls']==1 and contract['resources']['producer_peak_committed_bytes_witness']==c['peak_committed_bytes_observed']==22691840 and c['hard_Job_installed'] is False, 'resource witness no hardJob')

    raw_replay={'schema':'EU4-R80-INDEPENDENT-RAW-REPLAY/1','all64_raw_owned_sha256':o['sha256'],'decoded_rows':manual_rows,'complete_bytes':62,'partial':partial,'loaded_qword_sites':loads,'qword_load_count':8,'LEA_is_memory_read':False,'decoded_CALL_branch_RET_store_count':0,'no_new_decoder':True,
     'width_arithmetic_examples':width_examples,'conditional_register_projection':contract['conditional_projection'],
     'all_address_arithmetic_modulo': '2^64; valid access and normal CALL transfer required',
     'raw_call_math':{'site':'0x99358a','raw':call.hex(),'signed_rel32':struct.unpack('<i',call[1:])[0],'next':'0x99358f','target':'0x97bd30'},
     'RIP_math':{'site':'0x97bd40','next':'0x97bd47','signed_displacement':disp,'target':'0x233d8d0','data_opened':False},
     'cached_metadata':{'previous':prev,'next':nxt,'new_read_bytes':0},
     'decoder_witness':{'lookahead_requests':14,'total_inputs':185,'unique_owned':64,'repeated_inputs':121,'complete_decoded':62,'partial_owned':2}}
    save('raw-replay.json',raw_replay)
    for name, expected in list(PINS.items()):
        read(name,'after',expected)
    mem_after=memory()
    own_charged=sum(e['bytes'] for e in JOURNAL)
    require(own_charged+PRIOR_FAILED_STAGE_BYTES+MANUAL+TAIL<=LIMIT, 'own review final upper')
    findings={'schema':'EU4-R80-ACTUAL-INDEPENDENT-REVIEW/1','sealed':True,'passed':True,'blocking_findings':[],
     'scope':'complete non-author retained-file/raw semantic review of the separately authorized fixed64B known-CALL prefix only',
     'subject_actual_manifest':pin(SUB+'actual-manifest.json'),'subject_capture_pin':pin(SUB+'capture.json'),
     'subject_contract_pin':pin(SUB+'actual-contract.json'),'subject_owned_pin':pin(SUB+'owned-code.json'),'subject_selected_pin':pin(SUB+'actual-selected-evidence.json'),
     'subject_source_manifest':pin(SUB+'source-manifest.json'),'subject_producer':pin(SUB+'produce.py'),'subject_authorization':pin(SUB+'run-authorization.json'),
     'role_disclosure':{'R80_actual_author':'diplomacy_static; not this reviewer','reviewer':'war_api','previous_roles':['R79 source/producer design and actual author','R78 full independent reviewer','R69 original source designer and later actual full reviewer'],
       'R79_fullreview':'validation_audit fixed accepted findings/manifest witness; no recursive re-review','independence_limit':'Independent of R80 actual author, but not all upstream historical source design. All named prior-role overlaps disclosed.'},
     'result':{'owned_bytes':64,'complete_instructions':13,'complete_instruction_bytes':62,'partial_owned_bytes':2,'QWORD_loads':8,'LEA_memory_reads':0,'decoded_calls_branches_returns_explicit_stores':0,'whole_function_closed':False,'RAX_return_verified':False},
     'machine_checks':['All13 retained rows match the owned64B, manual opcode direction, operand width and contiguous offsets; partial48c1 is unclassified.',
       'RawMOVSX480fbfd0 extends AX to64-bit RDX; raw410fbfc1 extends R9W to32-bit EAX then clears RAX upper32. Negative16 examples distinguish their64-bit index values.',
       'Eight ordered loads only: O18/O10/module233d8d0/G118/T+8I/P1510/U+72J/U+72J+10. No target data was read by this review.',
       'The fixed old E8 signedrel32 and RIP displacement reproduce the entry and module slot; cached pdata neighbors and unique cached.text mapping reproduce the64B window without new PE/pdata access.',
       'No decoded RSP change or memory write; incoming CALL pushes8B, and runtime aliases/partial/tail remain unknown. No no-side-effect/full-function proof.'],
     'source_control':['Three exact accepted subject-bound reviews and new root once grant precede engine/PE work in source; the retained claim and command pins agree.',
       'The authorized manifest rawbuffer is bytes/SHA checked before JSON parsing or engine selection; both source_guard calls use base_pin and initial outer checks bracket the first guard.',
       'Normal target context exit precedes post-source/engine/auth/review checks and capture publish. Exclusive output and no-retry guards remain.',
       '158 completed source events total17127251B, including38 engine pin events each phase; engine bodies were not stat/opened by this audit. Pre/post equality is witness evidence, not atomic/ABA exclusion.'],
     'author_resources':{'targeted_code_bytes':64,'new_pdata_bytes':0,'two_SHA_bytes':76925008,'total_PE_bytes':76925072,'producer_source_completed_events':158,'producer_source_completed_bytes':17127251,
       'retained_successful_upper_bytes':3040742,'retained_frozen_prior_upper_bytes':6621998,'completion_read_bytes_within_remaining_allowance':11249,
       'producer_peak_committed_bytes_witness':22691840,'hard_Job_installed':False,'all_author_shells_collected_witness':True,'actual_attempts':1,'retries':0,
       'not_claimed':'No whole-OS/loader I/O, independent producer peak, universal failure-path budget or hard process-tree memory guarantee.'},
     'review_resources':{'flat_subject_file_count':len(PINS)-1,'own_script_pin':pin(own_name),'source_pin_before_after_equal':True,'completed_read_events':len(JOURNAL),'completed_read_bytes':own_charged,'prior_failed_review_stage_bytes':PRIOR_FAILED_STAGE_BYTES,
       'manual_inspection_allowance_bytes':MANUAL,'sealing_check_and_report_reserve_bytes':TAIL,'review_upper_bytes':own_charged+PRIOR_FAILED_STAGE_BYTES+MANUAL+TAIL,'review_budget_bytes':LIMIT,'ordinary_file_limit_bytes':CAP,'software_guard_bytes':MEM,'hard_stop_bytes':1024**3,'self_memory_before':mem_before,'self_memory_after':mem_after,
       'engine_witness_pin_count':38,'engine_bodies_stat_or_opened':0,'manual_allowance_includes':'Initial schema/directory inspections and focused author source text reads before this admitted-flat reviewer.'},
     'limits':['The64B prefix owns only13 complete instructions and an undecoded2B tail. Remaining48B to the cached next boundary and normal return are not acquired or inferred.',
       'Original incoming RDX/R8 are overwritten before the visible address use, but loaded pointers may alias D/header/stack/globals. No finalD0 or unchanged-header conclusion.',
       'Current module pointee and all pointed data, bounds/generation/roles/classes, units/currency/recipient/peace effects, lifetime and host compatibility remain unknown.',
       'R79 bounded unknown0code and historical files remain unchanged; this R80 scope is neither R79 retry nor global unwind absence proof.',
       'No R81 read/run permission or source-ready inference is granted by this review. Future scopes require their own source/raw/full gates and root grant.'],
     'precision_notes':['Own R1 reviewer failed after671038B on an over-specific xb check: author uses correct exclusive UTF-8 text x mode. Original reviewer source and full failure/read journal preserved; R2 only accepts the actual exclusive text form and carries prior read charges. No author source/actual was changed or repeated.',
       'Eight64-bit semantic loads sum64B of instruction read width; they are not64B of runtime or additional PE acquisition.',
       'The decoder185 cumulative input bytes are overlapping views of64 owned bytes, not185 physical target reads.',
       'SHR R9,32 is the last decoded flags writer. DF is inherited unknown; no successor condition or partial instruction effect is filled in.',
       'Collected-command receipts describe direct children and authored logs; the reviewer did not independently observe the prior actual processes.'],
     'operations':{'author_programs_tests_executed':0,'PE_stat_open_read':0,'engine_body_stat_open':0,'decoder_import_or_decode':0,'game_process_access':0,'Frida':0,'native_calls':0,'requests':0,'all_review_shells_collected':True},
     'authority':dict(contract['authority'])}
    save('findings.json',findings)
    save('read-accounting.json',{'schema':'EU4-R80-INDEPENDENT-READ-ACCOUNTING/1','events':JOURNAL,'measured_completed_bytes':own_charged,'prior_failed_review_stage_bytes':PRIOR_FAILED_STAGE_BYTES,'manual_allowance_bytes':MANUAL,'reserved_tail_bytes':TAIL,'successful_upper_bytes':own_charged+PRIOR_FAILED_STAGE_BYTES+MANUAL+TAIL,'budget_bytes':LIMIT,'full_OS_IO_claim':False})
    text_report=("R80 retained-only full independent review: PASSED, no blocking differences.\n\n"
      "All64 owned bytes and13 complete instructions were checked without PE/decoder access. Eight QWORD loads are observed; LEA is arithmetic. Signed16-to64 RDX and signed16-to32 EAX (zero high32) give different64-bit values for a negative slot. The2B partial48c1 remains undecoded; no RET, function closure, finalD/header, type/unit/recipient or effect is established.\n\n"
      "Exact three-review/root authorization, claim, normal-close then postguard capture order,158 source events and separate SHA/code/retained bills match. Thirty-eight engine pins are metadata witnesses only. The R79 full review is a fixed external witness, not recursively re-audited. Reviewer was R79 author and R78 full reviewer; R80 actual author is diplomacy_static.\n\n"
      "All runtime/ready/effect/lease/retry permissions remain false. No new scope or R81 actual is authorized.\n")
    with (OUT/'report.md').open('x',encoding='utf-8',newline='\n') as f:f.write(text_report)
    manifest_pins=dict(PINS)
    for name in ('raw-replay.json','findings.json','read-accounting.json','report.md'):
        rel=(OUT/name).relative_to(ROOT).as_posix(); manifest_pins[rel]=digest(read(rel,'own_output_seal'))
    save('manifest.json',{'schema':'EU4-R80-ACTUAL-INDEPENDENT-MANIFEST/1','sealed':True,'passed':True,'file_count':len(manifest_pins),'files':manifest_pins,'subject_actual_manifest':pin(SUB+'actual-manifest.json'),'engine_metadata_only':True,'engine_witness_count':38,'authority':dict(contract['authority'])})
    print(json.dumps({'status':'sealed_retained_review_passed','findings':digest((OUT/'findings.json').read_bytes()),'manifest':digest((OUT/'manifest.json').read_bytes()),'source_files':len(PINS)-1,'review_upper_bytes':own_charged+PRIOR_FAILED_STAGE_BYTES+MANUAL+TAIL,'all_review_shells_collected':True}))


def check():
    raw=read((OUT/'manifest.json').relative_to(ROOT).as_posix(),'review_check_manifest')
    m=strict(raw)
    require(m['sealed'] and m['passed'] and m['file_count']==len(m['files']), 'own sealed manifest')
    for name, expected in m['files'].items():read(name,'review_first_check',expected)
    result={'schema':'EU4-R80-INDEPENDENT-FIRST-FILECHECK/1','passed':True,'subject_manifest':digest(raw),'file_count':len(m['files']),'read_events':len(JOURNAL),'read_bytes':sum(e['bytes'] for e in JOURNAL),'author_program_PE_engine_decoder_test_game_native_operations':0,'all_shells_collected':True}
    save('verification.json',result);print(json.dumps(result))


if __name__=='__main__':
    try:
        if sys.argv[1:]==['--check']:check()
        else:
            require(sys.argv[1:]==[], 'only own review or first filecheck');review()
    except BaseException:
        if OUT.exists():
            with (OUT/'failure.json').open('x',encoding='utf-8') as f:json.dump({'traceback':traceback.format_exc(),'read_events':JOURNAL,'read_bytes':sum(e['bytes'] for e in JOURNAL),'author_runtime_not_repeated':True},f,indent=2)
        raise
