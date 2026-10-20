"""Replay prepared source/output receipts; do not compile/run/sample or seal."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'work'))
from discover_diplomacy import check_memory_budget


def pin(path):
    raw = path.read_bytes()
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def load(path):
    return json.loads(path.read_bytes())


def check():
    provenance = load(HERE/'source-pins.json')
    for name, expected in provenance['inputs'].items():
        assert pin(ROOT/name) == expected, name
    assert provenance['new_disassembly_bytes'] == 0 and provenance['native_ready'] is False
    correction = HERE/'environment-redaction.json'
    assert pin(correction)['sha256'] == 'ed8026bca17f3fd592b043202c850dcb17c56dbc322a677e4d67f8d44adb76b3'
    redactions = {row['path']: row for row in load(correction)['rows']}
    assert set(redactions) == {'build-attempt-'+number+'/environment.stdout.txt' for number in ('01', '02', '03')}
    old_receipts = {'01': '604966caebd618b1c0bd8b892d94fbdea18b079c627e1ccfcb0eb141148d340c',
        '02': '6cf86d6dbd39477f6498875e8628c6d29b4ac22ca3744f4083bb29f04a538447',
        '03': 'fc423d30b3752a5e27023c0badfbf3df0fe5a32a806709621ad19979b08ec1df'}
    for number, expected in old_receipts.items():
        directory = HERE/('build-attempt-'+number)
        assert pin(directory/'receipt.json')['sha256'] == expected
        for name, original in load(directory/'receipt.json')['output_pins'].items():
            relative = 'build-attempt-'+number+'/'+name
            if relative in redactions:
                row = redactions[relative]
                assert row['original_pin'] == original
                assert pin(HERE/relative) == row['redacted_pin']
                assert set(load(HERE/relative)) == {'PATH', 'INCLUDE', 'LIB', 'LIBPATH'}
            else:
                assert pin(directory/name) == original, relative
    directory = HERE/'build-attempt-04'
    receipt_path = directory/'receipt.json'
    assert pin(receipt_path)['sha256'] == '2473fbf604ab009b97d898fc3f4dad30300cce179d37fb902e74ae43ec7d61ae'
    receipt = load(receipt_path)
    for name, expected in receipt['source_pins'].items():
        assert pin(HERE/name) == expected, name
    for name, expected in receipt['output_pins'].items():
        assert pin(directory/name) == expected, name
    assert receipt['passed'] and receipt['source_unchanged'] and receipt['all_children_collected']
    assert receipt['default_44_and_DLL_unchanged'] and receipt['sealed'] is False
    assert all(stage['exit_code'] == 0 and stage['error'] is None and stage['collected']
        and stage['peak_committed_bytes'] <= 768*1024*1024 for stage in receipt['stages'])
    environment = load(directory/'environment.stdout.txt')
    assert set(environment) == {'PATH', 'INCLUDE', 'LIB', 'LIBPATH'}
    result = load(directory/'run.stdout.txt')
    assert result == receipt['test_result'] and result['cases'] == 14 and result['checks'] == 157
    for name in ('native_ready', 'native_entry_authenticated', 'header_lifetime_lease', 'atomic_snapshot', 'game_accessed'):
        assert result[name] is False
    build = ROOT/'bridge/native/tag_diplomacy_1375_v31/build-7/build/build.json'
    data = load(build)
    assert len(data['source_pins']) == 44
    for name, expected in data['source_pins'].items():
        assert pin(ROOT/name) == expected, name
    assert pin(build.parent/data['DLL']) == data['dll']
    return dict(passed=True, prepared=True, sealed=False, stored_cases=14, stored_checks=157,
        tests_reexecuted=False, compile_reexecuted=False, adopted_attempt='04',
        redacted_historical_logs=3, old_environment_hashes_are_historical_only=True,
        default_44_and_DLL_unchanged=True, game_process_accessed=False, game_native_calls=0,
        native_ready=False, native_entry_authenticated=False, shell_sessions_remaining=0,
        peak_committed_bytes=check_memory_budget())


if __name__ == '__main__':
    print(json.dumps(check()))
