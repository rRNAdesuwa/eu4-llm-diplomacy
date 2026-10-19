"""Read-only live decoder acceptance; the nonce is not a TAG installation."""
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_live_observer import KnowledgeRuntimeCapture, checked_capture, live_source_pins
from bridge.tag_command_backend import TagCommandBackend, digest, require


def main():
    backend = TagCommandBackend()
    identity = dict(pid=80340, creation='01dd5c075fcf8c26', session=secrets.token_hex(16),
        dll_sha256=backend.manifest['dll']['sha256'], manifest_sha256=backend.manifest_sha)
    directory = ROOT/'work/reports/diplomacy-live-observer-20261015-r1'
    destination = directory/'live-80340-knowledge-decoders.json'
    require(not destination.exists(), 'Exclusive live report required')
    before = live_source_pins()
    captures = []
    with KnowledgeRuntimeCapture(identity, backend) as cap:
        for action, actor, target in (('knowledge_sharing', 'FRA', 'JOL'),
                                      ('ask_knowledge_sharing', 'MAL', 'FRA')):
            command = dict(request_id='readonly-decoder-'+action,
                           action=action, actor=actor, target=target)
            value = cap.capture_knowledge(command)
            if value['state'].get('two_pass_equal') is True:
                checked_capture(value, command, identity)
            captures.append(value)
    require(live_source_pins() == before, 'Source changed during live acceptance')
    result = dict(schema='EU4-KNOWLEDGE-OBSERVER-LIVE-ACCEPTANCE/1',
        captured_utc=datetime.now(timezone.utc).isoformat(), identity=identity,
        identity_purpose='Read-only observation nonce, not a TAG installation or dispatch',
        native_session_installed=False, native_calls=0, memory_written=False,
        requests_published=0, saves_written=0, reloads=0,
        source_pins=before, captures=captures,
        active_sharing_effect_tested=False, institution_completion_verified=False,
        limitations=['Decoder and current pair state only; no new knowledge-sharing action was sent.',
                     'Two equal reads do not prove an atomic world epoch.'])
    with destination.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(destination), bytes=destination.stat().st_size,
        sha256=digest(destination.read_bytes()),
        captures=[dict(command=x['command'], duration_ms=x['duration_ms'],
                       status=x['state'].get('status'), two_pass_equal=x['state'].get('two_pass_equal'),
                       failure=x['state'].get('failure')) for x in captures])))


if __name__ == '__main__':
    main()
