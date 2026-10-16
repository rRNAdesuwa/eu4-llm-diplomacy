"""Build R86 frozen acquisition SOURCE ONLY. Never execute or import produce.py."""
import ast
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'work/reports/war-peace-api-20261016-r86-cc220-actual-source/'
OUT = ROOT / PREFIX
SELF = 'work/r86_build_source_20261016.py'
R79 = 'work/reports/war-peace-api-20261016-r79-null-selector-callee/'
AUTH = 'work/reports/war-peace-api-20261016-r85-root-source-plan-review/source-build-authorization.json'
AUTH_PIN = {'bytes': 3232, 'sha256': 'e46d8394585796331bde23ff22f95d78c0c45458b28893ff3016c7a70ceada90'}
OLD_BASE_PIN = {'bytes': 21830, 'sha256': 'a6d3c5282e46c9ede2da9c6cfaee29edb584636941411714a081331bcd584ab8'}
SOURCE_CAP = 32 * 1024 * 1024
MANUAL_UPPER = 2 * 1024 * 1024
RESERVED_BUILD_CLOSE = 2 * 1024 * 1024
events = []
used = 157787  # Explicit initial auth/base+template-intake reads, including copies.
peak = 0
HELPERS = ['require', 'save', 'digest', 'charge', 'read_source', 'stream_pin',
           'memory_guard', 'source_guard', 'raw_write_review', 'cfg']


class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('peak_working', 'working', 'peak_paged', 'paged',
        'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]


def guard():
    global peak
    c = PMC()
    c.cb = ctypes.sizeof(c)
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    f = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    f.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    f.restype = wintypes.BOOL
    if not f(k.GetCurrentProcess(), ctypes.byref(c), c.cb):
        raise RuntimeError('Own memory counter unavailable')
    peak = max(peak, int(c.private), int(c.peak_pagefile))
    if not (0 < peak <= 805306368 and peak < 1073741824):
        raise RuntimeError('Own memory guard')


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, phase, expected=None):
    global used
    guard()
    if path.startswith('work/deps/') or Path(path).suffix.lower() in ('.exe', '.dll', '.pyd'):
        raise RuntimeError('PE/engine stat/open/hash forbidden at preparation')
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4194304 or used + n + MANUAL_UPPER + RESERVED_BUILD_CLOSE > SOURCE_CAP:
        raise RuntimeError('source build budget')
    raw = fp.read_bytes()
    used += len(raw)
    p = pin(raw)
    events.append({'path': path, 'phase': phase, **p})
    if len(raw) != n or (expected is not None and expected != p):
        raise RuntimeError('Exact preparation text pin differs: ' + path)
    return raw


def write_raw(name, raw):
    if len(raw) > 4194304:
        raise RuntimeError('ordinary generated file cap')
    with (OUT / name).open('xb') as f:
        f.write(raw)
    return {'path': PREFIX + name, **pin(raw)}


