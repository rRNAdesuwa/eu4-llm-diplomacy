"""Read-only current-war host and optional HTTP composition with diplomacy.

Uses frozen R7-r2 decoding and the existing held QUERY/VM_READ process port.
The host has no publisher, injector, game function or memory write operation.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import struct
import time
from urllib.parse import urlsplit

from bridge.diplomacy_effect_observer import (RuntimeCapture, BudgetReader,
    HeldRPMPort, roots, country, full_handle, pins as effect_pins)
from bridge.tag_command_backend import (ROOT, GAME_SHA, TagCommandBackend,
    read, decode, digest, require, validate_identity)
from bridge.war_peace_memory_observer_r2 import capture_war_pair

WAR_MANIFEST = ROOT/'work/reports/war-peace-api-20261015-r7-r2/observer/manifest.json'
WAR_MANIFEST_SHA = '7f844951adb72c5843088f00172310642f9ef1f5efe12c1157b5260242227d8c'
HOST_MANIFEST = ROOT/'bridge/war_state_service_manifest_1375.json'
ERRORS = (OSError, ValueError, RuntimeError, KeyError, TypeError, UnicodeError, struct.error)


def source_pins():
    raw = read(HOST_MANIFEST, 65536)
    manifest = decode(raw)
    require(manifest['schema'] == 'EU4-WAR-STATE-HOST-MANIFEST/1'
        and manifest['game_sha256'] == GAME_SHA, 'War host identity differs')
    result = {}
    for relative, expected in manifest['source_pins'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
            'War host source path bound')
        data = read(ROOT/relative, 4*1024*1024)
        actual = dict(bytes=len(data), sha256=digest(data))
        require(actual == expected, 'War host source differs: '+relative)
        result[relative] = actual
    require({'bridge/war_state_service.py', 'tools/observe_war_runtime.py',
        'bridge/tests/test_war_state_service.py'} <= set(result), 'War host source graph incomplete')
    raw_war = read(WAR_MANIFEST, 65536)
    require(digest(raw_war) == WAR_MANIFEST_SHA, 'Frozen R7-r2 manifest differs')
    for row in decode(raw_war)['files']:
        relative = row['path']
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
            'Frozen war source path bound')
        data = read(ROOT/relative, 4*1024*1024)
        actual = dict(bytes=len(data), sha256=digest(data))
        require(actual == {k: row[k] for k in actual}, 'Frozen war source differs')
        result[relative] = actual
    result[WAR_MANIFEST.relative_to(ROOT).as_posix()] = dict(bytes=len(raw_war), sha256=digest(raw_war))
    result.update(effect_pins())
    result[HOST_MANIFEST.relative_to(ROOT).as_posix()] = dict(bytes=len(raw), sha256=digest(raw))
    return result


def tags(actor, target):
    require(type(actor) is str and type(target) is str
        and re.fullmatch('[A-Z0-9]{3}', actor) and re.fullmatch('[A-Z0-9]{3}', target)
        and actor != target, 'Distinct three-character country tags required')


def war_capabilities():
    return dict(schema='EU4-WAR-STATE-CATALOG/1', read_only=True,
        endpoint='/observer/v1/wars/<actor>/<target>', current_pair_state=True,
        required_manual_pause=True, requires_injected_DLL=False,
        native_calls=0, memory_written=False, requests_published=0, saves_written=0,
        declaration_API_completion_verified=False, peace_API_completion_verified=False,
        world_epoch_proven=False, world_lifetime_lease_proven=False,
        source_manifest_sha256=digest(read(HOST_MANIFEST, 65536)),
        limitations=['Current opposing membership only; independent of a request ID.',
            'War disappearance alone does not prove peace terms or object destruction.'])


def compact_capture(capture, record=None):
    graph = capture.get('projection') or {}
    return dict(schema='EU4-WAR-STATE-RESPONSE/1', status=capture['status'],
        identity=capture['identity'], captured_utc=capture['captured_utc'],
        identity_purpose=capture['identity_purpose'], native_session_installed=False,
        actor=graph.get('actor'), target=graph.get('target'), pair_state=graph.get('pair_state'),
        global_war_count=graph.get('global_war_count'), selected_war=graph.get('selected_war'),
        two_pass_equal=capture.get('two_pass_equal', False),
        physical_pair_indexes=graph.get('physical_pair_indexes'),
        relation_indexes=graph.get('relation_indexes'),
        duration_ms=capture['duration_ms'], rpm_budget=capture['total_rpm_budget'],
        record=record, failure=capture.get('failure'),
        read_only=True, native_calls=0, memory_written=False, requests_published=0,
        saves_written=0, reloads=0, automatic_command_retry=False,
        runtime_effect_verified=False, war_retired_proven=False,
        peace_terms_verified=False, peace_completion_verified=False,
        request_causality_verified=False, world_epoch_proven=False,
        limitations=capture['limitations'])


class WarStateObserver:
    def __init__(self, pid, creation, *, backend=None, store=None, allow_tag_host=False):
        self.backend = backend or TagCommandBackend()
        self.identity = validate_identity(dict(pid=pid, creation=creation,
            session=secrets.token_hex(16), dll_sha256=self.backend.manifest['dll']['sha256'],
            manifest_sha256=self.backend.manifest_sha))
        require(type(allow_tag_host) is bool, 'Explicit tag-host option must be boolean')
        self.allow_tag_host = allow_tag_host
        self.store = Path(store) if store is not None else None

    def capture_pair(self, actor, target):
        tags(actor, target)
        initial = source_pins()
        started = time.perf_counter()
        with RuntimeCapture(self.identity, self.backend) as cap:
            r = BudgetReader(HeldRPMPort(cap.held))
            research = [(b, p) for b, p in cap.modules if Path(p).name.lower().startswith(
                ('eu4_bridge_', 'eu4_pair_', 'eu4_spy_', 'eu4_tag_command_', 'tag_diplomacy'))]
            canonical = cap.held.injector._canonical
            expected = self.backend.build/self.backend.manifest['DLL']
            require(not research or (self.allow_tag_host and len(research) == 1
                and canonical(research[0][1]) == canonical(expected)), 'Unexpected research module')
            if research:
                header = cap.runtime.readonly.pe_header(r.read(research[0][0], 8192))
                require(header['machine'] == 0x8664
                    and header['timestamp'] == self.backend.manifest['PE_timestamp']
                    and header['size_of_image'] == self.backend.manifest['SizeOfImage'],
                    'Loaded build7 header differs')
            root = roots(r, cap.base)
            require(root['manual_pause'] == 1, 'Current-war observation requires a manually paused checkpoint')
            raw = r.read(int(root['array'], 16), root['count']*8)
            selected = {}
            for address, in struct.iter_unpack('<Q', raw):
                if not address:
                    continue
                handle = r.q(address+0x20)
                raw_tag = (handle & 0xffffff).to_bytes(3, 'little')
                for name in (actor, target):
                    if raw_tag == name.encode('ascii'):
                        require(name not in selected, 'Duplicate selected country tag')
                        full_handle(handle, root['count'], tag=name)
                        selected[name] = country(r, cap.base, root, handle, name)
            require(set(selected) == {actor, target}, 'Selected country unavailable')
            capture = capture_war_pair(r, cap.base, root, selected[actor], selected[target])
            cap.held.identity_check()
            require(cap.held.modules() == cap.modules and effect_pins() == cap.initial_pins,
                'Process modules or frozen observer sources changed')
            require(source_pins() == initial, 'War host sources changed during capture')
            capture.update(identity=self.identity,
                identity_purpose='Read-only observation nonce; not a TAG installation or request',
                native_session_installed=False, process_identity_authenticated_by_host=True,
                captured_utc=datetime.now(timezone.utc).isoformat(), source_pins=initial,
                total_rpm_budget=dict(calls=r.calls, bytes=r.bytes, largest_read=r.largest),
                duration_ms=round((time.perf_counter()-started)*1000, 3), saves_written=0, reloads=0)
        return capture

    def observe_pair(self, actor, target):
        capture = self.capture_pair(actor, target)
        record = None
        if self.store is not None:
            raw = json.dumps(capture, ensure_ascii=True, allow_nan=False, indent=2).encode('ascii')
            require(len(raw) <= 2*1024*1024, 'Complete war journal bound')
            self.store.mkdir(parents=True, exist_ok=True)
            path = self.store/f'war-{actor}-{target}-{time.time_ns()}.json'
            with path.open('xb') as f:
                require(f.write(raw) == len(raw), 'Short local journal write')
            record = dict(path=str(path), bytes=len(raw), sha256=digest(raw))
        return compact_capture(capture, record)


class NoEffects:
    def observe(self, request_id):
        raise FileNotFoundError('No request observer configured')


def make_war_server(war_observer, *, port=8775, token, effect_observer=None,
                    base_factory=None, capability_factory=None):
    """Compose routes by subclassing the frozen authenticated HTTP handler."""
    if base_factory is None:
        from bridge.diplomacy_observer_service import make_server
        base_factory = make_server
    server = base_factory(effect_observer or NoEffects(), port=port, token=token)
    original = server.RequestHandlerClass

    class Handler(original):
        def do_GET(self):
            if self.path == '/observer/v1/capabilities':
                if not self.authorized():
                    return self.send_json(403, {'error': 'unauthorized'})
                try:
                    value = capability_factory() if capability_factory else dict(
                        schema='EU4-RUNTIME-OBSERVER-CATALOG/1', read_only=True,
                        profiles=[], all120_effect_profiles_complete=False)
                    value['war_state'] = war_capabilities()
                    return self.send_json(200, value)
                except ERRORS as exc:
                    return self.send_json(409, dict(status='unknown', message=str(exc), automatic_command_retry=False))
            if not self.path.startswith('/observer/v1/wars/'):
                return super().do_GET()
            if not self.authorized():
                return self.send_json(403, {'error': 'unauthorized'})
            try:
                require(len(self.path) <= 512, 'Path bound')
                parts = urlsplit(self.path)
                require(not parts.query and not parts.fragment, 'Query/fragment unsupported')
                match = re.fullmatch('/observer/v1/wars/([A-Z0-9]{3})/([A-Z0-9]{3})', parts.path)
                require(match is not None, 'Invalid country-pair path')
                actor, target = match.groups()
                tags(actor, target)
                return self.send_json(200, war_observer.observe_pair(actor, target))
            except (ValueError, KeyError, TypeError, UnicodeError) as exc:
                return self.send_json(422, dict(error='invalid_or_refused', message=str(exc)))
            except (OSError, RuntimeError, struct.error) as exc:
                return self.send_json(409, dict(status='unknown', message=str(exc),
                    automatic_command_retry=False, native_calls=0, requests_published=0))

    server.RequestHandlerClass = Handler
    return server
