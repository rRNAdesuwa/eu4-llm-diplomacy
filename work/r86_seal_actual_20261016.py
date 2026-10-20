from pathlib import Path
import ctypes
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[1]
BASE = 'work/reports/war-peace-api-20261016-r86-cc220-actual-source/'
HERE = ROOT / BASE
OUT = HERE / 'actual-sealed-r1'
CAPTURE_PIN = {'bytes': 85315, 'sha256': 'e3a06664b11a14f483705cd3ae4852b0cd562a85ab46ac7395bfc428673bb28f'}
OWNED_PIN = {'bytes': 635, 'sha256': '65d0c63efdc37f369bb8aa4f0f55a0a5c3d59c79db8bc37e98723a30048fde82'}
SOURCE_PIN = {'bytes': 22473, 'sha256': '74f6c8f8eeeadea9e4216c7b37e2a8034e9fb7967d8dfe7167c7ee1ffd143472'}
AUTH_PIN = {'bytes': 3987, 'sha256': '3a7f3b87fef91f83b2909f66c5d61410abd8680ff3bb171f6a3c664c90a32cd5'}
PRODUCER_PIN = {'bytes': 27099, 'sha256': '0a3c13e779e4da424316b0e3a3ff3f86f49a460243f18b14c91644ca717522b4'}
CLAIM_PIN = {'bytes': 12761, 'sha256': 'd16e8a207844dd6d254292baed70e38c442365139eb9647e4fb763acf92a74c0'}
SOURCE_LIMIT = RETAINED_LIMIT = 16 * 1024 * 1024
LEDGER = []

def require(ok, message):
    if not ok: raise ValueError(message)

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def triple(rel, expected):
    return {'path': rel, **expected}

def memory_guard():
    class PMC(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong),
            ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
            ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
            ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
            ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
    p = PMC(); p.cb = ctypes.sizeof(p)
    g = ctypes.windll.kernel32.GetCurrentProcess; g.restype = ctypes.c_void_p
    require(ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(g()), ctypes.byref(p), p.cb), 'Own memory query')
    require(max(p.WorkingSetSize, p.PagefileUsage) <= 768 * 1024 * 1024, 'Own software memory guard')
    return {'working_set_bytes': p.WorkingSetSize, 'committed_bytes': p.PagefileUsage,
        'peak_working_set_bytes': p.PeakWorkingSetSize, 'peak_committed_bytes': p.PeakPagefileUsage}

def read(rel, expected, phase):
    require(not rel.startswith('work/deps/'), 'Engine metadata only, never opened by sealer')
    p = ROOT / rel
    require(p.stat().st_size <= 4 * 1024 * 1024, 'Ordinary source size')
    raw = p.read_bytes()
    LEDGER.append({'phase': phase, 'path': rel, **pin(raw)})
    require(sum(x['bytes'] for x in LEDGER) + 264684 <= SOURCE_LIMIT, 'Source read cap')
    require(pin(raw) == expected, 'Fixed raw source pin: ' + rel)
    memory_guard()
    return raw

def save(name, value):
    raw = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
    with (OUT / name).open('xb') as f: f.write(raw)
    return triple((OUT / name).relative_to(ROOT).as_posix(), pin(raw))

