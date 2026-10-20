"""Current indexed relations, including symmetric and directional controls."""
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_effect_observer import RuntimeCapture, BudgetReader, HeldRPMPort, roots, country, full_handle, pins
from bridge.relation_effect_reader import read_relation_pair, verify_manifest
from bridge.tag_command_backend import TagCommandBackend, digest, require

CASES = (('offer_alliance', 'FRA', 'POR'), ('offer_alliance', 'POR', 'FRA'),
    ('royal_marriage', 'ORL', 'BRI'), ('guarantee', 'FRA', 'SAV'),
    ('guarantee', 'SAV', 'FRA'), ('offer_alliance', 'FRA', 'ENG'))


def main():
    destination = ROOT/'work/reports/relation-effect-observer-20261015/live-80340-current-relations.json'
    require(not destination.exists(), 'Exclusive live output required')
    backend = TagCommandBackend()
    identity = dict(pid=80340, creation='01dd5c075fcf8c26', session=secrets.token_hex(16),
        dll_sha256=backend.manifest['dll']['sha256'], manifest_sha256=backend.manifest_sha)
    initial = verify_manifest()
    captures = []
    with RuntimeCapture(identity, backend) as cap:
        require(not any(Path(p).name.lower().startswith(('eu4_bridge_', 'eu4_pair_', 'eu4_spy_',
            'eu4_tag_command_', 'tag_diplomacy')) for _, p in cap.modules), 'Unexpected research module')
        r = BudgetReader(HeldRPMPort(cap.held))
        root = roots(r, cap.base)
        require(root['manual_pause'] == 1, 'Paused checkpoint required')
        tags = {name for _, a, b in CASES for name in (a, b)}
        selected = {}
        for address, in struct.iter_unpack('<Q', r.read(int(root['array'], 16), root['count']*8)):
            if not address:
                continue
            handle = r.q(address+0x20)
            tag = (handle & 0xffffff).to_bytes(3, 'little').decode('ascii', errors='replace')
            if tag in tags:
                require(tag not in selected, 'Duplicate selected country tag')
                full_handle(handle, root['count'], tag=tag)
                selected[tag] = country(r, cap.base, root, handle, tag)
        require(set(selected) == tags, 'Selected country unavailable')
        for action, a, b in CASES:
            started = time.perf_counter()
            value = read_relation_pair(r, cap.base, action, int(selected[a]['handle'], 16),
                int(selected[b]['handle'], 16), identity)
            captures.append(dict(action=action, actor=a, target=b, state=value,
                duration_ms=round((time.perf_counter()-started)*1000, 3)))
        require(roots(r, cap.base) == root, 'Capture roots changed')
        cap.held.identity_check()
        require(cap.held.modules() == cap.modules and pins() == cap.initial_pins,
            'Modules or frozen R1 sources changed')
        require(verify_manifest() == initial, 'Relation reader sources changed')
    result = dict(schema='EU4-RELATION-CURRENT-LIVE-ACCEPTANCE/1',
        captured_utc=datetime.now(timezone.utc).isoformat(), identity=identity,
        identity_purpose='Read-only nonce, not a TAG installation or request',
        source_pins=initial, captures=captures,
        rpm_budget=dict(calls=r.calls, bytes=r.bytes, largest_read=r.largest),
        native_calls=0, memory_written=False, requests_published=0, saves_written=0, reloads=0,
        new_API_effect_tested=False, global_membership_verified=False,
        exact_external_request_id_causality_verified=False,
        producer=dict(path=Path(__file__).relative_to(ROOT).as_posix(), sha256=digest(Path(__file__).read_bytes())))
    with destination.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(destination), sha256=digest(destination.read_bytes()),
        rpm_budget=result['rpm_budget'], captures=[dict(action=x['action'], actor=x['actor'], target=x['target'],
            status=x['state']['status'], two_pass_equal=x['state'].get('two_pass_equal'),
            duration_ms=x['duration_ms'], failure=x['state'].get('failure')) for x in captures])))


if __name__ == '__main__':
    main()
