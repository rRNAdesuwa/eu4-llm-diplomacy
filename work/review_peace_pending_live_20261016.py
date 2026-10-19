"""Non-author file-only replay of one failed/closed live attempt; never queries game."""
from pathlib import Path
import ast
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[1]
SUB = 'work/reports/peace-current-pending-observer-live-20261016-r1/'
CLI = 'work/candidates/peace-current-pending-observer-1375-v1/'
OUT = ROOT / 'work/reports/peace-current-pending-observer-live-independent-20261016-r1'
MANIFEST_PIN = dict(bytes=6411, sha256='b802fead2a7810763f82868e7791fb74ceda06c86dcff4b498244a049f2ac374')
CAPTURE_PIN = dict(bytes=41058, sha256='e3900ec5a6fb5f7451ce301231c6fab0fc7678e7549af1ef3b078e2f16c5e011')
READS, CACHE = [], {}
TOTAL = 0


def pin(b):
    return dict(bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def read(path, expected=None, phase='before'):
    global TOTAL
    p = (ROOT / path).resolve()
    assert p.is_relative_to(ROOT) and 0 <= p.stat().st_size <= 4194304
    with p.open('rb') as f:
        b = f.read(4194305)
    assert len(b) <= 4194304
    TOTAL += len(b)
    assert TOTAL + 1048576 < 16777216
    actual = pin(b)
    assert expected is None or actual == expected, path
    READS.append(dict(path=path, phase=phase, **actual))
    if phase == 'before':
        assert path not in CACHE or CACHE[path] == b
        CACHE[path] = b
    return b


def obj(path):
    return json.loads(CACHE[path])


def save(name, value):
    b = (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + '\n').encode()
    with (OUT / name).open('xb') as f:
        f.write(b)
    return pin(b)


def main():
    assert not OUT.exists()
    owner = json.loads(read(SUB + 'final-manifest.json', MANIFEST_PIN))
    assert owner['sealed'] is True and owner['status_attempts_total'] == 1 and owner['no_second_status'] is True
    selected = {}
    for group in ('local_pins', 'captured_source_pins', 'explanatory_after_only_source_pins', 'auxiliary_after_only_sources'):
        for path, expected in owner[group].items():
            assert path not in selected or selected[path] == expected
            selected[path] = expected
    assert len(owner['local_pins']) == 19
    for path, expected in selected.items():
        read(path, expected)
    assert pin(CACHE[SUB + 'capture.json']) == CAPTURE_PIN
    assert CACHE[SUB + 'capture.json'] == CACHE[SUB + 'stdout.txt']
    assert CACHE[SUB + 'stderr.txt'] == b''
    receipt = obj(SUB + 'receipt.json')
    cap = obj(SUB + 'capture.json')
    explanation = obj(SUB + 'guard-raw-explanation.json')
    assert receipt['control_passed'] is True and receipt['control_failure'] is None
    assert receipt['status_attempts'] == receipt['maximum_status_attempts'] == 1
    assert receipt['second_status_attempt'] is False
    assert receipt['source_before'] == receipt['source_after'] and receipt['source_unchanged'] is True
    assert receipt['capture'] == CAPTURE_PIN
    chosen = dict(actor='FRA', target='ENG', pid=38076, creation='01dd5cac0b1ad003')
    assert cap['selection'] == receipt['selection'] == chosen
    assert cap['identity']['pid'] == 38076 and cap['identity']['creation'] == chosen['creation']
    assert cap['identity_purpose'] == 'Fresh readonly nonce, not installed session or original request'
    job = receipt['job']
    assert job['exit_code'] == 2 and job['error'] is None and job['direct_child_collected'] is True
    assert job['job_active_processes_final'] == 0 and job['job_total_processes'] == 2
    assert job['completed_command_descendants_terminated'] is False and job['existing_target_game_assigned_to_job'] is False
    assert job['peak_job_commit'] < job['memory_limit'] == 805306368
    assert cap['status'] == receipt['status'] == 'unknown'
    assert cap['samples'] == [] and cap['selected_queue_presence'] is None
    assert cap['selected_two_pass_equal'] is cap['commit_after_context_exit'] is False
    assert cap['precheck'] is cap['postcheck'] is cap['code_before'] is None
    assert cap['normal_context_exit'] is cap['held_handle_cleared'] is True
    assert cap['close_os_return_checked'] is False
    assert cap['process_rights'] == 'QUERY/VM_READ/SYNCHRONIZE'
    assert cap['disk_before'] == cap['disk_after']
    assert cap['disk_before']['bytes'] == 38462504 and cap['disk_before']['sha256'] == cap['game_sha256'] == '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
    assert len(cap['errors']) == 2 and {e['message'] for e in cap['errors']} == {'Single player server type changed'}
    assert {e['stage'] for e in cap['errors']} == {'sample', 'host_sources_after'}
    assert all(value is False for value in receipt['authority'].values())
    for name in receipt['authority']:
        assert cap[name] is False
    for name in ('game_fields_written', 'native_game_calls', 'requests_published', 'saves', 'reloads', 'hooks_installed'):
        assert cap[name] == 0
    assert receipt['current_state_observed'] is False
    profile = obj(CLI + 'source-manifest.json')
    assert profile['sealed'] is profile['runtime_capture_authorized'] is True
    candidate = cap['source_graph']['candidate']
    assert candidate['manifest'] == pin(CACHE[CLI + 'source-manifest.json'])
    assert candidate['source_graph_sha256'] == profile['source_graph_sha256']
    # Authenticate the selected new graph now; do not recursively expand the old delegated host graph.
    for path, expected in profile['source_pins'].items():
        assert candidate['source_pins'][path] == expected
        if path not in CACHE:
            read(path, expected)
        else:
            assert pin(CACHE[path]) == expected
        selected[path] = expected
    journal = cap['raw_ordered_read_journal']
    assert len(journal) == 19 and [e['ordinal'] for e in journal] == list(range(1, 20))
    for e in journal:
        raw = bytes.fromhex(e['raw_hex'])
        assert e['status'] == 'complete' and len(raw) == e['requested_bytes'] == e['returned_bytes']
        address = int(e['address'], 16)
        assert 0x10000 <= address < 2**47 and 0 < len(raw) <= 65536 and address + len(raw) <= 2**47
    assert sum(e['requested_bytes'] for e in journal) == sum(e['returned_bytes'] for e in journal) == 9039
    assert cap['rpm_budget']['calls_attempted'] == 19 and cap['rpm_budget']['bytes_requested'] == cap['rpm_budget']['bytes_returned'] == 9039
    assert cap['rpm_budget']['largest'] == 8192
    assert cap['rpm_budget']['limits'] == dict(bytes=524288, calls=4096, single_read=65536)
    assert [e['stage'] for e in journal] == ['entry_PE'] + ['host_before'] * 7 + ['code_after'] * 4 + ['host_after'] * 7
    base = int(journal[0]['address'], 16)
    assert base == 0x7ff635e20000 and journal[0]['requested_bytes'] == 8192
    header = bytes.fromhex(journal[0]['raw_hex'])
    assert header[:2] == b'MZ'
    nt = struct.unpack_from('<I', header, 0x3c)[0]
    assert header[nt:nt + 4] == b'PE\0\0' and struct.unpack_from('<H', header, nt + 4)[0] == 0x8664
    assert struct.unpack_from('<H', header, nt + 24)[0] == 0x20b
    image_size = struct.unpack_from('<I', header, nt + 24 + 56)[0]
    # The loaded optional-header ImageBase is not taken as the preferred on-disk ImageBase.
    before, after = journal[1:8], journal[12:19]
    assert [(x['address'], x['raw_hex']) for x in before] == [(x['address'], x['raw_hex']) for x in after]
    q = lambda e: struct.unpack('<Q', bytes.fromhex(e['raw_hex']))[0]
    game, db, game_vt, array, counts, server, server_vt = [q(e) for e in before]
    expected_addresses = [base + 0x233fe78, base + 0x233d8d0, game, db + 0x118, db + 0x120, game + 0x1e00, server]
    assert [int(e['address'], 16) for e in before] == expected_addresses
    assert struct.unpack('<II', bytes.fromhex(before[4]['raw_hex'])) == (1380, 1380)
    assert game_vt == base + 0x1cb00c8
    assert server == 0x19265843010 and server_vt == 0x7ff637b7a8c8
    actual_rva = server_vt - base
    assert actual_rva == 0x1d5a8c8 != 0x1cb8460 and actual_rva < image_size
    assert explanation['candidate_rva_from_subtraction'] == hex(actual_rva)
    assert explanation['expected_guard_rva'] == '0x1cb8460'
    assert explanation['world_loaded'] is explanation['manual_pause'] is explanation['peace_request_rejected'] is None
    assert explanation['selected_country_or_queue_reads'] == 0
    code_plan = obj('work/reports/peace-current-pending-reader-design-20261016-r1/loaded-code-candidates.json')
    assert len(cap['code_after']) == len(code_plan['ranges']) == 4
    for sample, plan, event in zip(cap['code_after'], code_plan['ranges'], journal[8:12]):
        assert sample['rva'] == plan['start_rva'] and sample['raw_hex'] == plan['raw_hex']
        raw = bytes.fromhex(sample['raw_hex'])
        assert pin(raw)['sha256'] == sample['sha256'] == plan['sha256']
        assert int(event['address'], 16) == base + int(sample['rva'], 16)
        assert event['code_bytes'] is True and event['raw_hex'] == sample['raw_hex']
    assert sum(x['bytes'] for x in cap['code_after']) == 735
    assert 8192 + 56 + 735 + 56 == 9039
    assert '0X1CB8460' in CACHE['bridge/diplomacy_effect_observer.py'].decode().upper()
    for path, b in CACHE.items():
        if path.endswith('.py'):
            ast.parse(b)
    for path, expected in selected.items():
        read(path, expected, 'after')
    read(SUB + 'final-manifest.json', MANIFEST_PIN, 'after')
    OUT.mkdir()
    replay = save('raw-replay.json', dict(schema='EU4-PEACE-FIRST-LIVE-UNKNOWN-RAW-REPLAY/1', sealed=True,
        sample_count=0, queue_reads=0, pause_guard_reached=False,
        journal_count=19, journal_requested_returned_bytes=9039,
        budget_decomposition=dict(entry_header=8192, host_before_partial=56, code_after=735, host_after_partial=56),
        host_addresses=[hex(a) for a in expected_addresses], game=hex(game), database=hex(db), array=hex(array),
        server=hex(server), server_first_qword=hex(server_vt), candidate_rva=hex(actual_rva), expected_rva='0x1cb8460',
        partial_host_raw_prepost_equal=True, complete_host_validated=False, after_only_loaded_code_equal=True,
        no_full_before_after_code_pair=True, code_before_missing=True, loaded_PE_fields_replayed=True,
        loaded_image_size=image_size, preferred_ImageBase_not_inferred_from_loaded_header=True,
        raw_ordered_read_journal=journal))
    findings = save('findings.json', dict(schema='EU4-PEACE-FIRST-LIVE-INDEPENDENT-UNKNOWN-REVIEW/1',
        sealed=True, passed=True, blocking_findings=[], subject_capture_pin=CAPTURE_PIN,
        subject_final_manifest_pin=MANIFEST_PIN, subject_cli_pin=profile['source_pins'][CLI + 'peace_current_pending.py'],
        subject_source_graph_sha256=profile['source_graph_sha256'], raw_replay=replay,
        result='Unknown correctly retained at server-vtable equality guard; no selected queue/world-pause compatibility result.',
        source_scope='19 local files, nine unique fixed/explanatory sources, one after-only OS identity receipt, and 32 selected new-owner sources; no recursive old-host closure.',
        status_attempts_replayed=1, no_second_status=True, expected_cli_exit_code=2,
        control_passed_is_not_query_success=True, current_queue_presence=None,
        normal_context_exit=True, held_handle_cleared=True, close_os_return_checked=False,
        limits=['Only seven partial host reads repeat. Complete roots, manual pause, selected country table, action prefixes and queue were not reached.',
                'The four loaded-code slices were read only after the failed guard, not as a completed before/after pair.',
                'Actual first-QWORD subtraction gives candidateRVA1d5a8c8 versus frozen1cb8460. This is no RTTI/class/layout/lifetime/mode proof.',
                'Nothing establishes unloaded world, unpaused state, multiplayer mode, acceptance, rejection or queue absence.',
                'OS inventory was after-only auxiliary to the controller receipt. It is not claimed as a before-claim file pin.',
                'New graph/current selected files were independently hashed now. Runtime deep-library source/identity/disk checks and Job values remain retained execution witnesses.',
                'This review reran no CLI, tests, game reads, PE/decoder accesses or original action.',
                'User already authorized read-only tests. New selected runtime scope still requires fresh environment evidence and a bounded internal root grant; no retry of this unchanged failed state.'],
        authority=dict(selected_effect_verified=False, original_request_correlated=False, AI_acceptance_verified=False,
            AI_rejection_verified=False, peace_completed=False, persistence_verified=False, native_ready=False,
            callable=False, world_lease=False, atomic_snapshot=False, authorizes_retry=False),
        resources=dict(selected_file_reads=TOTAL, prior_manual_allowance=1048576, bounded_upper=TOTAL + 1048576, maximum=16777216)))
    verification = save('verification.json', dict(sealed=True, passed=True, read_journal=READS,
        pins_before_after=len(selected) + 1, sourcebytes=TOTAL, root_review_script=pin(Path(__file__).read_bytes()),
        operations=dict(PE=0, decoder=0, CLI=0, tests=0, process_reads=0, native=0)))
    manifest = save('manifest.json', dict(schema='EU4-PEACE-FIRST-LIVE-INDEPENDENT-REVIEW-MANIFEST/1',
        sealed=True, passed=True, subject_capture_pin=CAPTURE_PIN, subject_final_manifest_pin=MANIFEST_PIN,
        files={str((OUT / n).relative_to(ROOT)).replace('\\', '/'): p for n, p in [('findings.json', findings), ('raw-replay.json', replay), ('verification.json', verification)]},
        captured_source_pins=selected, subject_manifest=MANIFEST_PIN))
    print(json.dumps(dict(passed=True, retained_status='unknown', findings=findings, manifest=manifest,
        pins=len(selected) + 1, sourcebytes=TOTAL), ensure_ascii=True))


if __name__ == '__main__':
    main()
