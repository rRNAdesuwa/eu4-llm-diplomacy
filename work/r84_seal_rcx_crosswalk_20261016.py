"""R84 retain-only analysis and seal. Never opens the four upstream originals."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/war-peace-api-20261016-r84-selector-call-rcx-crosswalk'
PREFIX = str(OUT.relative_to(ROOT)).replace('\\', '/') + '/'
ORIGINAL_BYTES = 2795606
MANUAL_UPPER = 524288
VERIFY_RESERVE = 500000
LOCAL_CAP = 2 * 1024 * 1024
TOTAL_CAP = 8 * 1024 * 1024
FILES = ['owned-manifest.json', 'owned-crosswalk.json', 'owned-selected-context.json',
    'intake-claim.json', 'intake-failure.json', 'intake.stdout.txt', 'intake.stderr.txt',
    'metadata-continuation.json', 'small-context-claim.json', 'small-context.json',
    'small-context.stdout.txt', 'small-context.stderr.txt', 'native-window-claim.json',
    'rcx-window-evidence.json', 'native-window.stdout.txt', 'native-window.stderr.txt',
    'native-window-command.json']
SCRIPTS = ['work/r84_cached_intake_20261016.py', 'work/r84_cached_context_20261016.py',
           'work/r84_extract_rcx_windows_20261016.py', 'work/r84_seal_rcx_crosswalk_20261016.py']
events = []
used = 0
peak = 0


class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]


def guard():
    global peak
    p = PMC()
    p.cb = ctypes.sizeof(p)
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    fn = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    fn.restype = wintypes.BOOL
    if not fn(k.GetCurrentProcess(), ctypes.byref(p), p.cb):
        raise RuntimeError('self memory counter')
    peak = max(peak, p.PeakWorkingSetSize)
    if p.WorkingSetSize > 768 * 1024 * 1024 or p.PeakWorkingSetSize > 1024 * 1024 * 1024:
        raise RuntimeError('self memory guard')


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, phase, expected=None):
    global used
    guard()
    if not (path.startswith(PREFIX) or path in SCRIPTS):
        raise RuntimeError('non-owned original source forbidden during retain seal')
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4 * 1024 * 1024 or used + n > LOCAL_CAP:
        raise RuntimeError('local seal read budget')
    raw = fp.read_bytes()
    used += len(raw)
    p = pin(raw)
    events.append({'path': path, 'phase': phase, **p})
    if len(raw) != n or (expected is not None and p != expected):
        raise RuntimeError('local source differs')
    return raw


def write(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / name).open('xb') as f:
        f.write(raw)
    return {'path': PREFIX + name, **pin(raw)}


def main():
    write('analysis-seal-claim.json', {'schema': 'EU4-R84-RETAIN-SEAL-CLAIM/1',
        'original_source_reads': 0, 'game_access': False, 'native_calls': 0})
    paths = SCRIPTS + [PREFIX + name for name in FILES]
    raw = {p: read(p, 'local_before') for p in paths}
    doc = {name: json.loads(raw[PREFIX + name].decode('utf-8-sig')) for name in FILES if name.endswith('.json')}
    manifest = doc['owned-manifest.json']
    crosswalk = doc['owned-crosswalk.json']
    small = doc['small-context.json']
    evidence = doc['rcx-window-evidence.json']
    original = evidence['source']
    original_pin = evidence['source_pin']
    r82base = 'work/reports/war-peace-api-20261016-r82-selector-cached-use-crosswalk/'
    assert pin(raw[PREFIX + 'owned-crosswalk.json']) == manifest['crosswalk_pin']
    assert pin(raw[PREFIX + 'owned-selected-context.json']) == manifest['local_files']['selected-context.json']
    assert original_pin == manifest['source_pins'][original]
    assert evidence['charged_read_bytes'] == 2605284
    assert small['charged_bytes'] == 147976
    failure = doc['intake-failure.json']
    assert len(failure['reads']) == 1 and failure['reads'][0]['bytes'] == 21173
    metadata = doc['metadata-continuation.json']
    assert metadata['original_manifest_total_reads'] == 2 and metadata['original_manifest_before_after_equal']
    assert pin(raw[PREFIX + 'owned-manifest.json']) == {k: failure['reads'][0][k] for k in ['bytes', 'sha256']}
    assert ORIGINAL_BYTES == 2 * 21173 + 147976 + 2605284
    assert crosswalk['search_scope']['extra_sites'] == ['0x97beaa', '0x97ed33', '0x97f1a1']
    first = crosswalk['observations'][1]
    assert first['id'] == 'first-use-return-layout'
    assert first['raw_rows'][3]['row'] == {'rva': '0x97bea7', 'bytes': '488bf9', 'instruction': 'mov rdi, rcx'}
    assert first['raw_rows'][4]['row'] == {'rva': '0x97beaa', 'bytes': 'e881feffff', 'instruction': 'call 0x97bd30'}
    windows = {w['call_site']: w for w in evidence['windows']}
    w1, w2 = windows['0x97ed33'], windows['0x97f1a1']
    assert (w1['start_index'], w1['end_index_exclusive'], w1['rows_before'], w1['rows_after'], w1['selected_raw_bytes']) == (0, 31, 14, 16, 129)
    assert (w2['start_index'], w2['end_index_exclusive'], w2['rows_before'], w2['rows_after'], w2['selected_raw_bytes']) == (241, 274, 16, 16, 150)
    assert all(not w['linear_address_gaps'] for w in evidence['windows'])
    rows = {x['array_index']: x for w in evidence['windows'] for x in w['selected_rows']}
    checks = {10: ('0x97ed1f', '4c8bf1'), 14: ('0x97ed33', 'e8f8cfffff'),
              249: ('0x97f17c', '740d'), 252: ('0x97f189', 'eb13'),
              254: ('0x97f192', '498d8e88000000'), 255: ('0x97f199', 'e882d074ff'),
              256: ('0x97f19e', '498bce'), 257: ('0x97f1a1', 'e88acbffff')}
    for i, (address, code) in checks.items():
        assert rows[i]['row']['rva'] == address and rows[i]['row']['bytes'] == code
    # No new decoder: validate only the explicit retained branch/call encodings.
    branch_math = []
    for i, target in [(249, 0x97f18b), (252, 0x97f19e)]:
        row = rows[i]['row']
        b = bytes.fromhex(row['bytes'])
        addr = int(row['rva'], 16)
        got = addr + len(b) + int.from_bytes(b[1:], 'little', signed=True)
        assert got == target
        branch_math.append({'source_pointer': rows[i]['json_pointer'], 'site': row['rva'],
            'raw': row['bytes'], 'next': hex(addr + len(b)), 'signed_rel8': int.from_bytes(b[1:], 'little', signed=True),
            'target': hex(target)})
    assert int(w1['next_rva'], 16) + w1['signed_rel32'] == 0x97bd30
    assert int(w2['next_rva'], 16) + w2['signed_rel32'] == 0x97bd30
    before = {p: pin(v) for p, v in raw.items()}
    for p in paths:
        read(p, 'local_after', before[p])
    guard()
    upper = ORIGINAL_BYTES + MANUAL_UPPER + used + VERIFY_RESERVE
    assert upper < TOTAL_CAP
    context_pin = {'path': r82base + 'crosswalk.json', **pin(raw[PREFIX + 'owned-crosswalk.json'])}
    authority = {x: False for x in ['callable', 'native_ready', 'sender_authorized',
        'effect_verified', 'input_type_verified', 'endpoint_direction_verified', 'runtime_identity_verified',
        'reader_adoption_authorized', 'world_lease', 'atomic_snapshot', 'retry_authorized', 'new_native_scope_authorized']}
    entries = [
      {'call_site': '0x97beaa', 'result': 'RCX is the selected 0x97bea0 entry RCX on the retained straight prologue path.',
       'evidence_mode': 'reuse_already_complete_R82_answer_no_original_window_reextraction',
       'upstream_crosswalk': context_pin, 'answer_pointer': '/observations/1',
       'support_pointers': ['/observations/1/raw_rows/0', '/observations/1/raw_rows/1', '/observations/1/raw_rows/2', '/observations/1/raw_rows/3', '/observations/1/raw_rows/4'],
       'raw_MOV': {'rva': '0x97bea7', 'bytes': '488bf9', 'effect': 'RDI := RCX; RCX unchanged'},
       'input_origin_before_function_entry': 'unknown', 'object_type_and_pointed_contents': 'unknown'},
      {'call_site': '0x97ed33', 'result': 'RCX is the selected 0x97ed00 entry RCX on rows0..14; no prior CALL, branch or RCX assignment occurs in that selected prologue.',
       'evidence_mode': 'new_bounded_fixed_cached_window', 'source': original, 'source_pin': original_pin,
       'call_pointer': '/functions/0x97ed00/instructions/14', 'window': [0, 31],
       'saved_copy': {'pointer': '/functions/0x97ed00/instructions/10', 'rva': '0x97ed1f', 'raw': '4c8bf1', 'effect': 'R14 := RCX64; does not alter RCX'},
       'raw_call': 'e8f8cfffff', 'signed_rel32': -12296, 'target': '0x97bd30',
       'input_origin_before_function_entry': 'unknown',
       'post_call_unknowns': ['Returned RCX/other volatile values are not presumed preserved.', 'NULL branch at97ed3b exits this selected window.', '97cda0,97d130,97d4e0 are not followed; their register/alias effects are unknown.'],
       'object_type_and_endpoint_writers': 'unknown'},
      {'call_site': '0x97f1a1', 'result': 'After executing97f19e, selector RCX equals the R14 bits current at97f19e; the immediate prior assignment overrides the earlier LEA argument.',
       'evidence_mode': 'new_bounded_fixed_cached_window', 'source': original, 'source_pin': original_pin,
       'call_pointer': '/functions/0x97ed00/instructions/257', 'window': [241, 274],
       'immediate_definition': {'pointer': '/functions/0x97ed00/instructions/256', 'rva': '0x97f19e', 'raw': '498bce', 'effect': 'RCX := R14'},
       'not_selector_input': {'pointer': '/functions/0x97ed00/instructions/254', 'rva': '0x97f192', 'raw': '498d8e88000000', 'effect': 'RCX := R14 + 0x88 for the following97f199 CALL; overwritten at97f19e'},
       'local_predecessors': [
         {'route': 'JE97f17c not taken', 'through': ['97f17e', '97f181', '97f189 JMP97f19e'], 'R14_scalar': 'No direct R14 register assignment or CALL on this selected route before97f19e.'},
         {'route': 'JE97f17c taken', 'through': ['97f18b', '97f192', '97f199 CALL0xcc220', '97f19e'], 'R14_scalar': 'Current post-cc220 R14; actual preservation by this unexamined callee is unknown.'}],
       'raw_call': 'e88acbffff', 'signed_rel32': -13430, 'target': '0x97bd30',
       'entry_copy_does_not_close_late_identity': {'earlier_copy': '97ed1f R14 := function-entry RCX', 'unselected_indices_in_between': [31, 240],
           'condition_not_assumed': 'Every intervening instruction and callee would need to preserve the intended R14 value; not proved in these two windows.'},
       'unknown_incoming_control_edges': 'Only selected local branches are replayed. Unselected edges directly into the CALL or into this window are not enumerated.',
       'object_type_endpoint_direction_and_pointed_contents': 'unknown'},
    ]
    finding = {'schema': 'EU4-R84-CACHED-SELECTOR-RCX-FINDINGS/1', 'sealed': True, 'passed': True,
      'stage': 'author_retained_analysis_pending_non_author_review', 'blocking_findings': [],
      'scope': 'three_extra_R82_97bd30_calls_RCX_input_provenance_only',
      'role': 'War authored R84; prior R69 source designer and later raw/full peer, R79 actual author, R80/R81 full reviewer. R82 D author results are reused as accepted witnesses; no claim of independent re-review of all R82 or original native-owned-peace evidence.',
      'upstream_source_manifest': {'path': r82base + 'manifest.json', **pin(raw[PREFIX + 'owned-manifest.json'])},
      'upstream_crosswalk': context_pin,
      'upstream_selected_context': {'path': r82base + 'selected-context.json', **pin(raw[PREFIX + 'owned-selected-context.json'])},
      'optional_original_source': {'path': original, **original_pin}, 'results': entries,
      'new_selected_window_count': 2, 'new_selected_rows': 64, 'new_selected_raw_bytes': 279,
      'per_window_before_after_max': 16, 'new_native_code_acquisition_bytes': 0,
      'scope_limits': ['Instruction text/raw bytes are inherited frozen evidence; no PE read or new decode.',
        'A contiguous retained window does not prove dynamic reachability or all incoming control edges.',
        'MOV register provenance does not authenticate a C++ class, object extent, full handles, endpoint direction, ownership or lifetime.',
        'No ordinary ABI preservation is silently supplied across the unexamined calls.',
        'RAX-return use and field offsets do not prove original action acceptance, peace completion or settlement.',
        'The source full JSON is physically read and parsed, but only the two fixed instruction windows are semantically extracted. No other function body/callee is inspected.',
        'Pre/post equal pins are a source witness, not a common atomic snapshot or ABA proof.'],
      'retained_failure': {'kind': 'reviewer_manifest_schema_assumption', 'initial_exit': 1,
        'source_read_before_failure': 21173, 'original_large_source_reads_before_failure': 0,
        'cause': 'R82 has local_files plus a standalone crosswalk_pin, not full-path keys for both local artifacts.',
        'repair': 'R1 source/log unchanged; second manifest read exact-matched the initial pin, saved an owned copy, then a new small-context extractor used real exact pins.',
        'no_author_program_rerun': True, 'no_native_or_PE_retry': True},
      'accounting': {'original_source_read_bytes_including_failed_manifest_intake': ORIGINAL_BYTES,
        'manifest_two_pass': 42346, 'small_sources_two_pass': 147976, 'optional_original_two_pass': 2605284,
        'retain_seal_instrumented_bytes': used, 'manual_log_source_view_charged_upper': MANUAL_UPPER,
        'future_local_verify_reserve': VERIFY_RESERVE, 'whole_stage_upper': upper, 'budget': TOTAL_CAP,
        'native_window_extractor_peak': evidence['peak_working_set'], 'retained_sealer_peak': peak,
        'not_whole_OS_loader_IO': True},
      'authority': authority, 'process_reads': 0, 'PE_reads': 0, 'decoder_calls': 0,
      'native_game_calls': 0, 'game_field_writes': 0, 'new_requests': 0, 'all_shells_collected': True}
    findings_pin = write('findings.json', finding)
    replay_pin = write('raw-replay.json', {'schema': 'EU4-R84-RAW-PROVENANCE-REPLAY/1',
        'fixed_window_evidence': {'path': PREFIX + 'rcx-window-evidence.json', **pin(raw[PREFIX + 'rcx-window-evidence.json'])},
        'new_call_math': [{'site': w['call_site'], 'raw': w['raw_call'], 'signed_rel32': w['signed_rel32'], 'next': w['next_rva'], 'target': w['target']} for w in evidence['windows']],
        'local_branch_math': branch_math,
        'source_shape_correction': 'local_files[basename] and crosswalk_pin; original source from source_pins[path]',
        'new_instruction_decode': False, 'callee_followed': False, 'results': entries})
    accounting_pin = write('read-accounting.json', {'schema': 'EU4-R84-READ-ACCOUNTING/1',
        'original_sources': {'events': failure['reads'] + [{'path': metadata['source'], 'phase': 'manifest_after_schema_continuation', 'bytes': metadata['bytes'], 'sha256': metadata['sha256']}] + small['read_events'] + evidence['read_events'],
                             'charged_bytes': ORIGINAL_BYTES},
        'retained_events': events, 'retained_charged_bytes': used, 'manual_upper': MANUAL_UPPER,
        'manual_scope': 'Explicit small log/source views and reviewer orchestration; bounded allowance, not exact OS loader IO.',
        'verification_reserve': VERIFY_RESERVE, 'whole_stage_upper': upper, 'budget': TOTAL_CAP})
    report = """# R84 三处 selector CALL 的 RCX 来源\n\n- **97beaa**：直接引用 R82 已闭合的入口序列。PUSH/SUB/MOV RDI,RCX 未改 RCX，因此该选定路径传入 97bea0 的入口 RCX；不重新摘原调用点。\n- **97ed33**：补摘 `97ed00` 的第 0–30 行。CALL 前无其它 CALL/分支/RCX 赋值；`97ed1f: 4c8bf1` 只把 RCX 保存到 R14，所以 selector 收到入口 RCX。入口之前的来源和对象类型仍未知。\n- **97f1a1**：`97f19e: 498bce` 在 CALL 紧前把**当前 R14**写入 RCX。前面的 `LEA RCX,[R14+88]` 是 `97f199→cc220` 的参数，已经被该 MOV 覆盖。局部分支一条绕过 cc220，另一条经过它；后一条的 R14 保持没有实证。早先 `97ed1f` 的保存与此处之间，第 31–240 行没有纳入本轮，不能把当前 R14 无条件等同入口对象。\n\n两处新窗口共 64 行、279 B，分别不超过调用前后 16 行；全部 raw/pointer/call-rel32 和两条局部分支算术在 raw-replay 与 rcx-window-evidence 中。未跟踪外部 callee，也未假定寄存器跨 CALL 保持。类型、完整端点、方向、所有权、寿命及原动作效果均未知。\n\n首次审查脚本错误假定 R82 manifest 的本地 pin 结构，仅读 21,173 B 后失败；源码及日志保留。窄修只适配实际 schema，用第二次 manifest raw hash 完成前后核对，没有重跑作者程序或 native。所有 source/log/seal 读取计入独立 8 MiB 账；全部 shell 收齐，PE/decoder/runtime/native/新请求为 0，authority 全 false。\n"""
    report_raw = report.encode('utf-8')
    with (OUT / 'report.md').open('xb') as f:
        f.write(report_raw)
    report_pin = {'path': PREFIX + 'report.md', **pin(report_raw)}
    final = {'schema': 'EU4-R84-RCX-CROSSWALK-MANIFEST/1', 'sealed': True,
        'stage': 'author_retained_analysis_pending_non_author_review', 'inputs': before,
        'outputs': [findings_pin, replay_pin, accounting_pin, report_pin],
        'source_prepost_evidence': accounting_pin,
        'original_source_reads_during_seal': 0, 'whole_stage_upper': upper, 'all_authority': False}
    manifest_pin = write('manifest.json', final)
    print(json.dumps({'ok': True, 'findings': findings_pin, 'manifest': manifest_pin,
        'replay': replay_pin, 'read_accounting': accounting_pin, 'report': report_pin,
        'retained_reads': used, 'whole_stage_upper': upper, 'peak': peak}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        write('analysis-seal-failure.json', {'error': str(exc), 'traceback': traceback.format_exc(),
               'events': events, 'used': used, 'no_automatic_retry': True})
        print(json.dumps({'ok': False, 'error': str(exc), 'used': used}))
        sys.exit(1)
