"""Create v16 capture helpers from frozen v15 bytes; no import, game, or publication."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'work/run_lab_step_v15_1375.py': 'ded83df9a1df2c9de85d38450daad5a81652646a4fc52727a1079906b1d91387',
    'work/probe_preflight_v15_1375.py': 'c1d0698064f5da14446d98e312542dfa92ebc1ae59ba45769a1013d7acd0bdfc',
}


def main():
    outputs = []
    for name, pin in SOURCES.items():
        with (ROOT / name).open('rb') as f:
            raw = f.read(32769)
        if len(raw) > 32768 or hashlib.sha256(raw).hexdigest() != pin:
            raise ValueError('Frozen helper changed or budget exceeded')
        text = raw.decode('utf-8')
        if 'v15' not in text or 'v16' in text:
            raise ValueError('Unexpected source version')
        target = ROOT / name.replace('v15', 'v16')
        if target.exists():
            raise ValueError('Never overwrite versioned helper')
        updated = text.replace('v15', 'v16').encode('utf-8')
        compile(updated, str(target), 'exec')
        outputs.append((target, updated))
    for target, raw in outputs:
        with target.open('xb') as f:
            f.write(raw)
        print(target.relative_to(ROOT).as_posix(), hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    main()
