"""Isolated fake-byte-reader/MSVC validation. Never opens a game process."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
JOB_HELPER = ROOT / 'work/candidates/v21-core-pair-nosend-r2-1375/validate.py'
SOURCE_NAMES = ('cancel_reader.h', 'cancel_reader.cpp', 'test_cancel_reader.cpp', 'test_reader_budget.cpp',
                'build_test.cmd', 'validate.py')


def read(path):
    with Path(path).open('rb') as f:
        data = f.read(4 * 1024 * 1024 + 1)
    assert len(data) <= 4 * 1024 * 1024, path
    return data


def desc(path):
    data = read(path)
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def seal(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode('ascii')
    with Path(path).open('xb') as f:
        f.write(raw)
    return hashlib.sha256(raw).hexdigest()


def tracked():
    result = {str((HERE / n).relative_to(ROOT)).replace('\\', '/'): desc(HERE / n)
              for n in SOURCE_NAMES}
    if (HERE / 'source-index.json').exists():
        for name, expected in json.loads(read(HERE / 'source-index.json')).items():
            actual = desc(HERE / name)
            assert actual == expected, name
            result[str((HERE / name).relative_to(ROOT)).replace('\\', '/')] = actual
        result[str((HERE / 'source-index.json').relative_to(ROOT)).replace('\\', '/')] = desc(HERE / 'source-index.json')
    if (HERE / 'input-pins.json').exists():
        pins = json.loads(read(HERE / 'input-pins.json'))
        for path, expected in pins['files'].items():
            actual = desc(ROOT / path)
            assert actual == expected, path
            result[path] = actual
    else:
        for name in ('pair_component.h', 'pair_component.cpp', 'test_pair_component.cpp', 'validate.py'):
            path = JOB_HELPER.parent / name
            result[str(path.relative_to(ROOT)).replace('\\', '/')] = desc(path)
    return result


def main():
    assert len(sys.argv) == 2
    label = sys.argv[1]
    assert label.isascii() and label.replace('-', '').isalnum()
    out = HERE / label
    out.mkdir(exist_ok=False)
    before = tracked()
    pre = out / 'sources-before'
    pre.mkdir()
    for name in SOURCE_NAMES:
        with (pre / name).open('xb') as f:
            f.write(read(HERE / name))
    spec = importlib.util.spec_from_file_location('sealed_pair_job_helper', JOB_HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.HERE = HERE
    helper.ROOT = ROOT
    result = helper.run_build(out)
    after = tracked()
    artifacts = {str(p.relative_to(out)).replace('\\', '/'): desc(p)
                 for p in sorted((out / 'build').iterdir()) if p.is_file()}
    artifacts['build-command.stdout'] = desc(out / 'build-command.stdout')
    output = read(out / 'build/test.stdout').decode('utf-8') if (out / 'build/test.stdout').exists() else ''
    budget_output = read(out / 'build/budget.stdout').decode('utf-8') if (out / 'build/budget.stdout').exists() else ''
    passed = result['exit_code'] == 0 and before == after
    record = {'schema_version': 1, 'passed': passed, 'build': result,
              'inputs_before': before, 'inputs_after': after, 'inputs_unchanged': before == after,
              'artifacts': artifacts, 'test_stdout': output, 'budget_stdout': budget_output,
              'native_calls': 0, 'game_process_accessed': False, 'DLL_built': False,
              'new_decode_bytes': 0, 'all_shells_collected': result['all_children_collected']}
    sha = seal(out / 'validation.json', record)
    print(json.dumps({'passed': passed, 'validation_sha256': sha, 'build': result, 'test_stdout': output, 'budget_stdout': budget_output}))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
