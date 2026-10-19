"""Bounded live search for range/institution prerequisites without fixtures.

Uses existing decoded helper projections; does not call a native predicate or
infer full eligibility. A current-state nonce is never an installation session.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_effect_observer import RuntimeCapture, BudgetReader, HeldRPMPort, roots, country, full_handle
from bridge.tag_command_backend import TagCommandBackend, digest, read, require
from work import probe_knowledge_context_r3_1375 as context
from work import probe_knowledge_range_override_r3_1375 as override

PAIRS = (('MOS', 'KAZ'), ('MOS', 'GOL'), ('NOV', 'KAZ'), ('TIM', 'SHY'),
         ('TIM', 'BAL'), ('MNG', 'KHA'))


class Port:
    def __init__(self, budget):
        self.budget = budget

    def read(self, address, size):
        return self.budget.read(address, size)

    def qword(self, address):
        return self.budget.q(address)

    def integer(self, address):
        return self.budget.i(address)

    def byte(self, address):
        return self.budget.b(address)


def sample(r, base, image_size, selected, expected_roots):
    p = Port(r)
    root = roots(r, base)
    require(root == expected_roots and root['manual_pause'] == 1, 'Paused roots changed')
    registry = context.registry_snapshot(p, base)
    ids = [x['id_raw_10'] for x in registry['entries']]
    countries = {}
    for tag, old in selected.items():
        current = country(r, base, root, int(old['handle'], 16), tag)
        require(current == old, 'Selected full country identity changed')
        address = int(current['address'], 16)
        countries[tag] = dict(country=current,
            existence_province_count_raw_1344=r.i(address+0x1344),
            accepted=context.indexed_values(p, address, 0xc68, ids),
            sharing_counts=dict(signed_count_17dc=r.i(address+0x17dc), signed_count_17c4=r.i(address+0x17c4)))
    direct = dict(flag_233ff2c=r.b(base+0x233ff2c), flag_233fed6=r.b(base+0x233fed6))
    rows = []
    for provider, recipient in PAIRS:
        if provider not in selected or recipient not in selected:
            rows.append(dict(provider=provider, recipient=recipient, status='unknown', reason='Selected TAG unavailable'))
            continue
        a, b = selected[provider], selected[recipient]
        distance = context.distance_snapshot(p, a, b)
        native_range = context.provider_range_snapshot(p, base, a, image_size)
        projected = native_range['range_milli_projected']
        dynamic = int(native_range['dynamic_override_pointer_2da0'], 16)
        identity_branch = direct['flag_233ff2c'] != 0 and direct['flag_233fed6'] == 0
        override_code_verified = False
        if dynamic:
            vt = r.q(dynamic)
            require(vt == base+override.VT_RVA
                and r.read(vt, 16) == struct.pack('<QQ', base+0x8f48e0, base+override.SLOT_RVA),
                'Typed range override differs')
            require(digest(r.read(base+override.SLOT_RVA, override.CODE_BYTES)) == override.CODE_SHA,
                'Loaded range override bytes differ')
            override_code_verified = True
            if identity_branch and native_range['modifier_raw'] is not None:
                projected = context.range_arithmetic(native_range['base_range_raw_tech_50'], native_range['modifier_raw'])
        institutions = []
        for index in ids:
            key = str(index)
            pv = countries[provider]['accepted']['values_by_native_id'][key]
            rv = countries[recipient]['accepted']['values_by_native_id'][key]
            institutions.append(dict(native_id=index, provider_accepted_raw=pv,
                recipient_accepted_raw=rv, provider_nonzero_recipient_zero=pv != 0 and rv == 0))
        counts = [countries[x]['sharing_counts'] for x in (provider, recipient)]
        rows.append(dict(provider=provider, recipient=recipient,
            provider_handle=a['handle'], recipient_handle=b['handle'],
            distance=distance, native_range=native_range,
            direct_override_identity_branch=identity_branch,
            typed_override_loaded_code_verified=override_code_verified,
            range_raw_projected=projected,
            selected_distance_le_range=(distance['distance_milli'] <= projected)
                if distance['distance_milli'] is not None and projected is not None else None,
            institution_fields=institutions,
            sharing_counts_all_zero=all(x['signed_count_17dc'] == x['signed_count_17c4'] == 0 for x in counts),
            both_existence_counts_positive=all(countries[x]['existence_province_count_raw_1344'] > 0
                for x in (provider, recipient)),
            recipient_capital_area_and_progress_evaluated=False, pair_war_evaluated=False,
            full_native_legality_verified=False, dispatch_authorized=False))
    require(roots(r, base) == root and r.b(base+0x233ff2c) == direct['flag_233ff2c']
        and r.b(base+0x233fed6) == direct['flag_233fed6'], 'Range roots/gates changed')
    return dict(roots=root, registry=registry, countries=countries, direct_gates=direct, pairs=rows)


def main():
    destination = ROOT/'work/reports/knowledge-nearby-candidates-20261015/live-selected-pairs.json'
    require(not destination.exists(), 'Exclusive live output required')
    backend = TagCommandBackend()
    identity = dict(pid=80340, creation='01dd5c075fcf8c26', session=secrets.token_hex(16),
        dll_sha256=backend.manifest['dll']['sha256'], manifest_sha256=backend.manifest_sha)
    sources = override.source_pins()
    own = read(Path(__file__), 65536)
    sources[Path(__file__).relative_to(ROOT).as_posix()] = dict(bytes=len(own), sha256=digest(own))
    with RuntimeCapture(identity, backend) as cap:
        require(not any(Path(p).name.lower().startswith(('eu4_bridge_', 'eu4_pair_', 'eu4_spy_',
            'eu4_tag_command_', 'tag_diplomacy')) for _, p in cap.modules), 'Unexpected research module')
        r = BudgetReader(HeldRPMPort(cap.held))
        root = roots(r, cap.base)
        image_size = cap.runtime.readonly.pe_header(r.read(cap.base, 8192))['size_of_image']
        tags = {x for pair in PAIRS for x in pair}
        selected = {}
        for address, in struct.iter_unpack('<Q', r.read(int(root['array'], 16), root['count']*8)):
            if not address:
                continue
            handle = r.q(address+0x20)
            tag = (handle & 0xffffff).to_bytes(3, 'little').decode('ascii', errors='replace')
            if tag in tags:
                require(tag not in selected, 'Duplicate selected TAG')
                full_handle(handle, root['count'], tag=tag)
                selected[tag] = country(r, cap.base, root, handle, tag)
        first = sample(r, cap.base, image_size, selected, root)
        second = sample(r, cap.base, image_size, selected, root)
        require(first == second, 'Selected precondition passes differ')
        cap.held.identity_check()
        require(cap.held.modules() == cap.modules, 'Modules changed during capture')
        require(override.source_pins() == {k: v for k, v in sources.items()
            if k != Path(__file__).relative_to(ROOT).as_posix()}, 'Helper sources changed')
        result = dict(schema='EU4-NEARBY-KNOWLEDGE-PREREQUISITES/1', identity=identity,
            identity_purpose='Read-only nonce, not a TAG installation or request',
            captured_utc=datetime.now(timezone.utc).isoformat(), two_pass_equal=True,
            passes=[first, second], source_pins=sources,
            rpm_budget=dict(calls=r.calls, bytes=r.bytes, largest_read=r.largest),
            native_calls=0, memory_written=False, requests_published=0, saves_written=0, reloads=0,
            complete_legality_verified=False, automatic_command_retry=False)
    with destination.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(destination), rpm_budget=result['rpm_budget'],
        pairs=[dict(provider=x['provider'], recipient=x['recipient'],
            distance=x.get('distance', {}).get('distance_milli'), range=x.get('range_raw_projected'),
            range_allows=x.get('selected_distance_le_range'), counts_clear=x.get('sharing_counts_all_zero'),
            exists=x.get('both_existence_counts_positive'),
            institution_difference=any(v['provider_nonzero_recipient_zero'] for v in x.get('institution_fields', [])),
            full_legality=False) for x in first['pairs']])))


if __name__ == '__main__':
    main()
