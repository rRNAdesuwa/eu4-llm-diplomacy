"""CreateNew root validator adaptation; never materialize or compile native code."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    old = ROOT / 'work/validate_v16_candidate_root_1375.py'
    with old.open('rb') as stream:
        raw = stream.read(8193)
    assert len(raw) <= 8192 and hashlib.sha256(raw).hexdigest() == 'f3b8f09343d5743cec0c08b479eaf920355bc9fb58bc2f2dc7f6406535909811'
    text = raw.decode().replace('v16', 'v17').replace('V16', 'V17')
    text = text.replace('v17-acceptance-initialization-review', 'v17-acceptance-pin-review')
    text = text.replace('bfc1654624ad7ed054bf640f9445f566c73ce9e53f32041d8fbc687c4c680929',
                        'ad9d5d2c368e8358cf5e3e6b156f5ccb2b399a7c1c33f989a9e79db0e6d7fd7a')
    target = ROOT / 'work/validate_v17_candidate_root_1375.py'
    compile(text, str(target), 'exec')
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    print(hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
