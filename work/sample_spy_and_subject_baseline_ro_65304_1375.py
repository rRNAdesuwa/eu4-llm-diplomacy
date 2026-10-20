"""One fixed grouped RO baseline capture; never calls or writes game code."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'work/runtime/spy-dense-and-subject-baseline-ro-65304.json'
PID = 65304
CREATION = '01dd56d71677eb60'
WORLD = 0x2691a70c040
DATE = 56456976
FAMILIES = ('corrupt_officials', 'sabotage_reputation', 'sow_discontent',
            'slander_merchants', 'sabotage_recruitment')
PINS = {
    'work/candidates/spy-dense-full-observer-r2-1375/review.json':
        '589edf5304828d2de0854e261f03eef5f3f0f7dc52c22a6b5dd6e3b279b2f031',
    'work/candidates/spy-dense-full-observer-r2-1375/observer.py':
        'f25dace36f14f3ea01928f90c3817e715140b373723a3aa9843a280e01b5bd66',
    'work/review-results/spy-dense-full-r2-native-inventory-20261008a/review.json':
        'cdd7901f47871b7cfd12ae1cf0d605d0fb0ef660873045e8449ac279d207b26c',
    'work/candidates/subject-toggle-observer-1375/review.json':
        'ca3e29f41f1c663f7a0c748fbbd3e8d9ffdb3453ef435e9268dc87f6c26af72f',
    'work/candidates/subject-toggle-observer-1375/observer.py':
        '2757fdb158399908331c13972c4892ea55b48dbcfa4fa37ec6714f977be5ad90',
    'work/review-results/subject-toggle-observer-root-20261008a/review-r2.json':
        '703f73c6b9469ae49b63186dae759d3141466c0ae199d8f412ec0c6205f2c2fa',
}


def sha(path):
    d = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(65536):
            d.update(block)
    return d.hexdigest()


def verified():
    for name, digest in PINS.items():
        if sha(ROOT / name) != digest:
            raise ValueError('Reviewed source changed: ' + name)


def module(name, directory):
    path = ROOT / 'work/candidates' / directory / 'observer.py'
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    if Path(loaded.__file__).resolve() != path.resolve():
        raise ValueError('Import provenance')
    return loaded


def same_baseline(identity):
    if identity['game'] != WORLD or identity['date'] != DATE:
        raise ValueError('Fixed baseline world/date changed')


def main():
    verified()
    # Reserve the one-shot evidence path before any OS/process read.
    with OUTPUT.open('xb') as stream:
        record = dict(kind='grouped_spy_dense_and_subject_ro_baseline', schema_version=1,
                      pid=PID, creation=CREATION, world_cookie=hex(WORLD), raw_date=DATE,
                      source_pins=PINS, spy_reports={}, subject_report=None,
                      group_atomic=False, game_native_calls=False, game_memory_written=False,
                      requests_sent=0, individual_effect_verified=False, production_ready=False,
                      paused_native_verified=False)
        try:
            spy = module('_root_grouped_dense_r2', 'spy-dense-full-observer-r2-1375')
            subject = module('_root_grouped_subject', 'subject-toggle-observer-1375')
            for family in FAMILIES:
                result = spy.sample_process(pid=PID, creation=CREATION, executable=ROOT.parent / 'eu4.exe', family=family)
                same_baseline(result['before']['snapshot']['identity'])
                same_baseline(result['after']['snapshot']['identity'])
                record['spy_reports'][family] = result
            result = subject.sample_process(pid=PID, creation=CREATION, executable=ROOT.parent / 'eu4.exe')
            subject.validated_report(result)
            same_baseline(result['snapshot']['graph']['identity'])
            record['subject_report'] = result
            verified()
            record['status'] = 'captured'
        except Exception as error:
            record.update(status='unsupported_or_read_failed', error_type=type(error).__name__, error=str(error))
        stream.write((json.dumps(record, sort_keys=True, indent=2) + '\n').encode())
    summary = dict(status=record['status'], output=OUTPUT.relative_to(ROOT).as_posix(),
                   sha256=sha(OUTPUT), bytes=OUTPUT.stat().st_size,
                   families_captured=len(record['spy_reports']), error=record.get('error'),
                   native_calls=False, requests_sent=0)
    if record['status'] == 'captured':
        summary['spy'] = {name: dict(cost_status=x['dense']['before']['status'],
                                    candidate_milli=x['dense']['final_milli_candidate'],
                                    raw_modifier=x['dense']['before']['aggregate'].get('selected_record'),
                                    capability_raw=x['before']['snapshot']['capability']['raw'],
                                    network=x['before']['snapshot']['cost']['network_centipoints'])
                          for name, x in record['spy_reports'].items()}
        summary['subject_scope'] = record['subject_report']['snapshot']['graph']['scope_status']
    print(json.dumps(summary, sort_keys=True))
    return 0 if record['status'] == 'captured' else 1


if __name__ == '__main__':
    raise SystemExit(main())
