"""CreateNew version-only capture and RO helpers; no native build or process."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED = {
    'work/run_lab_step_v16_1375.py': '88f937741d7f0c7e7a7faf87c15a426227f4a41f958851e36839a0b5c36d1dbe',
    'work/probe_preflight_v16_1375.py': '6bc4c70f1b994de3ac53feaee132e9feddfc59e544bbefedbee8d3710eb7d1fb',
}


def main():
    pairs, pins = [], {}
    for name, expected in PINNED.items():
        path = ROOT / name
        with path.open('rb') as stream:
            raw = stream.read(8193)
        assert len(raw) <= 8192 and hashlib.sha256(raw).hexdigest() == expected
        target = ROOT / name.replace('v16', 'v17')
        assert not target.exists()
        result = raw.decode().replace('v16', 'v17').replace('V16', 'V17').encode()
        compile(result, str(target), 'exec')
        pairs.append((target, result))
        pins[name] = dict(input_sha256=expected, output_path=target.relative_to(ROOT).as_posix(),
                          output_sha256=hashlib.sha256(result).hexdigest())
    for target, result in pairs:
        with target.open('xb') as stream:
            stream.write(result)
    report = ROOT / 'work/review-results/root-v17-helper-adaptation-20261008a.json'
    with report.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(dict(purpose='root_v17_version_only_helpers', inputs=pins,
                       all_syntax_valid=True, process_accessed=False, native_built=False), stream, indent=2)
        stream.write('\n')
    print(json.dumps(pins))


if __name__ == '__main__':
    main()
