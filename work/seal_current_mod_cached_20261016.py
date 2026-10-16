"""Retain-only seal; reads this source and owned extraction artifacts, never old inputs."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/current-mod-field-cached-source-20261016-r1'
SELF = 'work/seal_current_mod_cached_20261016.py'
PREFIX = str(OUT.relative_to(ROOT)).replace('\\', '/') + '/'
NAMES = ['claim.json', 'extraction.json', 'source-manifest.json', 'read-account.json',
         'extraction-manifest.json', 'extraction.stdout.txt', 'extraction.stderr.txt',
         'command-receipt.json', 'launch-failure.json', 'launch-continuation.json',
         'continuation.stdout.txt', 'continuation.stderr.txt', 'continuation-command-receipt.json']
CAP = 650000
TOTAL_CAP = 4194304
events = []
charged = 0
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
        raise RuntimeError('self measurement unavailable')
    peak = max(peak, p.PeakWorkingSetSize)
    if p.WorkingSetSize > 768 * 1024 * 1024 or p.PeakWorkingSetSize > 1024 * 1024 * 1024:
        raise RuntimeError('self memory guard')


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, phase, expected=None):
    global charged
    guard()
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4194304 or charged + n > CAP:
        raise RuntimeError('local seal read budget')
    with fp.open('rb') as f:
        raw = f.read(n + 1)
    charged += len(raw)
    p = pin(raw)
    events.append({'path': path, 'phase': phase, **p})
    if len(raw) != n or (expected is not None and p != expected):
        raise RuntimeError('local source differs: ' + path)
    return raw


def write(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode('ascii')
    with (OUT / name).open('xb') as f:
        f.write(raw)
    return {'path': PREFIX + name, **pin(raw)}


def main():
    claim = write('seal-claim.json', {'schema': 'EU4-CACHED-FIELD-RETAIN-SEAL-CLAIM/1',
         'single_seal': True, 'old_source_body_reads': 0, 'game_access': False})
    paths = [SELF] + [PREFIX + n for n in NAMES]
    raw = {p: read(p, 'local_before') for p in paths}
    docs = {n: json.loads(raw[PREFIX + n].decode('utf-8-sig')) for n in NAMES if n.endswith('.json')}
    extraction = docs['extraction.json']
    source = docs['source-manifest.json']
    bill = docs['read-account.json']
    assert extraction['rva'] == '0x233e064' and extraction['rva_decimal'] == 36954212
    assert extraction['json_matches'] == [] and extraction['bounded_text_matches'] == []
    assert extraction['explicit_base_metadata'] == [{'source': 'work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/static.json',
        'pointer': '/image_base', 'key': 'image_base', 'value': '0x140000000', 'number': 5368709120}]
    assert extraction['authorized_normalized_numeric_targets'] == [36954212, 5405663332]
    assert 5368709120 + 36954212 == 5405663332 == int('14233e064', 16)
    assert source['raw_pin_before_parse'] and source['fixed_sources_before_after_reads'] == 8
    assert bill['charged_read_bytes'] == 3147462 and bill['fixed_source_two_pass'] == 3103976
    assert docs['launch-failure.json']['entry_script_started'] is False
    assert docs['launch-failure.json']['extraction_claim_exists'] is False
    assert docs['command-receipt.json']['exit_code'] == 2
    assert docs['continuation-command-receipt.json']['exit_code'] == 0
    assert docs['continuation-command-receipt.json']['first_extractor_execution'] is True
    own_extractor = source['reviewer_source']
    assert own_extractor['bytes'] == 13453 and own_extractor['sha256'] == 'fe5baa0fb4df9af282f290f603c7141d5ffcc2d1a1ebe38bd3b9ac3b8441bdd0'
    for out in docs['extraction-manifest.json']['outputs']:
        assert pin(raw[out['path']]) == {'bytes': out['bytes'], 'sha256': out['sha256']}
    before = {p: pin(v) for p, v in raw.items()}
    for path in paths:
        read(path, 'local_after', before[path])
    guard()
    # Known wrapper/manual reads, derived from immutable sizes; the larger manual
    # allowance remains the conservative charged envelope, never an OS IO claim.
    def size(name):
        return len(raw[PREFIX + name])
    manual_known = [
        {'activity': 'initial subject metadata read', 'bytes': 8290},
        {'activity': 'two wrapper extractor hashes', 'bytes': 2 * own_extractor['bytes']},
        {'activity': 'first failure local log hashes', 'bytes': size('extraction.stdout.txt') + size('extraction.stderr.txt') + size('command-receipt.json')},
        {'activity': 'continuation prior failure hashes', 'bytes': sum(size(n) for n in ['launch-failure.json', 'extraction.stdout.txt', 'extraction.stderr.txt', 'command-receipt.json'])},
        {'activity': 'failed launch stdout/stderr view', 'bytes': size('extraction.stdout.txt') + size('extraction.stderr.txt')},
        {'activity': 'first extractor stdout/stderr view', 'bytes': size('continuation.stdout.txt') + size('continuation.stderr.txt')},
        {'activity': 'local extraction/read-account/receipt review', 'bytes': size('extraction.json') + size('read-account.json') + size('continuation-command-receipt.json')},
    ]
    manual_sum = sum(x['bytes'] for x in manual_known)
    assert manual_sum <= 131072
    # This seal includes one future local output verification/view allowance.
    verification_reserve = 100000
    total_upper = bill['charged_read_bytes'] + 131072 + charged + verification_reserve
    assert charged + verification_reserve <= 650000 and total_upper <= TOTAL_CAP
    authorities = {name: False for name in ['native_ready', 'callable', 'sender_authorized',
        'runtime_authorized', 'selected_effect_verified', 'field_semantics_verified', 'mod_installed_verified',
        'world_lease', 'atomic_snapshot', 'retry_authorized', 'policy_guard_change_authorized']}
    finding = {
        'schema': 'EU4-CACHED-CURRENT-MOD-FIELD-FINDINGS/1', 'sealed': True, 'passed': True,
        'scope': 'four_fixed_retained_sources_explicit_field_reference_investigation',
        'blocking_findings': [],
        'meaning_of_passed': 'The exact bounded source extraction and its pins passed; native field semantics remain unknown.',
        'investigator_role': 'War API subagent; author of this investigation and prior restarted-peace capture review, not author of the root runtime capture. This is not an independent semantic acceptance of the four historical sources.',
        'subject_prior_review': source['subject'],
        'sources': source['fixed_sources'],
        'address': {'rva': '0x233e064', 'rva_decimal': 36954212, 'preferred_base': '0x140000000',
            'preferred_va': '0x14233e064', 'preferred_va_decimal': 5405663332,
            'base_source': {'path': 'work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/static.json',
                            'pointer': '/image_base', 'value': '0x140000000'},
            'width': 'Prior independent live review witnessed one signed DWORD read. No additional native consumer operand width was recovered here.'},
        'selected_result': {
            'status': 'unknown_native_field_meaning', 'explicit_json_value_matches': 0,
            'explicit_text_line_matches': 0, 'native_consumer_rows': [], 'native_writer_rows': [],
            'native_initialization_rows': [], 'mod_label_native_proof': False,
            'reason': 'No retained selected context explicitly names the RVA, the metadata-normalized preferred VA, or their decimal values.'},
        'interpretation_limits': [
            'This search checks retained scalar values/address text and bounded contexts, not decoded RIP-displacement resolution or all pointer aliases.',
            'Zero explicit matches in these four caches is not evidence that the native binary lacks readers, writers, initialization, or mode-dependent use.',
            'The prior error message Unsupported current Mod and synthetic -1 policy defaults do not prove an installed Mod, localization Mod, multiplayer, or any native mode meaning.',
            'The source /image_base permits arithmetic normalization only; it does not authenticate the current loaded module or current global lifetime.',
            'No raw instruction rows matched this field, so no machine consumer/writer/init byte arithmetic is claimed.',
            'trace.py was parsed as source for imports only, never imported, compiled, run, or treated as native evidence.',
            'Pre/post source equality is a witness, not external atomicity or ABA exclusion.'
        ],
        'relation_to_scheme_B': {
            'native_contradiction_found': False,
            'statement': 'No contradictory native field meaning was recovered. This investigation grants no production or runtime permission and does not validate removal or weakening of any other guard.',
            'diagnostic_only_candidate': 'The separately reviewed v2 may preserve two raw scalar observations as an unknown diagnostic, subject to its own source review and all typed/layout/code/identity guards.'},
        'next_scope_not_authorized': {
            'retained_sources_exhausted_for_explicit_references': True,
            'native_question': 'Which actual fixed-PE instruction initializes, reads, or writes RVA 0x233e064, and under what conditions?',
            'requirement': 'A new separately bounded source or static-reference scope would be needed; no new file, PE range, caller, or callee is selected or authorized here.'},
        'execution_history': {'initial_launcher_exit': 2, 'extractor_executions_before_launcher_fix': 0,
            'root_authorized_launcher_only_continuation': True, 'extractor_first_and_only_exit': 0,
            'extractor_source_unchanged': own_extractor,
            'claim_exclusive': True, 'actual_extraction_retries': 0, 'trace_executions': 0},
        'accounting': {'fixed_four_source_prepost_bytes': 3103976, 'instrumented_extraction_read_bytes': 3147462,
            'manual_known_size_derived_bytes': manual_sum, 'manual_charged_upper': 131072,
            'retained_seal_instrumented_read_bytes': charged, 'future_local_verify_reserve': verification_reserve,
            'whole_stage_charged_upper': total_upper, 'budget': TOTAL_CAP,
            'extractor_peak_working_set': 30760960, 'sealer_peak_working_set': peak,
            'not_whole_OS_loader_IO': True},
        'authority': authorities,
        'process_reads': 0, 'PE_reads': 0, 'decoder_calls': 0, 'native_game_calls': 0,
        'game_data_writes': 0, 'new_diplomacy_requests': 0, 'hooks': 0,
        'all_shells_collected': True,
    }
    finding_pin = write('findings.json', finding)
    account_pin = write('seal-read-account.json', {'schema': 'EU4-CACHED-FIELD-SEAL-READS/1',
        'events': events, 'instrumented_seal_bytes': charged, 'manual_size_derived_events': manual_known,
        'manual_known_bytes': manual_sum, 'manual_charged_upper': 131072,
        'extractor_bytes': 3147462, 'future_local_verify_reserve': verification_reserve,
        'whole_stage_charged_upper': total_upper, 'source_cap': TOTAL_CAP,
        'same_four_sources_not_read_by_sealer': True, 'self_peak_working_set': peak})
    report = """# 固定缓存字段来源调查\n\n四个固定源的前后 SHA 一致，首次且唯一提取完成；未发现字段 `RVA 0x233e064` 的显式地址或数值引用。`static.json#/image_base` 明确为 `0x140000000`，因此 preferred VA 可据实换算为 `0x14233e064`；十进制分别为 36954212 与 5405663332。\n\n本轮没有取到该字段的原生 consumer、writer 或初始化指令，字段语义仍为 unknown。零匹配只覆盖四份缓存的显式地址表示；没有重建 RIP 位移、间接别名或整个 PE 的引用图。旧错误文字 “Unsupported current Mod” 不足以证明安装了 Mod、汉化 Mod、多人模式或其他 native 含义。\n\n没有发现反对独立 v2 诊断方案的 native 语义，但本报告不批准运行、不授权改 guard，也不把诊断值当业务效果。trace.py 仅做源码 AST 读取，未执行。全部 process/PE/decoder/native/新外交请求为 0，authority 全 false。\n\n首次 launcher 路径参数解析失败 exit 2，未启动提取脚本、未创建提取 claim；原日志保留。经根任务明确允许，仅修 launcher，冻结脚本字节不变；唯一提取 exit 0，无提取重试。四源双遍 3,103,976 B，完整提取账 3,147,462 B；其余局部封存和 manual 上界见 findings/read-account，累计在 4 MiB 内。\n"""
    with (OUT / 'report.md').open('xb') as f:
        f.write(report.encode('utf-8'))
    report_pin = {'path': PREFIX + 'report.md', **pin(report.encode('utf-8'))}
    outputs = [finding_pin, account_pin, report_pin, claim]
    manifest = {'schema': 'EU4-CACHED-FIELD-FINAL-MANIFEST/1', 'sealed': True, 'passed': True,
        'scope': finding['scope'], 'inputs': {p: before[p] for p in paths},
        'fixed_source_pins_witnessed_by_extractor': source['fixed_sources'],
        'outputs': outputs, 'source_prepost_verified': True, 'old_source_reads_during_seal': 0,
        'whole_stage_upper': total_upper, 'all_authority': False}
    manifest_pin = write('manifest.json', manifest)
    print(json.dumps({'ok': True, 'findings': finding_pin, 'manifest': manifest_pin,
                      'read_account': account_pin, 'report': report_pin,
                      'seal_read_bytes': charged, 'manual_known': manual_sum,
                      'whole_stage_upper': total_upper, 'sealer_peak': peak}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        with (OUT / 'seal-failure.json').open('xb') as f:
            f.write((json.dumps({'error': str(exc), 'traceback': traceback.format_exc(),
                'events': events, 'charged': charged, 'no_automatic_retry': True}, indent=2) + '\n').encode())
        print(json.dumps({'ok': False, 'error': str(exc), 'charged': charged}))
        sys.exit(1)