def main():
    OUT.mkdir(exist_ok=False)
    save('seal-claim.json', {'schema': 'EU4-R86-RETAINED-SEAL-CLAIM/1', 'single_new_retained_stage': True,
        'root_executed_producer': True, 'producer_runs_here': 0, 'PE_reads_here': 0,
        'source_limit': SOURCE_LIMIT, 'retained_limit': RETAINED_LIMIT, 'preflight_source_bytes': 264684})
    buffers = {}
    # Each first raw buffer is pinned before parsing; source graph is flat, not recursive.
    for rel, expected in [(BASE + 'source-manifest.json', SOURCE_PIN), (BASE + 'capture.json', CAPTURE_PIN),
                          (BASE + 'owned-code.json', OWNED_PIN), (BASE + 'run-authorization.json', AUTH_PIN)]:
        buffers[rel] = read(rel, expected, 'before')
    source = json.loads(buffers[BASE + 'source-manifest.json'])
    capture = json.loads(buffers[BASE + 'capture.json'])
    owned = json.loads(buffers[BASE + 'owned-code.json'])
    auth = json.loads(buffers[BASE + 'run-authorization.json'])
    expected_sources = dict(source['actual_source_pins'])
    require(len(expected_sources) == 22 and len(source['decoder_expected_witness_pins']) == 38, 'Prepared flat source/engine counts')
    expected_sources.update({BASE + 'source-manifest.json': SOURCE_PIN, BASE + 'capture.json': CAPTURE_PIN,
        BASE + 'owned-code.json': OWNED_PIN, BASE + 'run-authorization.json': AUTH_PIN, BASE + 'claim.json': CLAIM_PIN})
    for name in ['root_raw_entry_review', 'source_peer_review', 'upstream_plan_review']:
        for ref in auth[name].values():
            expected_sources[ref['path']] = {k: ref[k] for k in ('bytes', 'sha256')}
    for rel, expected in expected_sources.items():
        if rel not in buffers: buffers[rel] = read(rel, expected, 'before')
    require(len(expected_sources) == 31, 'Flat actual source count')
    require(expected_sources[BASE + 'produce.py'] == PRODUCER_PIN, 'Frozen producer identity')
    require(auth['schema'] == 'EU4-R86-ROOT-AUTHORIZATION/1' and auth['sealed'] is True
        and auth['root_explicit_start_received'] is True and auth['single_attempt'] is True, 'Root once grant')
    require(auth['operation'] == 'one-fixed-callee-cc220-static' and auth['source_manifest'] == SOURCE_PIN
        and auth['producer_pin'] == PRODUCER_PIN, 'Fixed root scope/source')
    for name in ['root_raw_entry_review', 'source_peer_review', 'upstream_plan_review']:
        review = json.loads(buffers[auth[name]['findings']['path']])
        require(review['sealed'] is True and review['passed'] is True and review['blocking_findings'] == [], 'Review gate')
    claim = json.loads(buffers[BASE + 'claim.json'])
    require(claim['authorization_pin'] == AUTH_PIN and claim['source_manifest'] == SOURCE_PIN
        and claim['source_pins'] == capture['source_pins'] and claim['automatic_retry'] is False, 'Actual exclusive claim binding')
    require(capture['authorization_pin'] == AUTH_PIN and capture['source_manifest'] == SOURCE_PIN
        and capture['entry_rva'] == '0xcc220' and capture['raw_call_hex'] == 'e882d074ff', 'Capture binding')
    require(capture['normal_target_context_exit'] is True and capture['commit_after_target_close_and_final_guards'] is True
        and capture['source_engine_before_after_equal'] is True, 'Published normal postguard flags')
    expected_opaque = {**source['actual_source_pins'], **source['decoder_expected_witness_pins']}
    require(capture['source_pins'] == expected_opaque and source['decoder_expected_witness_pins'] == capture['decoder_expected_witness_pins'], 'Source/decoder witness maps')
    producer = buffers[BASE + 'produce.py'].decode()
    require(producer.index("TARGET_CONTEXT_NORMAL_EXIT=True;PHASE='source_engine_after'") < producer.index("_,post=source_guard(base_pin)")
        < producer.index("save('capture.json',value)"), 'Source-defined close/postguard/publish order')
    require("post==pins and stream_pin(HERE/'source-manifest.json')==base_pin" in producer, 'Source final equality guard')
    code = bytes.fromhex(owned['raw_hex'])
    require(len(code) == owned['bytes'] == 70 and owned['window'] == ['0xcc220', '0xcc266']
        and hashlib.sha256(code).hexdigest() == owned['sha256'], 'Owned raw code')
    require(capture['owned_code_pin'] == OWNED_PIN and owned['source_manifest'] == SOURCE_PIN, 'Owned source/pin')
    rows = capture['analysis']['instructions']
    expected_hex = ['4053','55','4155','4157','4883ec28','488b4108','4c8bfa','488b11','498bef','482bea',
        '482bc2','4d8be8','48c1fd03','48c1f803','49b8ffffffffffffff1f','488bd9','493bc0','0f84cd000000','488b4910','482bca']
    require(len(rows) == 20 and [r['bytes'] for r in rows] == expected_hex, 'Retained 20 raw instructions')
    cursor = 0xcc220
    for row in rows:
        require(int(row['rva'], 16) == cursor, 'Contiguous row RVA')
        r = bytes.fromhex(row['bytes']); offset = cursor - 0xcc220
        require(code[offset:offset + len(r)] == r, 'Raw instruction slice')
        cursor += len(r)
    require(cursor == 0xcc266, 'Full selected pdata bytes only')
    require(0xcc259 + 6 + struct.unpack('<i', bytes.fromhex('cd000000'))[0] == 0xcc32c, 'JE signed-rel32')
    require(not any(r['mnemonic'] in ('call','ret','int3') for r in rows), 'No decoded CALL/RET/INT3 in this slice')
    require(capture['analysis']['local_normal_CFG_closed'] is False and capture['analysis']['decoded_unique_bytes'] == 70, 'Finite partial CFG')
    require(len(capture['pdata_requests']) == 19 and capture['pdata_physical_bytes'] == 228 and capture['pdata_unique_bytes'] == 192, 'Pdata accounting')
    for record in capture['pdata_requests']:
        b,e,u = struct.unpack('<III', bytes.fromhex(record['raw_hex']))
        require((hex(b),hex(e),hex(u)) == (record['begin_rva'],record['end_exclusive'],record['unwind_rva_unfollowed']), 'Raw pdata width')
    require(capture['selected']['raw_hex'] == '20c20c0066c20c0054aedc01' and capture['next']['raw_hex'] == '66c20c008cc20c0028dddc01', 'Selected and next exact descriptors')
    require(capture['exact_pdata_begin'] is True and capture['selected_bounds_valid'] is True
        and owned['full_extent_owned'] is True, 'Extent ownership distinct from function closure')
    require(sum(x['bytes'] for x in capture['source_file_reads']) == capture['source_file_read_bytes'] == 16772282, 'Producer completed source journal')
    require(len(capture['source_file_reads']) == 148, 'Producer source event count')
    require(sum(x['bytes_read'] for x in capture['full_PE_authentication_reads']) == 76925008
        and sum(x['bytes'] for x in capture['sparse_reads']) == 298
        and capture['total_PE_physical_bytes'] == 76925306, 'Separate PE byte arithmetic')
    require(capture['analysis']['decoder_input_total_bytes'] == 278
        and capture['analysis']['decoder_input_unique_bytes'] == 70
        and capture['analysis']['decoder_overlap_bytes'] == 208, 'Decoder lookahead accounting')
    for field in ['native_ready','callable','reader_adoption_allowed','selected_effect_verified','amount_units_verified',
                  'recipient_direction_verified','world_lease','atomic_snapshot','authorizes_retry','further_actual_authorized']:
        require(capture[field] is False, 'No authority promotion')
    selected = save('selected-cfg.json', {'schema': 'EU4-R86-RETAINED-SELECTED-CFG/1',
        'method': 'Copied fixed owned/capture rows and arithmetic replay; no decoder imported or run.',
        'capture_pin': triple(BASE + 'capture.json', CAPTURE_PIN), 'owned_pin': triple(BASE + 'owned-code.json', OWNED_PIN),
        'raw_hex': code.hex(), 'analysis': capture['analysis']})
    witness = save('root-execution-witness.json', {'schema': 'EU4-R86-ROOT-EXECUTION-WITNESS/1',
        'source': 'Direct parent /root statement in this conversation; original raw stdout/stderr were not tee-retained.',
        'exec_command_chunk_id': 'c2313d', 'exit_code': 0, 'tool_wall_seconds_decimal_text': '1.217',
        'session_id': None, 'all_shells_collected_root_statement': True,
        'reported_output_summary': {'status':'bounded_exact_entry_static_capture','entry':'cc220','rows':20,'code_bytes':70,
            'source_journal_bytes':16772282,'native_ready':False,'further_actual_authorized':False},
        'is_independent_OS_or_raw_log_proof': False, 'producer_reexecuted_here': False})
    raw_replay = save('raw-replay.json', {'schema': 'EU4-R86-RAW-ARITHMETIC-REPLAY/1',
        'rows': [{'index':i,'rva':r['rva'],'raw_hex':r['bytes'],'mnemonic':r['mnemonic'],'operands':r['operands']} for i,r in enumerate(rows)],
        'row_bytes_sum': 70, 'manual_explicit_QWORD_reads': ['0xcc22b:C+8','0xcc232:C+0','0xcc25f:C+0x10 if comparison unequal'],
        'manual_explicit_memory_stores': 0, 'implicit_PUSH_QWORD_stores': ['Q-8:old_RBX','Q-16:old_RBP','Q-24:old_R13','Q-32:old_R15'],
        'implicit_PUSH_total_store_bytes': 32, 'frame_after_prologue': 'RSP=Q-0x48; Q is this callee entry RSP',
        'branch': {'site':'0xcc259','raw_hex':'0f84cd000000','next':'0xcc25f','signed_disp32':205,'target':'0xcc32c','outside_owned':True},
        'fallthrough_exit':'0xcc266','selected_pdata':capture['selected'],'previous_pdata':capture['previous'],'next_pdata':capture['next'],
        'physical_pdata_records':19,'unique_pdata_records':16,'new_code_bytes':70,'decoded_unique_bytes':70,
        'local_normal_CFG_closed':False,'whole_function_closed':False})
    authority = {k:False for k in ['native_ready','callable','reader_adoption_allowed','selected_effect_verified',
        'ownership_transfer_verified','Cxx_type_verified','amount_units_verified','recipient_direction_verified','world_lease',
        'atomic_snapshot','authorizes_retry','further_actual_authorized']}
    contract = save('contract.json', {'schema':'EU4-R86-CALLEE-MACHINE-CONTRACT/1','sealed':True,'author_report':True,
        'independent_full_actual_review_pending':True,'scope_kind':'exact_entry_selected_pdata_fragment',
        'entry_rva':'0xcc220','owned_ranges':[['0xcc220','0xcc266']],
        'subject_capture_pin':triple(BASE+'capture.json',CAPTURE_PIN),'subject_owned_pin':triple(BASE+'owned-code.json',OWNED_PIN),
        'subject_source_manifest':triple(BASE+'source-manifest.json',SOURCE_PIN),'subject_producer':triple(BASE+'produce.py',PRODUCER_PIN),
        'selected_cfg_pin':selected,'raw_replay_pin':raw_replay,
        'formal_inputs':'Opaque incoming RCX=C, RDX=D, R8=E, entry RSP=Q; presence is not a recovered C++ signature.',
        'memory_conditions':['Stack PUSH destinations [Q-32,Q) writable and instruction fetch valid.',
            'M64[C+8] at cc22b and M64[C] at cc232 readable; not-equal path additionally M64[C+0x10] at cc25f readable.',
            'Loaded values refer to actual instruction-time memory after PUSH writes; no disjointness from stack or concurrent immutability is assumed.'],
        'local_dataflow':[
            'Four PUSHes save old RBX/RBP/R13/R15 then SUB RSP,0x28 gives Q-0x48.',
            'A=M64[C+8]; R15=D; B=M64[C]; RBP=(D-B) mod2^64; RAX=(A-B) mod2^64.',
            'R13=E; RBP=SAR64(RBP,3); RAX=SAR64(RAX,3); R8=0x1fffffffffffffff; RBX=C.',
            'CMP RAX,R8 then JE cc32c, outside owned bytes. At this exit RCX=C.',
            'When unequal: RCX=M64[C+0x10], then RCX=(RCX-B) mod2^64; fallthrough cc266, outside owned bytes.'],
        'exit_state_common':{'RSP':'Q-0x48','RBX':'C','R15':'D','R13':'E','RDX':'B','RBP':'SAR64((D-B) mod2^64,3)',
            'RAX':'SAR64((A-B) mod2^64,3); intermediate, not a return value','R8':'0x1fffffffffffffff',
            'R9_R10_R11_XMM':'No access in these 20 rows only; no full-callee preservation contract.',
            'flags':'JE exit uses CMP; fallthrough exits after SUB RCX,RDX. Incoming flags not preserved.'},
        'memory_operations':{'explicit_QWORD_load_sites':3,'load_sites_executed_before_JE':2,'not_equal_extra_load':1,
            'explicit_memory_store_sites':0,'implicit_stack_store_sites':4,'implicit_stack_store_bytes':32,
            'payload_E_dereferenced_in_owned_slice':False,'CALL_sites':0,'RET_sites':0},
        'closure':{'declared_pdata_extent_fully_owned':True,'owned_bytes':70,'decoded_rows':20,'decoded_bytes':70,
            'no_partial_instruction':True,'external_exit_sites':2,'external_JE':'0xcc32c','external_fallthrough':'0xcc266',
            'local_normal_CFG_closed':False,'whole_function_closed':False,'return_value':'unknown','cleanup':'unknown',
            'ownership_transfer':'unknown','allocation_or_free_outside_slice':'unknown'},
        'first_append_conditional_projection':{'assumptions':'Hypothetical instruction-time C qwords 0/+8/+0x10 all0 and incoming D=0, with required memory validity.',
            'deduction':'RBP=0/RAX=0; comparison with 0x1fffffffffffffff is unequal; final RCX=0 and control reaches cc266.',
            'limit':'No append/store/allocator/return/ownership conclusion follows; this is local arithmetic, not a runtime or R6 lifetime closure.'},
        'provenance_limits':['Ordinary locked Capstone 5.0.7 capture; no REA deep-engine EvidenceID.',
            'The source peer and raw-entry reviews are upstream evidence, not a completed independent review of this actual semantic report.',
            'Producer capture/claim and source-defined close/postguard/publish ordering support its self-report; OS exit/all-collected rely on root tool-record witness, with no retained raw stdout/stderr.'],
        'next_scope_proposal_only':{'preferred':'Fallthrough suffix [0xcc266,0xcc28c), 38B, inherits current frame/register conditions; cached descriptor1253 retained.',
            'other_unresolved':'JE targetcc32c body/extent not read; no proposed automatic search or fallback.',
            'new_actual_authorized':False,'new_source_prep_authorized':False},**authority})
    report = '''# R86 selected cc220 machine fragment\n\nThe exact selected pdata interval is [0xcc220,0xcc266), 70 owned/decoded bytes in twenty contiguous rows. It is not a closed helper: JE at cc259 goes to cc32c, and the unequal path falls through cc266. No CALL or RET is present.\n\nThe fragment saves four registers by PUSH (32 bytes of implicit stack writes), reserves another 0x28 bytes, and reads two QWORDs through incoming RCX. It subtracts the loaded base from incoming RDX and from the other loaded value, arithmetic-shifts both differences by three, saves incoming R8 in R13, and compares the latter result with 0x1fffffffffffffff. The unequal path reads RCX+0x10, subtracts the same base, and leaves the owned interval. These are opaque machine values; they do not recover a C++ class, allocator contract, return value, ownership transfer or successful append.\n\nThe capture records 19 pdata reads/228 bytes (16 unique/192 bytes), one 70-byte code read, and two full EXE SHA streams totaling 76,925,008 bytes: PE total 76,925,306. Decoder lookahead input278/union70/overlap208 is a separate layer. Its completed explicit source journal is148 events/16,772,282 bytes; engine file hashes are producer witness only for this retained stage, and no engine body was reopened here.\n\nRoot's execution tool record c2313d reports exit0/1.217s with no live session. Original stdout/stderr were not separately retained, so root-execution-witness.json is explicitly a conversation/tool-record summary, not manufactured raw logs or independent OS observation. Normal target-context exit and publication after postguards are producer fields supported by the frozen producer source ordering.\n\nNo producer, decoder, PE, game process or native operation ran in this seal. Sources and all new authority flags stay unchanged/false. Independent full actual review is pending. A separate future38-byte suffix scope could follow cc266, but none is authorized by this report.\n'''
    with (OUT/'report.md').open('xb') as f:f.write(report.encode())
    # Exact flat post-read. No nested historical manifests/engine bodies are traversed.
    for rel, expected in expected_sources.items():read(rel,expected,'after')
    own_source = sum(x['bytes'] for x in LEDGER) + 264684
    accounting = save('read-accounting.json', {'schema':'EU4-R86-RETAINED-SEAL-ACCOUNTING/1',
        'source_reads':LEDGER,'preflight_explicit_source_bytes':264684,'source_explicit_bytes':own_source,
        'source_manual_and_finalcheck_allowance_bytes':1048576,'source_upper_bytes':own_source+1048576,
        'own_source_limit_bytes':SOURCE_LIMIT,'own_retained_limit_bytes':RETAINED_LIMIT,
        'producer_source_completed_events':148,'producer_completed_source_bytes':16772282,'producer_source_limit_bytes':33554432,
        'producer_source_scope':'Completed explicit read/stream hashes before capture publish; not allOS, loader, failures, root preflight or this sealer.',
        'producer_PE_stream_bytes':76925008,'producer_PE_metadata_physical_bytes':228,'producer_PE_code_bytes':70,'producer_PE_total':76925306,
        'producer_decoder_input_bytes':278,'producer_decoder_unique_bytes':70,'producer_decoder_overlap_bytes':208,
        'producer_peak_committed_bytes_observed_witness':capture['peak_committed_bytes_observed'],
        'producer_hard_Job_installed':capture['hard_Job_installed'],'root_preflight_reads_included_in_own_ledger':False,
        'memory':memory_guard(),'authority':authority})
    require(own_source+1048576 < SOURCE_LIMIT,'Sealer upper source budget')
    local_pins = {}
    for p in sorted(OUT.iterdir()):
        if p.is_file():local_pins[p.relative_to(ROOT).as_posix()]=pin(p.read_bytes())
    script=Path(__file__).resolve();local_pins[script.relative_to(ROOT).as_posix()]=pin(script.read_bytes())
    retained_upper=sum(p['bytes'] for p in local_pins.values())+131072
    require(retained_upper<RETAINED_LIMIT,'Retained publication cap')
    manifest=save('actual-manifest.json',{'schema':'EU4-R86-ACTUAL-DELIVERY-MANIFEST/1','sealed':True,'author_report':True,
        'independent_full_actual_review_pending':True,'source_pins':expected_sources,'source_pin_count':len(expected_sources),
        'producer_actual_source_pin_count':22,'producer_decoder_expected_witness_pins':source['decoder_expected_witness_pins'],
        'decoder_witness_only_here_count':38,'local_pins':local_pins,'subject_capture_pin':triple(BASE+'capture.json',CAPTURE_PIN),
        'subject_owned_pin':triple(BASE+'owned-code.json',OWNED_PIN),'subject_contract_pin':contract,'selected_cfg_pin':selected,
        'read_accounting_pin':accounting,'root_execution_witness_pin':witness,'retained_upper_bytes':retained_upper,
        'roles':{'source_design_author':'/root/war_api','actual_executor':'/root','retained_semantics_author':'/root/war_api',
            'upstream_source_peer':'/root/validation_audit','independent_full_actual_review':'pending'},
        'all_shells_collected_here':True,'root_actual_shell_collected_witness':True,**authority})
    delivery=save('delivery.json',{'schema':'EU4-R86-ACTUAL-DELIVERY/1','sealed':True,'actual_manifest':manifest,
        'capture':triple(BASE+'capture.json',CAPTURE_PIN),'owned':triple(BASE+'owned-code.json',OWNED_PIN),
        'contract':contract,'selected_cfg':selected,'raw_replay':raw_replay,'accounting':accounting,
        'root_execution_witness':witness,'first_filecheck_pending':True,'all_shells_collected_here':True,**authority})
    print(json.dumps({'manifest':manifest,'contract':contract,'selected':selected,'delivery':delivery,
        'source_upper_bytes':own_source+1048576,'retained_upper_bytes':retained_upper,'all_shells_collected':True}))

if __name__=='__main__':main()
