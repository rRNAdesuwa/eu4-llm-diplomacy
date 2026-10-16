"""Discover existing providers' current counterparts, then use strict decoder.

No historical task pointer is followed and no action is sent. Discovery reads
only current typed index keys; effect evaluation remains request-independent.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_effect_observer import BudgetReader, HeldRPMPort, roots, country
from bridge.diplomacy_live_observer import KnowledgeRuntimeCapture, checked_capture, live_source_pins
from bridge.knowledge_effect_reader_v2 import _index
from bridge.tag_command_backend import TagCommandBackend, digest, require


def main():
    directory = ROOT/'work/reports/diplomacy-live-observer-20261015-r1'
    destination = directory/'live-80340-existing-active-sharing.json'
    require(not destination.exists(), 'Exclusive current-state output required')
    source = json.loads((ROOT/'work/reports/knowledge-nearby-candidates-20261015/live-selected-pairs.json').read_bytes())
    backend = TagCommandBackend()
    identity = dict(pid=80340, creation='01dd5c075fcf8c26', session=secrets.token_hex(16),
        dll_sha256=backend.manifest['dll']['sha256'], manifest_sha256=backend.manifest_sha)
    initial = live_source_pins()
    discoveries, captures = [], []
    with KnowledgeRuntimeCapture(identity, backend) as cap:
        discovery_reader = BudgetReader(HeldRPMPort(cap.held))
        root = roots(discovery_reader, cap.base)
        require(root['manual_pause'] == 1, 'Expected paused checkpoint')
        for provider_tag in ('MOS', 'TIM', 'MNG'):
            previous = source['passes'][0]['countries'][provider_tag]['country']
            provider = country(discovery_reader, cap.base, root, int(previous['handle'], 16), provider_tag)
            relation_root = int(provider['address'], 16)+0x14f8
            index = _index(discovery_reader, cap.base, relation_root, 0x2d0, 0, root['count'])
            require(index['count_signed'] <= 4, 'Discovery provider count bound')
            raw = discovery_reader.read(int(index['array'], 16), index['count_signed']*16) if index['count_signed'] else b''
            selected_targets = []
            for slot, unused_object in struct.iter_unpack('<i4xQ', raw):
                address = discovery_reader.q(int(root['array'], 16)+slot*8)
                handle = discovery_reader.q(address+0x20)
                recipient = country(discovery_reader, cap.base, root, handle)
                require(recipient['slot'] == slot, 'Discovered counterpart generation differs')
                selected_targets.append(recipient)
            require(_index(discovery_reader, cap.base, relation_root, 0x2d0, 0, root['count']) == index,
                'Discovery index changed')
            discoveries.append(dict(provider=provider, index=index, current_counterparts=selected_targets,
                historical_object_pointer_dereferenced=False))
            for recipient in selected_targets:
                if provider_tag == 'TIM':
                    actor, target, action = recipient, provider, 'ask_knowledge_sharing'
                else:
                    actor, target, action = provider, recipient, 'knowledge_sharing'
                command = dict(request_id='readonly-existing-'+actor['tag']+'-'+target['tag'],
                    action=action, actor=actor['tag'], target=target['tag'])
                capture = cap.capture_knowledge(command, dict(actor_handle=int(actor['handle'], 16),
                    target_handle=int(target['handle'], 16)))
                if capture['state'].get('two_pass_equal') is True:
                    checked_capture(capture, command, identity)
                captures.append(capture)
        require(roots(discovery_reader, cap.base) == root, 'Discovery roots changed')
        cap.held.identity_check()
        require(cap.held.modules() == cap.modules, 'Modules changed during current-state observation')
    require(live_source_pins() == initial, 'Decoder source changed')
    result = dict(schema='EU4-KNOWLEDGE-EXISTING-PAIR-ACCEPTANCE/1',
        captured_utc=datetime.now(timezone.utc).isoformat(), identity=identity,
        identity_purpose='Read-only nonce, not a TAG installation or dispatch',
        source_pins=initial, discovery_source_sha256=digest(
            (ROOT/'work/reports/knowledge-nearby-candidates-20261015/live-selected-pairs.json').read_bytes()),
        discoveries=discoveries, captures=captures,
        discovery_read_budget=dict(calls=discovery_reader.calls, bytes=discovery_reader.bytes),
        native_calls=0, memory_written=False, requests_published=0, saves_written=0, reloads=0,
        new_API_effect_tested=False, institution_completion_verified=False,
        exact_external_request_id_causality_verified=False,
        limitations=['Existing current task decoder acceptance only; no new request was prepared or sent.',
                     'Active sharing does not prove institution adoption or external-request causality.'])
    with destination.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(destination), sha256=digest(destination.read_bytes()),
        captures=[dict(command=x['command'], status=x['state']['status'],
            two_pass_equal=x['state'].get('two_pass_equal'), duration_ms=x['duration_ms'],
            active_pair=x['state']['exact_pair_active_verified'], failure=x['state'].get('failure')) for x in captures])))


if __name__ == '__main__':
    main()
