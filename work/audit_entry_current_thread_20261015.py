"""Retained-file current-thread witness audit. No producer import or OS query."""
import argparse
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / 'work/reports/war-peace-api-20261015-r12-entry-live'
OUT = ROOT / 'work/reports/frida-entry-current-thread-review-20261015-r1'
BASE = ROOT / 'work/reports/frida-entry-live-review-20261015-r1'


def pin(path):
    sha = hashlib.sha256()
    count = 0
    with path.open('rb') as stream:
        while raw := stream.read(65536):
            count += len(raw)
            sha.update(raw)
    return {'bytes': count, 'sha256': sha.hexdigest()}


def load(path):
    assert path.stat().st_size < 1024 * 1024
    return json.loads(path.read_text(encoding='utf-8'))


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        if isinstance(value, str):
            stream.write(value)
        else:
            stream.write(json.dumps(value, ensure_ascii=True, indent=2) + '\n')


def check():
    manifest = load(OUT / 'manifest.json')
    assert manifest['sealed'] is True
    for name, expected in manifest['source_pins'].items():
        assert pin(ROOT / name) == expected, name
    print(json.dumps({'status': 'pass', 'pins': len(manifest['source_pins']),
                      'process_read': False, 'producer_executed': False}))


def main():
    witness_path = LIVE / 'current-thread-identity.json'
    producer_path = ROOT / 'work/capture_entry_thread_identity_20261015.py'
    assert pin(witness_path)['sha256'] == '4387696e9e8853ac2e1b66f7f04f308879b7db897a8ac1f642a6be7d1bfcdc5a'
    assert pin(producer_path) == {'bytes': 5405, 'sha256': 'd35e158f0a89122fb76d989f69d6cf666e6489e38e326fe7af4fca9177bdcc90'}
    witness = load(witness_path)
    capture = load(LIVE / 'capture.json')
    payload = load(LIVE / 'owned-payload.json')
    base = load(BASE / 'independent-file-audit.json')
    assert pin(BASE / 'independent-file-audit.json') == {'bytes': 4866, 'sha256': 'a64cb8d8804bbaf5012578780600cc7b49d3c552961d450fc5c2f16bb058e1a1'}
    assert pin(BASE / 'manifest.json')['sha256'] == '0d471c9168598f2af2d7cebd4d4805c14d1b8795794eeebe084be3b131d3ce50'
    assert base['status'] == 'pass_selected_retained_runtime_context' and base['findings'] == []
    source_names = {
        'work/candidates/frida-entry-observer-1375-v1/capture_once.py',
        'work/capture_entry_thread_identity_20261015.py',
        'work/reports/war-peace-api-20261015-r12-entry-live/capture.json',
        'work/reports/war-peace-api-20261015-r12-entry-live/owned-payload.json',
    }
    assert set(witness['source_pins']) == source_names
    for name, expected in witness['source_pins'].items():
        assert pin(ROOT / name) == expected, name
    manifest_path = ROOT / 'work/candidates/frida-entry-observer-1375-v1/host-manifest.json'
    assert pin(manifest_path) == {'bytes': 43987, 'sha256': witness['host_manifest_sha256']}
    assert witness['host_manifest_sha256'] == 'e7673b0e07c052788d6d2c6378939e176f57e79a45ea09888b957741b7370166'
    assert witness['schema'] == 'EU4-ENTRY-CURRENT-THREAD-IDENTITY/1'
    assert type(witness['pid']) is int and witness['pid'] == capture['pid'] == 80340
    assert witness['creation'] == capture['creation'] == '01dd5c075fcf8c26'
    tid = witness['observed_callback_tid']
    assert type(tid) is int and 0 < tid <= 0xffffffff
    assert tid == payload['observation']['thread_id'] == capture['payload_evaluation']['thread_id'] == 35220
    assert type(witness['current_visible_unowned_game_window_tid']) is int
    assert witness['current_visible_unowned_game_window_tid'] == tid
    assert type(witness['selected_current_thread_owner_pid']) is int
    assert witness['selected_current_thread_owner_pid'] == witness['pid']
    assert witness['callback_tid_matches_current_window_thread'] is True
    assert witness['selected_current_thread_alive'] is True
    start = datetime.fromisoformat(capture['captured_utc'])
    observed = datetime.fromisoformat(witness['observed_utc'])
    assert start.tzinfo is not None and observed.tzinfo is not None and observed >= start
    assert witness['retained_capture_started_utc'] == capture['captured_utc']
    thread_ft_hex = witness['selected_current_thread_creation']
    assert len(thread_ft_hex) == 16 and all(c in '0123456789abcdef' for c in thread_ft_hex)
    thread_ft = int(thread_ft_hex, 16)
    delta = start - datetime(1601, 1, 1, tzinfo=timezone.utc)
    start_ft = (delta.days * 86400 + delta.seconds) * 10000000 + delta.microseconds * 10
    assert witness['thread_creation_predates_capture_start'] is (thread_ft <= start_ft)
    assert thread_ft <= start_ft
    seconds, fraction = divmod(thread_ft, 10000000)
    thread_utc = (datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)).strftime('%Y-%m-%dT%H:%M:%S') + f'.{fraction:07d}+00:00'
    false_fields = ('Frida_called', 'retained_stack_or_heap_dereferenced', 'thread_suspended',
                    'thread_context_modified', 'historical_thread_interval_or_owner_lease_proven',
                    'native_ready', 'lifetime_lease')
    for key in false_fields:
        assert witness[key] is False, key
    for key in ('native_game_calls', 'game_fields_written', 'requests_published', 'saves', 'reloads'):
        assert type(witness[key]) is int and witness[key] == 0, key
    # AST/text review of the pinned producer only; never import or run it.
    source = producer_path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert {'OpenThread', 'GetProcessIdOfThread', 'GetThreadTimes', 'WaitForSingleObject', 'CloseHandle'} <= attrs
    assert not attrs.intersection({'SuspendThread', 'ResumeThread', 'GetThreadContext', 'SetThreadContext', 'WriteProcessMemory', 'VirtualAllocEx', 'CreateRemoteThread'})
    main_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    open_call = next(n for n in ast.walk(main_node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'OpenThread')
    rights = open_call.args[0]
    assert isinstance(rights, ast.BinOp) and isinstance(rights.op, ast.BitOr)
    assert isinstance(rights.left, ast.Constant) and rights.left.value == 0x0800
    assert isinstance(rights.right, ast.Constant) and rights.right.value == 0x00100000
    assert isinstance(open_call.args[1], ast.Constant) and open_call.args[1].value is False
    assert isinstance(open_call.args[2], ast.Name) and open_call.args[2].id == 'tid'
    close_finally = [n for n in ast.walk(main_node) if isinstance(n, ast.Try) and any(
        isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == 'CloseHandle'
        for statement in n.finalbody for v in ast.walk(statement))]
    assert len(close_finally) == 1
    assert "with observer.RuntimeCapture(identity,backend) as cap:" in source
    assert "held.identity_check()" in source and "held.modules() == cap.modules and host.verify_manifest() == initial" in source
    assert "ft(times[1]) == 0 and kernel.WaitForSingleObject(handle,0) == 0x102" in source
    assert "digest(CAPTURE) == 'cd96099990856fde385a8499f7e3c1d0a303ed11d6460947d45dab0c9ce83a6b'" in source
    # PAYLOAD lacks a predeclared digest in this producer. Its exact current
    # digest is instead checked against the independently reviewed capture.
    assert pin(LIVE / 'owned-payload.json')['sha256'] == '3e59254de3eb7c52020dc30df71497d64febb6023dbe69da8249ce45b50b66b2'
    report = {
        'schema': 'EU4-ENTRY-INDEPENDENT-CURRENT-THREAD-FILE-AUDIT/1',
        'status': 'pass_selected_current_thread_witness', 'findings': [],
        'base_live_audit_unchanged': pin(BASE / 'independent-file-audit.json'),
        'witness': pin(witness_path), 'producer': pin(producer_path),
        'current_binding': {'pid': witness['pid'], 'creation': witness['creation'],
                            'observed_callback_tid': tid, 'current_window_tid': tid,
                            'current_owner_pid': witness['pid'], 'current_alive_reported': True},
        'creation_replay': {'thread_filetime_hex': thread_ft_hex, 'thread_utc_100ns': thread_utc,
                            'capture_started_utc': capture['captured_utc'],
                            'thread_creation_predates_capture_start': True,
                            'difference_100ns': start_ft - thread_ft,
                            'host_timestamp_is_native_event_timestamp': False},
        'source_review': {'producer_imported_or_executed': False, 'selected_query_rights': 'QUERY_LIMITED_INFORMATION|SYNCHRONIZE',
                          'selected_thread_handle_finally_close': True, 'held_context_normal_exit_before_result_write': True,
                          'current_identity_modules_source_recheck': True, 'retained_Q_or_heap_dereferenced': False,
                          'current_payload_exact_matches_prior_audit': True,
                          'payload_predeclared_literal_sha_in_producer': False},
        'limits': [
            'This audit only reads files and parses producer AST/text. No producer, RuntimeCapture, process API, Frida or REA is executed.',
            'Raw GetThreadTimes four FILETIMEs, Wait status, OS handle and owner-query telemetry were not retained; alive/owner/query/cleanup facts rely on the pinned producer receipt.',
            'The retained creation scalar and captured_utc support exact 100ns arithmetic replay. Capture start is the host wall clock, not an independent callback-event timestamp.',
            'Current TID/window/owner agreement and earlier thread creation do not prove historical thread ownership throughout the capture interval, object/header lease, atomicity or native-entry authentication.',
            'The producer pins the original capture literally; its PAYLOAD file is source-pinned at output rather than by a predeclared literal digest. This audit independently matches it to the prior audited owned payload.',
            'RuntimeCapture performs current identity/image setup checks; no claim of zero setup RPM reads is made. It does not follow retained Q or heap addresses.',
            'The original live audit is immutable. This later current-query witness adds a limited OS binding observation, without retroactively changing its original evidence set or authority flags.'
        ],
        'tests_reexecuted': False, 'producer_executed': False, 'process_read_by_auditor': False,
        'native_ready': False, 'native_entry_authenticated': False, 'lifetime_lease': False,
        'atomic_snapshot': False, 'new_API_effects': 0,
    }
    assert not OUT.exists()
    OUT.mkdir(parents=True)
    write_new(OUT / 'independent-file-audit.json', report)
    write_new(OUT / 'independent-file-audit.md',
        '# 当前线程见证独立文件审计\n\n'
        '通过。固定来源与原捕获、owned payload 的 TID 均为 35220；当前窗口线程和当前线程 owner PID 80340 一致。'
        '重算保留的 FILETIME 创建值早于原 host 捕获开始时间。\n\n'
        '只读核对了 producer 的 QUERY_LIMITED_INFORMATION|SYNCHRONIZE 权限、退出检查、句柄 finally 关闭和 held 身份/模块/源图复核路径。'
        '原始四个 FILETIME、Wait 结果和 OS 句柄未留存，因此相关内核结果仍属固定 producer 回执，不能逐字节重放。\n\n'
        '这是稍后的当前绑定见证。它不证明历史线程区间、对象或 header 寿命、原子性或原生入口认证。'
        'native_ready、native_entry_authenticated、lifetime_lease、atomic_snapshot 均保持 false；未重采、未执行 producer、未触进程、未重跑测试。原入口审计不改写。\n')
    selected = source_names | {
        str(witness_path.relative_to(ROOT)).replace('\\', '/'),
        str(manifest_path.relative_to(ROOT)).replace('\\', '/'),
        str((BASE / 'independent-file-audit.json').relative_to(ROOT)).replace('\\', '/'),
        str((BASE / 'manifest.json').relative_to(ROOT)).replace('\\', '/'),
        str(Path(__file__).resolve().relative_to(ROOT)).replace('\\', '/'),
        str((OUT / 'independent-file-audit.json').relative_to(ROOT)).replace('\\', '/'),
        str((OUT / 'independent-file-audit.md').relative_to(ROOT)).replace('\\', '/'),
    }
    write_new(OUT / 'manifest.json', {'schema': 'EU4-INDEPENDENT-CURRENT-THREAD-FILE-AUDIT-MANIFEST/1',
        'sealed': True, 'source_pins': {name: pin(ROOT / name) for name in sorted(selected)}})
    print(json.dumps({'status': report['status'], 'report': pin(OUT / 'independent-file-audit.json'),
                      'manifest': pin(OUT / 'manifest.json'), 'pins': len(selected)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    check() if args.check else main()
