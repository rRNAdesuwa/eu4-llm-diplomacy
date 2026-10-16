"""R85 retain-only proposal seal. No upstream body or target access."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'work/reports/war-peace-api-20261016-r85-cc220-cache-source-plan/'
OUT = ROOT / PREFIX
SELF = 'work/r85_seal_source_plan_20261016.py'
FILES = [SELF, 'work/r85_cc220_cache_metadata_20261016.py'] + [PREFIX + n for n in [
    'manifest-intake.json', 'owned-r6-manifest.json', 'owned-r6-corrigendum-manifest-r2.json',
    'metadata-claim.json', 'cache-metadata.json', 'metadata.stdout.txt', 'metadata.stderr.txt', 'metadata-command.json']]
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
    if path not in FILES:
        raise RuntimeError('unselected/original source prohibited in retain seal')
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4 * 1024 * 1024 or used + n > 500000:
        raise RuntimeError('local seal reserve')
    raw = fp.read_bytes()
    used += len(raw)
    p = pin(raw)
    events.append({'path': path, 'phase': phase, **p})
    if len(raw) != n or (expected is not None and expected != p):
        raise RuntimeError('local pin differs')
    return raw


def write(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / name).open('xb') as f:
        f.write(raw)
    return {'path': PREFIX + name, **pin(raw)}


def main():
    write('seal-claim.json', {'schema': 'EU4-R85-RETAIN-SEAL-CLAIM/1', 'upstream_original_reads': 0,
                            'actual_authorization': False, 'game_access': False})
    raw = {p: read(p, 'local_before') for p in FILES}
    evidence = json.loads(raw[PREFIX + 'cache-metadata.json'])
    assert pin(raw[PREFIX + 'cache-metadata.json']) == {'bytes': 14693, 'sha256': 'a7d29e110940d15305a4bd928a04ca10ebffdca19b85673095d01e03ab7f2d6d'}
    assert evidence['cache_metadata']['present'] is False
    assert evidence['cache_metadata']['functions_container_type'] == 'dict'
    assert evidence['cache_metadata']['selected_key'] == '0xcc220'
    assert evidence['charged_read_bytes_including_prior_intake'] == 2714677
    assert evidence['source_only_two_pass_bytes'] == 2682814
    assert evidence['R84_seed']['target'] == '0xcc220'
    assert evidence['R84_seed']['raw'] == 'e882d074ff'
    assert int(evidence['R84_seed']['next'], 16) + evidence['R84_seed']['signed_rel32'] == 0xcc220
    before = {p: pin(v) for p, v in raw.items()}
    for p in FILES:
        read(p, 'local_after', before[p])
    guard()
    verify_reserve = 200000
    assert used + verify_reserve <= evidence['seal_verify_reserve']
    upper = evidence['charged_read_bytes_including_prior_intake'] + evidence['manual_upper'] + used + verify_reserve
    assert upper < evidence['budget']
    R6 = 'work/reports/war-peace-api-20261015-r6-registry-lifetime/war/'
    metadata_pin = {'path': PREFIX + 'cache-metadata.json', **pin(raw[PREFIX + 'cache-metadata.json'])}
    plan = {
      'schema': 'EU4-R85-CC220-NEXT-SOURCE-PLAN/1', 'sealed': True,
      'stage': 'author_source_plan_pending_non_author_review', 'scope': 'cache_metadata_and_next_scope_only',
      'no_business_body_analysis': True,
      'current_cache_result': {'source': evidence['cache_metadata']['source'],
         'source_pin': evidence['cache_metadata']['source_pin'], 'functions_container_type': 'dict',
         'exact_key': '0xcc220', 'present': False, 'row_count': None, 'recorded_extent': None,
         'meaning': 'No body under this exact key in this one exact JSON. Other caches/reports and alternate function representations were not searched.'},
      'selected_call_seed': evidence['R84_seed'],
      'historical_first_append_gap': {
         'source': R6 + 'corrigendum-r2.md', 'pin': evidence['source_pins'][R6 + 'corrigendum-r2.md'], 'lines': [11, 14],
         'retained_statement': 'Fresh heap28 owner +10/+18/+20 are zero, so the first append takes da4acf -> cc220. The original scope lacked the callee body; successful first append ownership transfer was not closed.',
         'not_an_observed_native_failure': True,
         'spare_capacity_direct_store_does_not_cover_first_append': True,
         'later_closures_not_reaudited': True},
      'preferred_next_step': {
         'kind': 'bounded_existing_cache_confirmation_before_any_new_PE_acquisition',
         'action': 'Root may select any later retained cc220 body manifest and exact JSON pointer, if available. Its identity, recorded range, raw coverage and previous review boundary should be checked before proposing new code reads.',
         'not_performed_here': True, 'new_source_path': None, 'new_source_pin': None,
         'constraint': 'Do not recursively search the repository or inherit a claim that all caches lack cc220.'},
      'conditional_native_static_scope_if_no_usable_cache': {
         'entry_rva': '0xcc220', 'entry_basis': 'Only the exact R84 direct CALL target arithmetic; no body range is currently proved.',
         'metadata': {'max_pdata_records': 32, 'max_physical_pdata_bytes': 384,
                      'selection': 'exact begin must equal cc220; check adjacent ordering/disjoint intervals',
                      'exact_begin_miss': 'unknown with zero code reads, no search/fallback'},
         'code': {'single_window': True, 'if_extent_at_most_8192': 'selected full extent',
                  'otherwise': 'first 2048 bytes at cc220', 'max_unique_new_code_bytes': 8192,
                  'current_exact_end_unknown': True, 'no_callee_RIP_data_vslot_unwind_neighbor_following': True},
         'proposed_resources': {'self_software_memory': 805306368, 'self_hard_stop': 1073741824,
                  'ordinary_source_file_cap': 4194304,
                  'future_source_budget_requires_new_review': 33554432,
                  'future_retained_budget_requires_new_review': 16777216,
                  'PE_two_SHA_stream_bytes_if_same_38462504B_target': 76925008,
                  'PE_hash_plus_max_selected_code_and_pdata_upper': 76933584,
                  'PE_bytes_separate_from_source_retained_IO': True},
         'required_gates': ['Exact source/budget/producer freeze and non-author source review',
                            'Independent raw caller-entry seed and historical upstream subject checks',
                            'New root exact once grant before decoder/PE access',
                            'Raw-manifest buffer pin before parse or engine reads; pre/post exact pins, single claim, no automatic retry'],
         'actual_authorized': False},
      'questions_that_may_be_narrowed': [
         {'R84': 'On the selected branch97f199, does the concrete cc220 body preserve the current R14 scalar on relevant normal returns? This cannot close unselected caller rows31..240 or other incoming edges.'},
         {'R6': 'After first binding the original retained caller actual arguments, which zero-header normal path reads/copies the input item and publishes new header/end/storage, and under what callee/allocator/alias preconditions?'},
         {'lifetime': 'Which caller-owned or borrowed bytes must remain stable during the helper? Normal field publication cannot itself establish sentinel/definition/world lifetime authority.'}],
      'questions_not_answered': ['Whether cc220 is a C++ vector implementation or has a particular formal signature',
         'Successful allocation, exception/new-handler behavior, script/message-pump/reload reentry',
         'First append final ownership or all caller objects staying alive',
         'Business class, endpoint direction, ordinary diplomacy effects, callable readiness or retry permission'],
      'existing_failure_and_limit_scope': {
         'R6': 'The selected reports describe missing callee/alias/exception evidence, not a proved failed runtime append.',
         'R85': 'Metadata extraction succeeded once without failure; no old scripts, tests or runtime operations were run.',
         'source_scope': 'Exactly seven original pinned sources before/after. R6 indirect scan limits and helper-body gaps retain their historical scope.',
         'not_global_absence': True},
      'all_authority_false': True, 'native_ready': False, 'callable': False, 'actual_authorized': False,
      'sender_authorized': False, 'effect_verified': False, 'lease': False, 'atomic': False}
    plan_pin = write('source-plan.json', plan)
    finding = {'schema': 'EU4-R85-CC220-PLAN-FINDINGS/1', 'sealed': True, 'passed': True,
      'stage': plan['stage'], 'scope': plan['scope'], 'blocking_findings': [],
      'meaning_of_passed': 'The bounded metadata/pin extraction passed; the cc220 body and first append conditions remain unresolved.',
      'role': 'War authored the R6 registry-lifetime scope, R84 and this R85 proposal; this is author planning, not an independent acceptance of those original analyses. Root accepted R84 separately; that review graph is not recursively opened here.',
      'metadata_evidence': metadata_pin, 'source_plan': plan_pin,
      'source_pins': evidence['source_pins'], 'cache_body_available_in_selected_JSON': False,
      'function_row_count': None, 'function_extent': None, 'no_global_cache_absence_proof': True,
      'R84_known_call_entry': evidence['R84_seed'],
      'retained_first_append_limit': {'source': R6 + 'corrigendum-r2.md', 'lines': [11, 14], 'still_unresolved_in_this_scope': True},
      'accounting': {'original_source_only_two_pass_bytes': 2682814,
         'metadata_phase_reads_including_prior_intake_and_local_sources': 2714677,
         'retain_seal_instrumented_reads': used, 'manual_charged_upper': evidence['manual_upper'],
         'local_verification_reserve': verify_reserve, 'whole_stage_upper': upper, 'budget': evidence['budget'],
         'metadata_peak': evidence['peak_working_set'], 'seal_peak': peak, 'not_whole_OS_loader_IO': True},
      'authority': {x: False for x in ['callable', 'native_ready', 'actual_authorized', 'sender_authorized',
          'reader_adoption_authorized', 'first_append_verified', 'ownership_closed', 'business_type_verified',
          'effect_verified', 'world_lease', 'atomic_snapshot', 'retry_authorized']},
      'PE_reads': 0, 'decoder_calls': 0, 'old_programs_executed': False,
      'native_game_calls': 0, 'process_access': False, 'new_requests': 0, 'all_shells_collected': True}
    finding_pin = write('findings.json', finding)
    account_pin = write('read-accounting.json', {'schema': 'EU4-R85-READ-ACCOUNT/1',
         'metadata_evidence': metadata_pin, 'local_events': events, 'retained_read_bytes': used,
         'metadata_read_bytes': 2714677, 'manual_upper': 524288, 'local_verify_reserve': verify_reserve,
         'whole_stage_upper': upper, 'budget': 8388608, 'original_sources_read_by_sealer': 0})
    report = """# R85 cc220 缓存与下一步范围计划\n\n指定 `native-owned-peace-1375.json` 的 `/functions` 是字典，但精确键 `0xcc220` 不存在。因此本轮没有可报告的缓存行数或函数范围。这只限该 SHA 对应的单一文件，不是全仓无缓存证明。\n\nR84 的 `97f199: e882d074ff` 直接目标为 `cc220`。旧 R6 补正第 11–14 行同时指出：新 heap28 owner 的 +10/+18/+20 为零，首次追加必走 da4acf→cc220；原范围没有该 body，不能用 spare-cap 的直接写证明替代首次追加拥有移交。这是证据缺口，不是实机失败。\n\n下一步优先由根任务指定任何后来已有 cc220 缓存的 exact manifest/JSON pointer，先确认元数据及旧审边界。本轮没有搜索这些其他来源。只有没有可用缓存且根任务重新授权时，才建议以 direct-CALL 已证入口 cc220 为单一静态范围：≤32 条 pdata 核 exact begin，extent≤8192 则完整，否则仅首 2048 B；无 exact entry 则 unknown/0 code，不自动滑窗或追 callee。\n\n该 body 将来可能帮助核 R84 当前 R14 的局部 normal-return 保持，以及 R6 零容量 firstappend 的输入复制和 header/end 发布条件；不能据此预认 vector 类型、allocator 成功、完整拥有权、sentinel/world lease 或业务效果。具体条件、未来资源和门禁列于 source-plan.json，当前一律未授权。\n\n本轮仅固定来源元数据和小报告，双遍 pins 相同；未解释 cc220 业务、未运行旧脚本/tests、无 PE/decoder/process/native/新请求。所有权限 false，全部 shell 收齐，供非作者审查。\n"""
    report_raw = report.encode('utf-8')
    with (OUT / 'report.md').open('xb') as f:
        f.write(report_raw)
    report_pin = {'path': PREFIX + 'report.md', **pin(report_raw)}
    manifest_pin = write('manifest.json', {'schema': 'EU4-R85-CC220-SOURCE-PLAN-MANIFEST/1',
        'sealed': True, 'stage': plan['stage'], 'inputs': before,
        'fixed_original_source_pins_witnessed': evidence['source_pins'],
        'outputs': [plan_pin, finding_pin, account_pin, report_pin],
        'original_source_reads_during_seal': 0, 'whole_stage_upper': upper, 'all_authority': False})
    print(json.dumps({'ok': True, 'source_plan': plan_pin, 'findings': finding_pin,
         'manifest': manifest_pin, 'read_accounting': account_pin, 'report': report_pin,
         'retained_reads': used, 'whole_stage_upper': upper, 'peak': peak}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        write('seal-failure.json', {'error': str(exc), 'traceback': traceback.format_exc(),
              'events': events, 'read_bytes': used, 'no_automatic_retry': True})
        print(json.dumps({'ok': False, 'error': str(exc), 'read_bytes': used}))
        sys.exit(1)
