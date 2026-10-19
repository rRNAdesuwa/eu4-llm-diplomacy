"""One new pure-data CLI adapter suite in the previously reviewed bounded Job."""
import hashlib
import json
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / 'offline-r1'
JOB = ROOT / 'work/candidates/frida-entry-observer-1375-v1/job_tree.py'
JOB_SHA = '5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(name, value):
    with (OUT/name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def main():
    assert not OUT.exists(), 'One-shot offline receipt already exists'
    raw = JOB.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == JOB_SHA
    helper = types.ModuleType('_direct_truce_offline_job')
    helper.__file__ = str(JOB)
    exec(compile(raw, str(JOB), 'exec'), helper.__dict__)
    sources = {name: pin(HERE/name) for name in ('direct_truce_cache.py', 'test_direct_truce_cache.py',
                                                'README.md', 'run_offline.py', 'source-manifest.json')}
    dependencies = {name: pin(ROOT/name) for name in ('work/capture_direct_truce_flags_20261015.py',
        'bridge/diplomacy_effect_observer.py', 'work/candidates/frida-entry-observer-1375-v1/job_tree.py')}
    OUT.mkdir()
    save('claim.json', {'source_pins': sources, 'dependencies': dependencies, 'old_tests_to_run': 0,
                        'actual_process_capture_authorized': False})
    job = helper.run_cli_tree([sys.executable, '-B', str(HERE/'test_direct_truce_cache.py')], ROOT,
        OUT/'stdout.txt', OUT/'stderr.txt', timeout_seconds=30, memory_limit=768*1024*1024)
    error = (OUT/'stderr.txt').read_text(encoding='utf-8')
    unchanged = all(pin(HERE/name) == value for name, value in sources.items())
    unchanged = unchanged and all(pin(ROOT/name) == value for name, value in dependencies.items())
    passed = (job.get('error') is None and job.get('exit_code') == 0
              and job.get('job_active_processes_final') == 0 and job.get('direct_child_collected') is True
              and 1 <= job.get('job_total_processes', 0) <= 8 and unchanged
              and 'Ran 12 tests' in error and error.rstrip().endswith('OK'))
    receipt = dict(schema='EU4-DIRECT-TRUCE-CACHE-CLI-OFFLINE/1', status='passed' if passed else 'failed',
        new_test_methods=12, source_unchanged=unchanged, source_pins=sources, dependencies=dependencies,
        stdout=pin(OUT/'stdout.txt'), stderr=pin(OUT/'stderr.txt'), job=job,
        actual_game_accesses=0, EXE_reads=0, REA_operations=0, Frida_operations=0, native_game_calls=0,
        requests_published=0, old_tests_run=0, native_ready=False, source_sealed=False)
    save('receipt.json', receipt)
    print(json.dumps({'status': receipt['status'], 'receipt': pin(OUT/'receipt.json'), 'job': job}, indent=2))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
