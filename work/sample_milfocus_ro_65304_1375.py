"""Explicit held-process RO sample on the paused 65304 baseline."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'work/candidates/subject-military-focus-observer-1375'
OUTPUT = ROOT / 'work/runtime/subject-military-focus-ro-65304.json'
PID = 65304
CREATION = '01dd56d71677eb60'
WORLD = 0x2691a70c040
DATE = 56456976
PINS = {
    'work/candidates/subject-military-focus-observer-1375/review.json':
        '14854bb58611a6b5842d086ee1059c41d6ca7ff5d967a277473d3f020607a2c5',
    'work/candidates/subject-military-focus-observer-1375/observer.py':
        'd03c53ddae7735d4ee2b521dd878fb5bc9045a509a9b56d80ae48f0597367edc',
    'work/review-results/subject-military-focus-observer-action-catalog-20261008a/review.json':
        'fa5775e30715b6c0a62b6b1d5669c0bd918befc6438c53e35b816e8bcabf3349',
}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(65536):
            digest.update(block)
    return digest.hexdigest()


def main():
    for key, expected in PINS.items():
        if sha(ROOT / key) != expected:
            raise ValueError('Reviewed source changed: ' + key)
    with OUTPUT.open('xb') as stream:
        record = dict(schema_version=1, kind='explicit_subject_military_focus_ro_attempt',
                      pid=PID, creation=CREATION, world_cookie=hex(WORLD), raw_date=DATE,
                      actor='FRA', target='NAV', source_pins=PINS,
                      game_native_calls=False, individual_effect_verified=False,
                      production_ready=False, window_pause_observed=True,
                      paused_native_verified=False)
        try:
            spec = importlib.util.spec_from_file_location('_root_milfocus_ro_65304', HERE / 'observer.py')
            observer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(observer)
            result = observer.sample_process(pid=PID, creation=CREATION, executable=ROOT.parent / 'eu4.exe')
            identity = result['snapshot']['identity']
            if identity['game'] != WORLD or identity['date'] != DATE:
                raise ValueError('Explicit baseline world/date changed')
            record.update(status='captured', report=result)
        except Exception as error:
            record.update(status='unsupported_or_read_failed', error_type=type(error).__name__, error=str(error))
        stream.write((json.dumps(record, sort_keys=True, indent=2) + '\n').encode())
    print(json.dumps(dict(output=OUTPUT.relative_to(ROOT).as_posix(), status=record['status'],
                          error=record.get('error'), sha256=sha(OUTPUT), native_calls=False)))
    return 0 if record['status'] == 'captured' else 1


if __name__ == '__main__':
    raise SystemExit(main())
