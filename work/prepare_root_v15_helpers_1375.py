"""Create new root capture helpers from the fixed reviewed v14 helpers, no game access."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    sources = (
        ('work/run_lab_step_v14_1375.py', 'work/run_lab_step_v15_1375.py'),
        ('work/probe_preflight_v14_1375.py', 'work/probe_preflight_v15_1375.py'),
    )
    pins = {
        'work/run_lab_step_v14_1375.py': 'c64aac8c3115ffe441ff791621bd6ddc837736d41d4d18d1d415da5868c05290',
        'work/probe_preflight_v14_1375.py': 'f66613f32b37217fe81446e4c6d65de0a7683c234d6763f5551d50ea2685392b',
    }
    outputs = []
    for source, target in sources:
        raw = (ROOT / source).read_bytes()
        if len(raw) > 32768:
            raise ValueError('Helper read budget')
        if hashlib.sha256(raw).hexdigest() != pins[source]:
            raise ValueError('Frozen predecessor helper changed')
        # The only change is the new protocol/module/output version; no publication added.
        text = raw.decode('utf-8')
        if 'v14' not in text or 'v15' in text:
            raise ValueError('Unexpected predecessor version')
        updated = text.replace('v14', 'v15').encode('utf-8')
        compile(updated, target, 'exec')
        if (ROOT / target).exists():
            raise ValueError('Never overwrite a versioned helper')
        outputs.append((ROOT / target, updated))
    for target, raw in outputs:
        with target.open('xb') as stream:
            stream.write(raw)
        print(target.relative_to(ROOT).as_posix(), hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    main()
