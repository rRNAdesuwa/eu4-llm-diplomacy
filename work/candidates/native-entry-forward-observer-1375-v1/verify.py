"""Seal the accepted exact source/attempt04 once; checks never build or run it."""
import argparse
import hashlib
import json
from pathlib import Path
from check_prepared import check as prepared

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
READY = ROOT/'work/reports/native-entry-forward-observer-review-20261015-r1/independent-source-ready.json'
READY_PIN = dict(bytes=4950, sha256='13ffca14e1a5ace7b99e38ad33746a0314ef813be7cb4f70ffa7ae5b9ab4e170')


def pin(path):
    data = path.read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def write_new(name, value):
    with (HERE/name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def checked():
    replay = prepared()
    assert pin(READY) == READY_PIN
    review = json.loads(READY.read_bytes())
    assert review['status'] == 'ready_for_offline_candidate_seal_at_reviewed_pins'
    assert review['adopted_build_attempt'] == '04' and not review['findings']
    for name, expected in review['source_pins'].items():
        assert pin(HERE/name) == expected, name
    return replay


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--seal', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = checked()
    if args.seal:
        with (HERE/'independent-source-ready.json').open('xb') as stream:
            stream.write(READY.read_bytes())
        files = [dict(path=path.relative_to(HERE).as_posix(), **pin(path))
            for path in sorted(HERE.rglob('*')) if path.is_file() and '__pycache__' not in path.parts
            and path.name not in ('manifest.json', 'verification.json')]
        write_new('manifest.json', dict(schema='EU4-NATIVE-ENTRY-FORWARD-OFFLINE-MANIFEST/1',
            files=files, adopted_attempt='04', independent_review=dict(path=str(READY), **READY_PIN),
            historical_environment_hashes='historical only; redaction mapping is mandatory',
            native_ready=False, game_provenance_authenticated=False))
        write_new('verification.json', dict(schema='EU4-NATIVE-ENTRY-FORWARD-OFFLINE-VERIFICATION/1',
            passed=True, manifest_pin=pin(HERE/'manifest.json'), independent_review_pin=READY_PIN,
            stored_cases=14, stored_checks=157, compile_reexecuted=False, tests_reexecuted=False,
            game_accessed=False, native_ready=False, all_direct_Popen_children_collected=True,
            entire_child_tree_cleanup_or_peak_proven=False, shell_sessions_remaining=0))
    manifest = json.loads((HERE/'manifest.json').read_bytes())
    for row in manifest['files']:
        assert pin(HERE/row['path']) == {key: row[key] for key in ('bytes', 'sha256')}, row['path']
    verified = json.loads((HERE/'verification.json').read_bytes())
    assert verified['manifest_pin'] == pin(HERE/'manifest.json') and pin(HERE/'independent-source-ready.json') == READY_PIN
    print(json.dumps(dict(passed=True, sealed=True, stored_cases=result['stored_cases'], stored_checks=result['stored_checks'],
        manifest_sha256=pin(HERE/'manifest.json')['sha256'], verification_sha256=pin(HERE/'verification.json')['sha256'],
        tests_reexecuted=False, compile_reexecuted=False, native_ready=False, game_accessed=False,
        shell_sessions_remaining=0)))


if __name__ == '__main__':
    main()
