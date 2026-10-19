"""Fixed-process initial/final selected census for the next manual UI batch."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PID = 38232
CREATION = '01dd56e0cbe2c7f7'
WORLD = 0x1a0cb39c020
DATE = 56456976
PINS = {
    'work/candidates/curry-favors-observer-1375/review.json': 'b384a68867c6ac29e9544ac484481c9ba5a806f6376d74ae638d62aaa292d49a',
    'work/candidates/curry-favors-observer-1375/observer.py': '1d960aee7de4daeb4afe1f53cef4f37ec6972b5b577252e026fd8c9e5e33c8f9',
    'work/review-results/curry-favors-observer-native-inventory-20261008a/review.json': '19270114928db54827eead8083e26a26b22345f6641e2424a6cb73efc0902561',
    'work/candidates/subject-military-focus-observer-1375/review.json': '14854bb58611a6b5842d086ee1059c41d6ca7ff5d967a277473d3f020607a2c5',
    'work/candidates/subject-military-focus-observer-1375/observer.py': 'd03c53ddae7735d4ee2b521dd878fb5bc9045a509a9b56d80ae48f0597367edc',
    'work/review-results/subject-military-focus-observer-action-catalog-20261008a/review.json': 'fa5775e30715b6c0a62b6b1d5669c0bd918befc6438c53e35b816e8bcabf3349',
    'work/candidates/subject-toggle-observer-1375/review.json': 'ca3e29f41f1c663f7a0c748fbbd3e8d9ffdb3453ef435e9268dc87f6c26af72f',
    'work/candidates/subject-toggle-observer-1375/observer.py': '2757fdb158399908331c13972c4892ea55b48dbcfa4fa37ec6714f977be5ad90',
    'work/review-results/subject-toggle-observer-root-20261008a/review-r2.json': '703f73c6b9469ae49b63186dae759d3141466c0ae199d8f412ec0c6205f2c2fa',
}
OBSERVERS = {
    'curry': 'curry-favors-observer-1375',
    'military_focus': 'subject-military-focus-observer-1375',
    'subject_toggles': 'subject-toggle-observer-1375',
}


def sha(path):
    d = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(65536):
            d.update(block)
    return d.hexdigest()


def verify():
    for path, digest in PINS.items():
        if sha(ROOT / path) != digest:
            raise ValueError('Reviewed source changed: ' + path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('before_ui', 'after_ui'), required=True)
    phase = parser.parse_args().phase
    verify()
    initial_path = ROOT / 'work/runtime/subject-and-curry-ui-batch-ro-38232-before_ui.json'
    initial_sha = None
    if phase == 'after_ui':
        if initial_path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('Initial budget')
        initial_sha = sha(initial_path)
        initial = json.loads(initial_path.read_text('utf-8'))
        if initial['status'] != 'captured' or initial['world'] != WORLD or initial['pid'] != PID or initial['creation'] != CREATION:
            raise ValueError('Same-process complete initial required')
    output = ROOT / ('work/runtime/subject-and-curry-ui-batch-ro-38232-' + phase + '.json')
    with output.open('xb') as stream:
        record = dict(kind='fixed_subject_and_curry_ui_selected_census', phase=phase,
                      pid=PID, creation=CREATION, world=WORLD, raw_date=DATE,
                      source_pins=PINS, capture_helper_sha256=sha(__file__), reports={},
                      group_atomic=False, game_native_calls=False, game_memory_written=False,
                      individual_effect_verified=False, production_ready=False,
                      native_request_receipt=False, initial_reference_sha256=initial_sha)
        try:
            for name, directory in OBSERVERS.items():
                path = ROOT / 'work/candidates' / directory / 'observer.py'
                spec = importlib.util.spec_from_file_location('_subject_curry_batch_' + name, path)
                observer = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(observer)
                if Path(observer.__file__).resolve() != path or observer.ROOT != ROOT:
                    raise ValueError('Observer provenance')
                result = observer.sample_process(pid=PID, creation=CREATION, executable=ROOT.parent / 'eu4.exe')
                identity = result['passes'][0]['identity'] if name == 'curry' else result['snapshot']['graph']['identity'] if name == 'subject_toggles' else result['snapshot']['identity']
                if identity['game'] != WORLD or identity['date'] != DATE:
                    raise ValueError('Fixed world/date changed: ' + name)
                record['reports'][name] = result
            verify()
            if initial_sha is not None and sha(initial_path) != initial_sha:
                raise ValueError('Initial changed during capture')
            record['status'] = 'captured'
        except Exception as error:
            record.update(status='unsupported_or_read_failed', error_type=type(error).__name__, error=str(error))
        stream.write((json.dumps(record, sort_keys=True, indent=2) + '\n').encode())
    print(json.dumps(dict(status=record['status'], phase=phase, error=record.get('error'),
                          sha256=sha(output), bytes=output.stat().st_size,
                          curry_state=record['reports'].get('curry', {}).get('state'),
                          capture_native_calls=False, individual_effect_verified=False)))
    return 0 if record['status'] == 'captured' else 1


if __name__ == '__main__':
    raise SystemExit(main())
