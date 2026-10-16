"""Compile only the actual owned-peace lifecycle module to a fresh object file.

No DLL/executable link, no game process access, no native function invocation.
Does not rerun the synthetic checker tests. All evidence output is exclusive.
"""
from __future__ import annotations
import datetime
import json
import uuid
from pathlib import Path
from verify_checker import HERE, ROOT, FLAGS, audit, compiler_environment, create_file, digest, json_bytes, run

def main():
    parent = HERE / 'validation-results'
    parent.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = parent / ('lifecycle-object-' + stamp + '-' + uuid.uuid4().hex)
    out.mkdir()
    create_file(out / 'claim.json', json_bytes({'created_utc': stamp, 'purpose': 'actual_lifecycle_object_only', 'retry': False}))
    report = {'schema': 'owned_peace_lifecycle_object_validation_v1', 'created_utc': stamp,
              'output_directory': out.relative_to(ROOT).as_posix(), 'passed': False,
              'compile_exit': None, 'link_performed': False, 'checker_tests_rerun': False,
              'dll_built': False, 'game_process_access': False, 'native_peace_called': False,
              'runtime_verified': False, 'execution_verified': False}
    try:
        inputs, static = audit(out)
        inputs.append({'path': Path(__file__).name, 'sha256': digest(Path(__file__))})
        report['inputs'] = inputs; report['static_audit'] = static
        compiler, env = compiler_environment(out)
        source = HERE / 'peace-owned-lifecycle-1375.cpp'
        obj = out / 'peace-owned-lifecycle-1375.obj'
        pdb = out / 'compiler.pdb'
        if obj.exists() or pdb.exists(): raise FileExistsError('Refuse existing compiler output')
        flags = [*FLAGS, '/c']
        result = run([compiler, *flags, str(source), '/Fo' + str(obj), '/Fd' + str(pdb)], out, env=env)
        create_file(out / 'compile.stdout.txt', result.stdout)
        create_file(out / 'compile.stderr.txt', result.stderr)
        report['compile_exit'] = result.returncode
        report['compiler'] = {'path': compiler, 'sha256': digest(Path(compiler)), 'flags': flags}
        includes = result.stdout.decode('mbcs', errors='replace').replace('/', '\\').lower()
        report['actual_headers_in_compiler_dependencies'] = {
            name: str(HERE / name).lower() in includes
            for name in ('peace-owned-lifecycle-1375.h', 'default-contract.h', 'pins.h')}
        report['compile_output'] = [{'path': p.name, 'sha256': digest(p), 'bytes': p.stat().st_size}
                                    for p in (out / 'compile.stdout.txt', out / 'compile.stderr.txt')]
        diagnostics = result.stdout.decode('mbcs', errors='replace') + result.stderr.decode('mbcs', errors='replace')
        report['diagnostics'] = [line for line in diagnostics.splitlines()
                                 if ' error ' in line.lower() or ' warning ' in line.lower()]
        if result.returncode == 0:
            if not all(report['actual_headers_in_compiler_dependencies'].values()):
                raise ValueError('Actual lifecycle headers missing from compiler dependency output')
            if not obj.is_file(): raise ValueError('Compiler returned success without object')
            if any(out.glob('*.exe')) or any(out.glob('*.dll')): raise ValueError('Unexpected linked artifact')
            if any(digest(HERE / source['path']) != source['sha256'] for source in inputs):
                raise ValueError('Candidate changed during object compilation')
            report['object'] = {'path': obj.name, 'sha256': digest(obj), 'bytes': obj.stat().st_size}
            report['passed'] = True
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    create_file(out / 'validation.json', json_bytes(report))
    print(json.dumps({'path': str(out / 'validation.json'), 'sha256': digest(out / 'validation.json'),
                      'passed': report['passed'], 'compile_exit': report['compile_exit'],
                      'diagnostics': report.get('diagnostics'), 'object': report.get('object'),
                      'error': report.get('error')}))
    return 0 if report['passed'] else 1

if __name__ == '__main__': raise SystemExit(main())
