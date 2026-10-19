"""Create a new curry-only sender; old successful actions are rejected on wire.

Reuses the V25 corrected ownership/transport implementation without editing it.
This generator performs no game access or request publication.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'work/candidates/v25-pair-send-bootstrap-1375'
HERE = ROOT / 'work/candidates/v26-gap-curry-bootstrap-1375'

def desc(p):
    data = p.read_bytes()
    assert len(data) <= 4 * 1024 * 1024
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

index = json.loads((OLD / 'source-index.json').read_bytes())
assert all(desc(OLD / n) == pin for n, pin in index.items())
HERE.mkdir(exist_ok=False)
pins = json.loads((OLD / 'input-pins.json').read_bytes())
for name, pin in index.items():
    pins[(OLD / name).relative_to(ROOT).as_posix()] = pin
    if name == 'input-pins.json':
        continue
    s = (OLD / name).read_text(encoding='ascii')
    s = s.replace('v25-pair-send-bootstrap', 'v26-gap-curry-bootstrap').replace('pair25', 'pair26').replace('_v25', '_v26').replace('V25', 'V26')
    if name == 'codec.h':
        s = s.replace('a>=Names.size()', 'a>=Names.size()||a!=10')
    elif name == 'test_codec.cpp':
        s = s.replace('assert(length>0&&length<=1024);pair26::Packet out{};',
                      'if(action!=10){assert(length<0);++groups;continue;} assert(length>0&&length<=1024);pair26::Packet out{};')
        s = s.replace('guarantee', 'curry_favors')
    elif name == 'README.md':
        s = 'V26 gap sender. Only curry_favors (token 3acc, family 5) is accepted by the canonical wire renderer/parser. No previously successful action can be published. Existing corrected V25 native port and ownership implementation is reused unchanged. Gameplay effects are not inferred from dispatch.\n'
    (HERE / name).write_text(s, encoding='ascii')
pins[__file__ and Path(__file__).relative_to(ROOT).as_posix()] = desc(Path(__file__))
(HERE / 'input-pins.json').write_text(json.dumps(pins, indent=2, sort_keys=True) + '\n', encoding='ascii')
print(json.dumps({'candidate': str(HERE), 'allowed_actions': ['curry_favors'], 'game_accessed': False}))