def write(name, value):
    return write_raw(name, (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode())


def functions(text):
    return {n.name: n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Exact source replacement count differs')
    return text.replace(old, new, 1)


def main():
    if sys.argv[1:]:
        raise RuntimeError('No input/path/entry override')
    write('source-build-claim.json', {'schema': 'EU4-R86-SOURCE-BUILD-CLAIM/1', 'source_build_only': True,
        'grant': {'path': AUTH, **AUTH_PIN}, 'actual_authorized': False, 'PE_or_engine_access': False})
    own_raw = read(SELF, 'builder_source_before')
    intake_raw = read(PREFIX + 'template-intake.json', 'owned_intake')
    intake = json.loads(intake_raw)
    if intake['charged_read_bytes_including_initial_intake'] != 157787:
        raise RuntimeError('prior intake bill differs')
    auth_raw = read(PREFIX + 'owned-source-build-authorization.json', 'owned_authorization', AUTH_PIN)
    auth = json.loads(auth_raw)
    if not (auth['sealed'] and auth['source_build_only'] and auth['actual_acquisition_authorized'] is False
            and auth['output_namespace'] + '/' == PREFIX and auth['entry_rva'] == '0xcc220'):
        raise RuntimeError('exact source-only grant scope')
    old_base_raw = read(PREFIX + 'owned-r79-source-manifest.json', 'owned_template_base', OLD_BASE_PIN)
    old_base = json.loads(old_base_raw)
    old_pins = intake['selected_original_source_pins']
    originals = {AUTH: AUTH_PIN, R79 + 'source-manifest.json': OLD_BASE_PIN, **old_pins}
    owned = {p: read(copy, 'owned_selected_template', old_pins[p])
             for p, copy in intake['owned_source_mapping'].items()}
    review_ref = auth['root_independent_plan_review']
    review = json.loads(owned[review_ref['path']])
    if not (review['sealed'] and review['passed'] and review['blocking_findings'] == []
            and review['subject_plan'] == auth['source_plan']):
        raise RuntimeError('Accepted root source-plan review subjects')
    old_text = owned[R79 + 'produce.py'].decode('utf-8')
    old_funcs = functions(old_text)
    seed_ref = auth['entry_basis']
    caller = json.loads(owned[seed_ref['source']])
    window = caller['windows'][1]
    record = window['selected_rows'][14]
    if not (record['array_index'] == 255 and record['json_pointer'] == seed_ref['original_source_pointer']
            and record['row']['rva'] == seed_ref['site'] and record['row']['bytes'] == seed_ref['raw']):
        raise RuntimeError('Exact retained caller row')
    call = bytes.fromhex(record['row']['bytes'])
    disp = int.from_bytes(call[1:], 'little', signed=True)
    if not (call[0] == 0xe8 and len(call) == 5 and 0x97f199 + 5 + disp == 0xcc220 and disp == -9121662):
        raise RuntimeError('Exact retained direct CALL arithmetic')
    constants = '\n'.join([
        'UPSTREAM_PLAN=' + repr(auth['source_plan']['path']),
        'UPSTREAM_PLAN_REF=' + repr(auth['source_plan']),
        'UPSTREAM_MANIFEST=' + repr(review['subject_manifest']['path']),
        'UPSTREAM_MANIFEST_REF=' + repr(review['subject_manifest']),
        'UPSTREAM_REVIEW_REF=' + repr(review_ref),
        'UPSTREAM_SECOND_CACHE_REF=' + repr(auth['second_fixed_cache_probe']),
        'SOURCE_BUILD_AUTH_REF=' + repr({'path': AUTH, **AUTH_PIN}),
        'CALLER_EVIDENCE=' + repr(seed_ref['source']),
        'CALLER_EVIDENCE_PIN=' + repr(seed_ref['source_pin']),
        'CALLER_ORIGINAL_SOURCE=' + repr(window['source']),
        'CALLER_ORIGINAL_PIN=' + repr(window['source_pin']),
        'CALLER_ORIGINAL_POINTER=' + repr(record['json_pointer']),
    ]) + '\n'
    start = old_text.index('UPSTREAM_MANIFEST=')
    end = old_text.index('TARGET_CONTEXT_NORMAL_EXIT=False')
    producer = old_text[:start] + constants + old_text[end:]
    producer = replace_one(producer, 'ENTRY=0x97bd30', 'ENTRY=0xcc220')
    producer = replace_one(producer, 'CALL_SITE=0x99358a', 'CALL_SITE=0x97f199')
    producer = replace_one(producer, "RAW_CALL='e8a187feff'", "RAW_CALL='e882d074ff'")
    producer = producer.replace('R79', 'R86').replace('one-fixed-callee-97bd30-static', 'one-fixed-callee-cc220-static')
    producer = replace_one(producer, 'fixed opaque97bd30 callee', 'fixed opaquecc220 callee')
    producer = replace_one(producer, "and auth.get('entry_seed_pin')==seed_pin,'Source-only: exact new root once grant required')",
        "and auth.get('entry_seed_pin')==seed_pin\n      and auth.get('source_build_authorization')==SOURCE_BUILD_AUTH_REF,'Source-only: exact new root once grant required')")
    gate_start = producer.index('    review_pins={}\n')
    gate_end = producer.index("    memory_guard();PHASE='source_engine_before'", gate_start)
    new_gate = '''    review_pins={}
    build_path=ROOT/SOURCE_BUILD_AUTH_REF['path']
    build_raw=read_source(build_path)
    require({'bytes':len(build_raw),'sha256':digest(build_raw)}=={k:SOURCE_BUILD_AUTH_REF[k] for k in ('bytes','sha256')},'Exact source-build grant buffer')
    build=json.loads(build_raw)
    require(build.get('schema')=='EU4-R86-CC220-NATIVE-SOURCE-BUILD-ONLY/1' and build.get('sealed') is True
      and build.get('source_build_only') is True and build.get('actual_acquisition_authorized') is False
      and build.get('entry_rva')==hex(ENTRY) and build.get('output_namespace')==str(HERE.relative_to(ROOT)).replace('\\\\','/'),
      'Frozen source-build grant is a prerequisite, never an actual grant')
    review_pins[str(build_path.resolve())]={k:SOURCE_BUILD_AUTH_REF[k] for k in ('bytes','sha256')}
    for label in ('root_raw_entry_review','upstream_plan_review','source_peer_review'):
        group=auth.get(label,{})
        parts=('findings',) if label=='upstream_plan_review' else ('findings','manifest')
        require(set(group)==set(parts),'Exact review artifact shape required: '+label)
        findings=None
        for part in parts:
            declared=group[part]
            require(set(declared)=={'path','bytes','sha256'},'Exact review triple')
            if label=='upstream_plan_review':require(declared==UPSTREAM_REVIEW_REF,'Pinned root R85 plan review')
            path=(ROOT/declared['path']).resolve()
            require(path.is_relative_to(ROOT),'Project-local review only')
            expected={k:declared[k] for k in ('bytes','sha256')}
            raw_review=read_source(path)
            require({'bytes':len(raw_review),'sha256':digest(raw_review)}==expected,'Review raw pin differs: '+label)
            review_pins[str(path)]=expected
            if part=='findings':findings=json.loads(raw_review)
        require(findings.get('sealed') is True and findings.get('passed') is True
          and findings.get('blocking_findings')==[],'Passed independent review required: '+label)
        if label=='upstream_plan_review':
            require(findings.get('subject_plan')==UPSTREAM_PLAN_REF and findings.get('subject_manifest')==UPSTREAM_MANIFEST_REF
              and findings.get('subject_second_cache_probe')==UPSTREAM_SECOND_CACHE_REF,'Exact accepted R85 plan/cache subjects required')
        else:
            require(findings.get('subject_source_manifest')==base_pin and findings.get('subject_producer')==producer_pin
              and findings.get('subject_entry_seed')==seed_pin,'New R86 review subjects differ: '+label)
            if label=='root_raw_entry_review':
                require(findings.get('scope')=='raw_direct_call_entry_seed_only'
                  and findings.get('entry_rva')==hex(ENTRY) and findings.get('call_site_rva')==hex(CALL_SITE)
                  and findings.get('raw_call_hex')==RAW_CALL,'Exact retained raw caller entry review required')
'''
    producer = producer[:gate_start] + new_gate + producer[gate_end:]
    caller_start = producer.index('    upstream=json.loads(read_source(ROOT/UPSTREAM_OWNED))')
    caller_end = producer.index('    cached=json.loads(read_source(ROOT/ANCHORS))', caller_start)
    new_caller = '''    caller_raw=read_source(ROOT/CALLER_EVIDENCE)
    require({'bytes':len(caller_raw),'sha256':digest(caller_raw)}==CALLER_EVIDENCE_PIN,'Exact retained caller raw buffer before parse')
    upstream=json.loads(caller_raw)
    window=upstream['windows'][1];record=window['selected_rows'][14];row=record['row']
    require(window['call_site']=='0x97f1a1' and window['source']==CALLER_ORIGINAL_SOURCE
      and window['source_pin']==CALLER_ORIGINAL_PIN and record['array_index']==255
      and record['json_pointer']==CALLER_ORIGINAL_POINTER and row['rva']==hex(CALL_SITE),'Fixed R84 cached caller pointer')
    call=bytes.fromhex(row['bytes'])
    require(call.hex()==RAW_CALL and len(call)==5 and call[0]==0xe8
      and CALL_SITE+5+struct.unpack('<i',call[1:])[0]==ENTRY,'Exact retained E8 signed-rel32 seed')
    require(pins[CALLER_EVIDENCE]==CALLER_EVIDENCE_PIN
      and pins[UPSTREAM_PLAN]=={k:UPSTREAM_PLAN_REF[k] for k in ('bytes','sha256')}
      and pins[UPSTREAM_MANIFEST]=={k:UPSTREAM_MANIFEST_REF[k] for k in ('bytes','sha256')},'Upstream source subjects fixed')
'''
    producer = producer[:caller_start] + new_caller + producer[caller_end:]
    if 'UPSTREAM_OWNED' in producer or '0x993570' in producer or "ENTRY=0x97bd30" in producer:
        raise RuntimeError('Old target caller leaked into new producer')
    compile(producer, PREFIX + 'produce.py', 'exec')  # Syntax only, no import/execute.
    new_funcs = functions(producer)
    helper_pins = {}
    for name in HELPERS:
        old_node, new_node = old_funcs[name], new_funcs[name]
        old_segment = ast.get_source_segment(old_text, old_node).encode()
        new_segment = ast.get_source_segment(producer, new_node).encode()
        if ast.dump(old_node, include_attributes=False) != ast.dump(new_node, include_attributes=False) or old_segment != new_segment:
            raise RuntimeError('Accepted helper changed: ' + name)
        helper_pins[name] = {'bytes': len(old_segment), 'sha256': hashlib.sha256(old_segment).hexdigest(),
                             'AST_same': True, 'text_same': True}
    old_nested = {n.name: n for n in ast.walk(old_funcs['main']) if isinstance(n, ast.FunctionDef) and n.name != 'main'}
    new_nested = {n.name: n for n in ast.walk(new_funcs['main']) if isinstance(n, ast.FunctionDef) and n.name != 'main'}
    nested_same = {}
    for name in ['mapping', 'authenticate', 'target_read', 'record']:
        if ast.dump(old_nested[name], include_attributes=False) != ast.dump(new_nested[name], include_attributes=False):
            raise RuntimeError('Acquisition nested helper changed: ' + name)
        nested_same[name] = True
    producer_pin = write_raw('produce.py', producer.encode())
    main_text = ast.get_source_segment(producer, new_funcs['main']) + '\n'
    main_pin = write_raw('main-template.py.inc', main_text.encode())
    seed = {'schema': 'EU4-R86-DIRECT-CALL-ENTRY-SEED/1', 'sealed': True, 'entry_rva': '0xcc220',
       'call_site_rva': '0x97f199', 'raw_call_hex': 'e882d074ff', 'signed_rel32': -9121662,
       'return_rva': '0x97f19e', 'retained_source': seed_ref['source'], 'retained_source_pin': seed_ref['source_pin'],
       'retained_json_pointer': '/windows/1/selected_rows/14', 'original_source': window['source'],
       'original_source_pin_metadata_only': window['source_pin'], 'original_json_pointer': record['json_pointer'],
       'retained_selected_caller_rows': [x for x in window['selected_rows'] if 246 <= x['array_index'] <= 256],
       'caller_path_condition': 'Selected97f17c JE is taken after CMP RDX,M64[currentR14+98]; this is the local branch that reaches97f199.',
       'register_evidence': {
         'RCX': '97f192 LEA RCX,[currentR14+88]; no intervening instruction beforeCALL exceptCALL itself.',
         'RDX': '97f16e MOV RDX,M64[currentR14+90]; CMP/JE and LEAs do not overwrite RDX on the selected taken route.',
         'R8': '97f18b LEA R8,[currentRBP+170]. That current stack slot has the selected97f167 QWORDstore from currentRAX; width consumed by cc220 is unknown.',
         'R9_XMM': 'No local selected assignments supply a known value. The earlier unselected caller/callees are opaque; no zero constant or formal consumption is assumed.',
         'RAX': 'Opaque current value used by97f167 store. It is not assigned a numeric formal meaning.',
         'R14_RBP': 'Current scalar values; not unconditionally joined to function-entry values across unselected caller rows31..240 or unexamined callees.',
         'flags': 'On this taken equality route ZF1; CMP64 equality also CF0/SF0/OF0/PF1/AF0, with MOV/LEA preserving those flags. DF is unknown; no callee flag contract.'},
       'stack_evidence': {'F': 'RSP immediately before the97f199 CALL', 'callee_entry_RSP': 'F-8 from the machine CALL pushing returnQWORD97f19e',
          'not_a_runtime_stack_sample': True, 'no_fixed_late_frame_from_unselected_caller_assumed': True,
          'borrow_lifetime_alias_and_valid_memory_unknown': True},
       'accepted_upstream_plan_review': review_ref, 'source_build_authorization': {'path': AUTH, **AUTH_PIN},
       'scope': 'Opaque fixed CALL-target static research; caller register presence is not a callee formal/type/ownership contract.',
       'new_callee_bytes_read': 0, 'actual_authorized': False, 'native_ready': False, 'callable': False,
       'selected_effect_verified': False, 'world_lease': False, 'atomic_snapshot': False, 'authorizes_retry': False}
    seed_pin = write('entry-seed.json', seed)
    budget = {'schema': 'EU4-R86-BUDGET/1', 'sealed': True, 'source_build_bytes': 33554432,
       'retained_bytes': 16777216, 'ordinary_file_bytes': 4194304, 'future_source_engine_bytes': 33554432,
       'future_retained_bytes': 16777216, 'software_memory_bytes': 805306368, 'one_GiB_stop': 1073741824,
       'hard_Job_installed': False, 'metadata_records_max': 32, 'metadata_physical_bytes_max': 384,
       'exact_begin_required': '0xcc220', 'full_if_extent_le': 8192, 'otherwise_first_prefix_bytes': 2048,
       'code_unique_bytes_max': 8192, 'exact_begin_miss': 'unknown0code_no_fallback',
       'callee_RIPdata_vslot_unwind_header_neighbor_code_bytes': 0,
       'two_full_EXE_SHA_stream_bytes_separate': 76925008, 'hash_chunk_bytes_max': 1048576,
       'PE_with_max_metadata_and_code_separate_upper': 76933584,
       'source_preparation_engine_body_stat_open': False, 'actual_authorized': False, 'tests_authorized': False,
       'native_ready': False, 'OS_loader_IO_complete': False, 'failed_partial_IO_not_universally_in_completed_journal': True}
    budget_pin = write('budget.json', budget)
    protocol = '''# R86 cc220 单入口静态采集源码协议

当前只有 source-build grant，禁止运行 produce.py。本次准备不 stat/open/hash EXE，不加载/读取 decoder，不运行旧脚本/tests，不接游戏/native/Frida。

未来唯一入口固定 cc220，来自 R84 冻结97f199 E8e882d074ff的signedrel32。只核≤32条12B pdata；要求selected.begin精确等于cc220且相邻记录不交叠。extent≤8192则单次读完整，否则仅首2048；无exactbegin或映射失败则unknown0code，不能containing/滑窗fallback。不跟外callee、RIPdata、vslot、unwind、header或邻code。

10个顶层helpers和4个main内采集helpers逐字/AST复用accepted R79。source_guard(expected_manifest_pin)对单个rawmanifest先bytes/SHA再parse和选择engine；pre/post均传base_pin，首次guard前后有exact外check。38个Capstone5.0.7 pin只作为prep metadata；未来actual才stream核。使用ordinary Capstone，不是REA deep-engine Evidence ID；已知Ghidra/IDA未配置，本轮不重复诊断/安装。

未来run-authorization.json须新schema EU4-R86-ROOT-AUTHORIZATION/1、sealed/root_explicit_start_received/single_attempt均true，operation='one-fixed-callee-cc220-static'；entry_rva/call_site_rva/raw_call_hex固定cc220/97f199/e882d074ff；source_manifest/producer_pin/entry_seed_pin都是当前精确{bytes,sha256}，source_build_authorization为原3232B/e46d...完整{path,bytes,sha256}。

三review门禁：root_raw_entry_review与source_peer_review均为{findings,manifest}完整triple；findings sealed/passed/[]及subject_source_manifest/subject_producer/subject_entry_seed均为三当前pin-only对象。raw门另要求scope='raw_direct_call_entry_seed_only'及固定entry_rva/call_site_rva/raw_call_hex。upstream_plan_review诚实为单{findings}triple，精确固定已有R85 root11396B/35917...；subject_plan/subject_manifest/subject_second_cache_probe均核既有完整triples。原R85 root目录没有manifest，不伪造配对。

以上三review及新root oncegrant必须在engine/PE之前通过。source-build grant本身actual=false，不能代用。当前不创建run-authorization/claim/capture/owned-code/failure，不执行producer。语法检查仅compile AST，不import/exec。

未来实际使用独占claim/no retry，EXE前后两次整文件SHA流单列76925008B；target with正常退出及source/engine/auth/reviews后核全部通过后才发布capture。failure保留，无自动修复重采。journal不宣称完整OS/loader/失败partial I/O，软件memoryguard不伪称Job硬限制。

RCX=currentR14+88/RDX=selectedM64[R14+90]/R8=currentRBP+170只是caller机器来源，不是C++vector/formals、对象范围或拥有权证明。R6首次append、R84 R14跨callee保持、allocator/异常/reentry/lease/业务效果仍未知，所有ready/callable/effect/reader/retry权限false。
'''
    protocol_pin = write_raw('PROTOCOL.md', protocol.encode('utf-8'))
    delta_pin = write('source-delta.json', {'schema': 'EU4-R86-SOURCE-DELTA/1',
       'template_source': {'path': R79 + 'produce.py', **old_pins[R79 + 'produce.py']},
       'template_manifest': {'path': R79 + 'source-manifest.json', **OLD_BASE_PIN},
       'helper_pins': helper_pins, 'unchanged_top_level_helpers': HELPERS,
       'unchanged_main_nested_helpers': nested_same,
       'main_changes': ['R86 namespace/schema/entry/call identity', 'Existing R85 plan review has a single findings artifact; new raw/source-peer remain pairs',
          'New source-build prerequisite is never an actual grant', 'R84 exact caller raw-buffer hash-before-parse and fixed row pointer replace R69 owned-prefix seed'],
       'acquisition_bounds_changed': False, 'raw_manifest_guard_changed': False,
       'decoder_witness_pins_unchanged': True, 'decoder_body_stat_open_during_build': False,
       'producer_imported_or_executed': False, 'old_programs_executed': False})
    checker_path = PREFIX + 'check_prepared.py'
    checker_raw = read(checker_path, 'new_checker_source_before')
    compile(checker_raw, checker_path, 'exec')
    new_local_pins = {x['path']: {k: x[k] for k in ['bytes', 'sha256']} for x in [producer_pin, main_pin, seed_pin, budget_pin, protocol_pin, delta_pin]}
    new_local_pins[checker_path] = pin(checker_raw)
    new_local_pins[SELF] = pin(own_raw)
    actual_pins = {**originals, **new_local_pins}
    engine = old_base['decoder_expected_witness_pins']
    if len(engine) != 38 or engine != intake['decoder_metadata_witness_only']:
        raise RuntimeError('Locked decoder metadata changed')
    future_sum = sum(p['bytes'] for p in actual_pins.values()) + sum(p['bytes'] for p in engine.values())
    estimate = 2 * future_sum + 2 * 1024 * 1024 + 512 * 1024
    if estimate >= 33554432:
        raise RuntimeError('Conditional future explicit-source estimate exceeds fixed cap')
    base = {'schema': 'EU4-R86-SOURCE-MANIFEST/1', 'sealed': True, 'stage': 'source-budget-prepared-not-actual',
       'entry_rva': '0xcc220', 'call_site_rva': '0x97f199', 'raw_call_hex': 'e882d074ff',
       'game_sha256': auth['target_game']['sha256'], 'game_bytes': auth['target_game']['bytes'],
       'source_pins': {**actual_pins, **engine}, 'actual_source_pins': actual_pins, 'actual_source_pin_count': len(actual_pins),
       'decoder_expected_witness_pins': engine, 'decoder_witness_pin_count': 38,
       'engine_files_accessed_at_preparation': False,
       'four_gates': ['new raw caller entry review', 'exact accepted R85 root full source-plan review', 'new full source peer', 'new root exact once grant'],
       'conditional_estimated_future_source_bytes': estimate, 'conditional_review_allowance_bytes': 2097152,
       'estimate_not_universal_or_OS_IO_bound': True,
       **{x: False for x in ['actual_authorized', 'tests_authorized', 'native_ready', 'callable', 'reader_adoption_allowed',
          'selected_effect_verified', 'amount_units_verified', 'recipient_direction_verified', 'world_lease', 'atomic_snapshot', 'authorizes_retry']}}
    base_pin = write('source-manifest.json', base)
    identity_pin = write('prepared-identity.json', {'schema': 'EU4-R86-PREPARED-IDENTITY/1', 'sealed': True,
       'source_manifest': {k: base_pin[k] for k in ['bytes', 'sha256']},
       'producer_pin': {k: producer_pin[k] for k in ['bytes', 'sha256']},
       'entry_seed_pin': {k: seed_pin[k] for k in ['bytes', 'sha256']},
       'actual_source_pin_count': len(actual_pins), 'source_build_authorization': {'path': AUTH, **AUTH_PIN},
       'actual_authorized': False, 'not_an_actual_grant_or_independent_review': True})
    # First pass for the fourteen original sources was done during fixed intake.
    # Only this AFTER pass reopens them; no engine body is ever stat/opened here.
    for p, expected in originals.items():
        read(p, 'selected_original_source_after', expected)
    read(SELF, 'builder_source_after', pin(own_raw))
    read(checker_path, 'new_checker_source_after', pin(checker_raw))
    guard()
    preparation_pin = write('preparation.json', {'schema': 'EU4-R86-SOURCE-PREPARATION/1', 'sealed': True,
       'source_build_authorization': {'path': AUTH, **AUTH_PIN}, 'source_manifest': base_pin,
       'producer': producer_pin, 'entry_seed': seed_pin, 'prepared_identity': identity_pin,
       'original_selected_source_count': len(originals), 'original_pins_before_after_equal': True,
       'original_selected_source_pins': originals, 'source_intake_metadata': PREFIX + 'template-intake.json',
       'read_events': events, 'prior_intake_explicit_reads': 157787,
       'explicit_build_read_bytes_including_prior_intake': used,
       'manual_charged_upper': MANUAL_UPPER, 'remaining_build_close_reserve': RESERVED_BUILD_CLOSE,
       'whole_build_upper': used + MANUAL_UPPER + RESERVED_BUILD_CLOSE, 'build_limit': SOURCE_CAP,
       'future_source_conditional_estimate': estimate,
       'peak_committed_bytes': peak, 'engine_bodies_stat_open': False, 'PE_stat_open_hash': False,
       'syntax_only_compilation': True, 'producer_imported_or_executed': False,
       'actual_authorized': False, 'tests_run': 0, 'game_access': False,
       'all_shells_collected_on_return': True})
    print(json.dumps({'ok': True, 'source_manifest': base_pin, 'producer': producer_pin, 'seed': seed_pin,
       'budget': budget_pin, 'preparation': preparation_pin, 'actual_sources': len(actual_pins),
       'engine_metadata': 38, 'explicit_build_reads': used, 'build_upper': used + MANUAL_UPPER + RESERVED_BUILD_CLOSE,
       'future_source_estimate': estimate, 'peak': peak, 'actual_authorized': False}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        write('source-build-failure.json', {'error': str(exc), 'traceback': traceback.format_exc(),
             'read_events': events, 'prior_intake_explicit_reads': 157787, 'explicit_read_bytes': used,
             'manual_upper': MANUAL_UPPER, 'actual_authorized': False, 'PE_or_engine_access': False})
        print(json.dumps({'ok': False, 'error': str(exc), 'read_bytes': used}))
        sys.exit(1)
