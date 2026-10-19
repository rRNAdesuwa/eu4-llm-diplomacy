"""R86 retained-only source delivery seal. No target/engine/old program access."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'work/reports/war-peace-api-20261016-r86-cc220-actual-source/'
HERE = ROOT / PREFIX
SELF = 'work/r86_seal_prepared_20261016.py'
EXTRA = [SELF, 'work/r86_intake_template_20261016.py', 'work/r86_build_source_20261016.py']
BASE_PIN = {'bytes': 22473, 'sha256': '74f6c8f8eeeadea9e4216c7b37e2a8034e9fb7967d8dfe7167c7ee1ffd143472'}
RET_LIMIT = 16777216
CHECK_READS = 488888
MANUAL_RESERVE = 1048576
FINAL_VERIFY_RESERVE = 524288
events = []
used = 0
peak = 0


class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
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
        raise RuntimeError('Own memory counter')
    peak = max(peak, int(c.private), int(c.peak_pagefile))
    if not (0 < peak <= 805306368 and peak < 1073741824):
        raise RuntimeError('Own memory guard')


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, phase, expected=None):
    global used
    guard()
    if not (path.startswith(PREFIX) or path in EXTRA):
        raise RuntimeError('Only new owned preparation files in retained seal')
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4194304 or used + n + CHECK_READS + MANUAL_RESERVE + FINAL_VERIFY_RESERVE > RET_LIMIT:
        raise RuntimeError('Retained budget')
    raw = fp.read_bytes()
    used += len(raw)
    p = pin(raw)
    events.append({'path': path, 'phase': phase, **p})
    if len(raw) != n or (expected is not None and p != expected):
        raise RuntimeError('Owned prepared source pin differs')
    return raw


def write(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    if len(raw) > 4194304:
        raise RuntimeError('Generated file cap')
    with (HERE / name).open('xb') as f:
        f.write(raw)
    return {'path': PREFIX + name, **pin(raw)}


def main():
    if sys.argv[1:]:
        raise RuntimeError('No arguments')
    forbidden = ['run-authorization.json', 'claim.json', 'capture.json', 'owned-code.json', 'failure.json']
    if any((HERE / n).exists() for n in forbidden):
        raise RuntimeError('Actual artifacts/grant prohibited at source-only seal')
    write('prepared-seal-claim.json', {'schema': 'EU4-R86-PREPARED-SEAL-CLAIM/1',
        'source_only': True, 'actual_authorized': False, 'engine_or_PE_access': False})
    base_raw = read(PREFIX + 'source-manifest.json', 'owned_before', BASE_PIN)
    base = json.loads(base_raw)
    names = [p.name for p in HERE.iterdir() if p.is_file() and p.name not in ('prepared-final-manifest.json', 'prepared-delivery.json', 'delivery-manifest.json')]
    paths = [PREFIX + n for n in sorted(names)] + EXTRA
    raw = {PREFIX + 'source-manifest.json': base_raw}
    for path in paths:
        if path not in raw:
            raw[path] = read(path, 'owned_before')
    identity = json.loads(raw[PREFIX + 'prepared-identity.json'])
    prep = json.loads(raw[PREFIX + 'preparation.json'])
    check = json.loads(raw[PREFIX + 'prepared-filecheck.json'])
    if not (identity['source_manifest'] == BASE_PIN and check['source_manifest'] == BASE_PIN
            and check['sealed'] and check['passed'] and check['read_bytes'] == CHECK_READS):
        raise RuntimeError('First prepared filecheck exact subjects')
    if not (base['actual_source_pin_count'] == 22 and len(base['decoder_expected_witness_pins']) == 38
            and check['actual_source_pin_count'] == 22 and check['decoder_metadata_count'] == 38):
        raise RuntimeError('Flat source/engine witness count')
    if any(base[n] is not False for n in ('actual_authorized', 'tests_authorized', 'native_ready', 'callable',
           'reader_adoption_allowed', 'selected_effect_verified', 'world_lease', 'atomic_snapshot', 'authorizes_retry')):
        raise RuntimeError('False authority required')
    # Latest first checker already hashed every actual source twice. The sealer
    # verifies those exact records and only reopens new owned preparation files.
    for path, expected in base['actual_source_pins'].items():
        matches = [x for x in check['read_events'] if x['path'] == path]
        if len(matches) != 2 or any({k: x[k] for k in ['bytes', 'sha256']} != expected for x in matches):
            raise RuntimeError('Checker source pre/post witness differs: ' + path)
    before = {p: pin(v) for p, v in raw.items()}
    for path, expected in before.items():
        read(path, 'owned_after', expected)
    guard()
    retained_upper = CHECK_READS + used + MANUAL_RESERVE + FINAL_VERIFY_RESERVE
    if retained_upper > RET_LIMIT or prep['whole_build_upper'] > 33554432:
        raise RuntimeError('Stage budget')
    account = {'schema': 'EU4-R86-PREPARED-READ-ACCOUNT/1', 'sealed': True,
        'source_build_explicit_read_bytes': prep['explicit_build_read_bytes_including_prior_intake'],
        'source_build_upper': prep['whole_build_upper'], 'source_build_limit': 33554432,
        'source_build_manual_and_close_reserves': prep['manual_charged_upper'] + prep['remaining_build_close_reserve'],
        'first_new_prepared_check_read_bytes': CHECK_READS, 'retained_seal_read_bytes': used,
        'retained_events': events, 'retained_manual_upper': MANUAL_RESERVE,
        'final_owned_verification_reserve': FINAL_VERIFY_RESERVE, 'retained_upper': retained_upper, 'retained_limit': RET_LIMIT,
        'current_target_PE_bytes': 0, 'current_engine_body_bytes': 0,
        'future_PE_two_SHA_stream_bytes_separate': 76925008,
        'future_conditional_source_estimate': base['conditional_estimated_future_source_bytes'],
        'not_OS_loader_or_failure_partial_IO_bound': True}
    account_pin = write('prepared-read-accounting.json', account)
    report = '''# R86 cc220 单入口静态采集 SOURCE ONLY

R86 已根据新的 source-build grant 构建并冻结源码。produce.py 没有 import/执行；没有 EXE stat/open/hash、decoder import/body读取、旧程序/tests 或游戏/native操作。当前没有 run-authorization、实际 claim、capture 或 owned-code。

复用固定 R79 producer 的 10 个顶层 helper，逐字及 AST 相同；mapping/authenticate/target_read/record 四个 main 内采集 helper AST 相同。新 main 只绑定 R86 身份、97f199 E8→cc220、R84 caller 原始 buffer/pointer 和实际 review 形状。R85 root 上游只有 findings，故 upstream_plan_review 是单 findings；新 raw/source-peer 仍需 findings+manifest 和三精确 subjects。全部门禁与另一次 root oncegrant通过前不能访问 engine/PE。

未来范围严格为 cc220 exactbegin：最多32条/384B pdata，完整extent≤8192则单读完整，否则首2048；无exact或无有效唯一映射则unknown0code，不fallback。调用目标/邻字段/外callee/RIPdata/vslot/unwind/header不跟踪。EXE 两整SHA流76925008B单列，不与source预算混写。

source-manifest.json 是22个当前已读并核验的text源+38个仅metadata decoder pins的flat graph。Capstone5.0.7 bytes仅继承固定witness，prep没有stat/open body；使用ordinary Capstone的未来代码，不伪称REA Evidence ID。已知Ghidra/IDA未配置，无重复diagnostic或安装。

首次源码构建与首次新filecheck均exit0，语法检查只compile AST；这不是非作者source peer，也不是actual授权。caller RCX/RDX/R8 只是当前机器位来源，不能预认vector/formal/type/extent/ownership。首次append、R14跨callee保持、allocator/异常/reentry/lease/业务效果仍未解决，全部ready/callable/effect/reader/retry权限false。

精确源/seed/producer/budget在 prepared-final-manifest 和 prepared-delivery；各stage真实read与预留分账在 prepared-read-accounting。所有shell收齐，等待根任务完整非作者源码审查。
'''
    report_raw = report.encode('utf-8')
    with (HERE / 'SOURCE_STATUS.md').open('xb') as f:
        f.write(report_raw)
    report_pin = {'path': PREFIX + 'SOURCE_STATUS.md', **pin(report_raw)}
    files = dict(base['actual_source_pins'])
    for path, p in before.items():
        if path in files and files[path] != p:
            raise RuntimeError('Owned/source graph pin collision')
        files[path] = p
    files[account_pin['path']] = {k: account_pin[k] for k in ['bytes', 'sha256']}
    files[report_pin['path']] = {k: report_pin[k] for k in ['bytes', 'sha256']}
    final_pin = write('prepared-final-manifest.json', {'schema': 'EU4-R86-PREPARED-FINAL-MANIFEST/1',
        'sealed': True, 'stage': 'source_only_author_complete_pending_non_author_source_review',
        'source_manifest': {'path': PREFIX + 'source-manifest.json', **BASE_PIN},
        'producer': {'path': PREFIX + 'produce.py', **identity['producer_pin']},
        'entry_seed': {'path': PREFIX + 'entry-seed.json', **identity['entry_seed_pin']},
        'files': files, 'file_count': len(files),
        'decoder_expected_witness_pins_metadata_only': base['decoder_expected_witness_pins'],
        'engine_body_stat_open_during_prep': False, 'PE_stat_open_hash_during_prep': False,
        'actual_source_prepost_witness': {'path': PREFIX + 'prepared-filecheck.json', **before[PREFIX + 'prepared-filecheck.json']},
        'sealer_reopened_upstream_original_texts': False,
        'source_build_upper': prep['whole_build_upper'], 'retained_upper': retained_upper,
        'actual_authorized': False, 'non_author_source_review_claimed': False,
        'native_ready': False, 'callable': False, 'selected_effect_verified': False,
        'world_lease': False, 'atomic_snapshot': False, 'authorizes_retry': False})
    delivery_pin = write('prepared-delivery.json', {'schema': 'EU4-R86-PREPARED-DELIVERY/1', 'sealed': True,
        'prepared_final_manifest': final_pin, 'source_manifest': {'path': PREFIX + 'source-manifest.json', **BASE_PIN},
        'producer': {'path': PREFIX + 'produce.py', **identity['producer_pin']},
        'entry_seed': {'path': PREFIX + 'entry-seed.json', **identity['entry_seed_pin']},
        'budget': {'path': PREFIX + 'budget.json', **base['actual_source_pins'][PREFIX + 'budget.json']},
        'protocol': {'path': PREFIX + 'PROTOCOL.md', **base['actual_source_pins'][PREFIX + 'PROTOCOL.md']},
        'first_filecheck': {'path': PREFIX + 'prepared-filecheck.json', **before[PREFIX + 'prepared-filecheck.json']},
        'source_read_accounting': account_pin, 'status': report_pin,
        'future_review_subject_shape': 'subject_source_manifest/subject_producer/subject_entry_seed are exact pin-only {bytes,sha256}; raw scope is raw_direct_call_entry_seed_only',
        'actual_authorized': False, 'producer_executed': False, 'tests_run': 0,
        'native_ready': False, 'all_shells_collected_on_return': True})
    publication_pin = write('delivery-manifest.json', {'schema': 'EU4-R86-PREPARED-DELIVERY-MANIFEST/1',
        'sealed': True, 'files': {p['path']: {k: p[k] for k in ['bytes', 'sha256']} for p in [final_pin, delivery_pin, account_pin, report_pin]},
        'prepared_final_manifest_contains_flat_text_pins': True,
        'engine_body_not_verified': True, 'actual_authorized': False, 'non_author_source_review_claimed': False,
        'all_authority': False})
    print(json.dumps({'ok': True, 'prepared_final_manifest': final_pin, 'prepared_delivery': delivery_pin,
        'delivery_manifest': publication_pin, 'read_accounting': account_pin,
        'flat_text_pins': len(files), 'engine_metadata': 38, 'retained_read_bytes': used,
        'retained_upper': retained_upper, 'source_build_upper': prep['whole_build_upper'], 'peak': peak,
        'actual_authorized': False}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        write('prepared-seal-failure.json', {'error': str(exc), 'traceback': traceback.format_exc(),
            'read_events': events, 'retained_read_bytes': used, 'actual_authorized': False})
        print(json.dumps({'ok': False, 'error': str(exc), 'read_bytes': used}))
        sys.exit(1)
