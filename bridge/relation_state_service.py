"""Identity-bound current relation queries through the frozen read-only reader."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import re
import secrets
import struct
import time
from urllib.parse import urlsplit

from bridge.diplomacy_effect_observer import (
    RuntimeCapture, BudgetReader, HeldRPMPort, roots, country, full_handle, ptr, pins as effect_pins)
from bridge.relation_effect_reader import ACTIONS, PROFILES, read_relation_pair, verify_manifest as reader_pins
from bridge.tag_command_backend import (
    TagCommandBackend, ROOT, GAME_SHA, DEFAULT_MANIFEST, read, decode, digest, require, validate_identity)

HOST_MANIFEST = ROOT/'bridge/relation_state_service_manifest_1375.json'
READER_MANIFEST_SHA = 'a7f49bca379b725e2987d425c849272b6ca05fe9ad6c3aa6579deead2c80e753'
IDENTITY_PURPOSE = 'Read-only observation nonce; not a TAG installation or request'
LIMITATIONS = [
    'Current membership in both typed native indexes only; no new action is sent.',
    'Current presence or absence is independent of a request ID or prior API result.',
    'Global relation registration, expiry, AI acceptance and full lifecycle are not observed.',
    'Two consistent external passes can miss transient changes or ABA reuse; no atomic snapshot or world lease.']


def source_pins():
    raw=read(HOST_MANIFEST,65536);manifest=decode(raw)
    require(manifest['schema']=='EU4-RELATION-STATE-HOST-MANIFEST/1'
        and manifest['game_sha256']==GAME_SHA,'Relation host manifest identity differs')
    result={}
    for name,expected in manifest['source_pins'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts,'Relation host source path bound')
        data=read(ROOT/name,4*1024*1024);actual=dict(bytes=len(data),sha256=digest(data))
        require(actual==expected,'Relation host source differs: '+name);result[name]=actual
    require({'bridge/relation_state_service.py','tools/observe_relation_runtime.py',
        'bridge/tests/test_relation_state_service.py','bridge/relation_effect_reader_manifest_1375.json',
        'bridge/diplomacy_observer_service.py'}<=set(result),'Relation host source graph incomplete')
    require(result['bridge/relation_effect_reader_manifest_1375.json']['sha256']==READER_MANIFEST_SHA,
        'Frozen relation reader manifest differs')
    for graph in (reader_pins(),effect_pins()):
        for name,pin in graph.items():
            require(name not in result or result[name]==pin,'Dependency pin conflict: '+name)
            result[name]=pin
    result[HOST_MANIFEST.relative_to(ROOT).as_posix()]=dict(bytes=len(raw),sha256=digest(raw))
    return result


def validate_pair(action,actor,target):
    require(type(action) is str and action in ACTIONS,'Unsupported relation action')
    require(type(actor) is str and type(target) is str and re.fullmatch('[A-Z0-9]{3}',actor)
        and re.fullmatch('[A-Z0-9]{3}',target) and actor!=target,'Distinct three-character country tags required')


def relation_capabilities():
    return dict(schema='EU4-RELATION-STATE-CATALOG/1',read_only=True,
        endpoint='/observer/v1/relations/<action>/<actor>/<target>',
        actions=[dict(action=a,symmetric=PROFILES[a]['symmetric'],
            reply_required_for_new_positive_action=PROFILES[a]['reply_required']) for a in ACTIONS],
        statuses=['current_relation_observed','reverse_relation_observed','pair_absent_observed','unknown'],
        required_manual_pause=True,requires_injected_DLL=False,
        native_calls=0,memory_written=False,requests_published=0,saves_written=0,
        runtime_effect_verified=False,global_membership_verified=False,request_causality_verified=False,
        world_epoch_proven=False,world_lifetime_lease_proven=False,atomic_snapshot_proven=False,
        source_manifest_sha256=digest(read(HOST_MANIFEST,65536)),limitations=LIMITATIONS)


def compact_capture(capture,record=None):
    snapshot=capture.get('snapshot') or {};obj=snapshot.get('object')
    return dict(schema='EU4-RELATION-STATE-RESPONSE/1',action=capture['action'],status=capture['status'],
        identity=capture['identity'],identity_purpose=capture['identity_purpose'],
        native_session_installed=False,process_identity_authenticated_by_host=True,
        captured_utc=capture['captured_utc'],pair=snapshot.get('pair'),
        current_relation_observed=capture.get('current_relation_observed',False),
        requested_direction_matches=obj['requested_direction_matches'] if obj else None,
        object=obj,physical_pair_indexes=snapshot.get('indexes'),
        two_pass_equal=capture.get('two_pass_equal',False),now_raw=snapshot.get('now_raw'),
        duration_ms=capture['duration_ms'],rpm_budget=capture['total_rpm_budget'],record=record,
        failure=capture.get('failure'),read_only=True,native_calls=0,memory_written=False,
        requests_published=0,saves_written=0,reloads=0,automatic_command_retry=False,
        runtime_effect_verified=False,global_membership_verified=False,
        request_causality_verified=False,AI_acceptance_verified=False,
        world_epoch_proven=False,world_lifetime_lease_proven=False,atomic_snapshot_proven=False,
        limitations=LIMITATIONS)


class RelationStateObserver:
    def __init__(self,pid,creation,*,store=None,allow_tag_host=False,backend=None):
        self.backend=backend or TagCommandBackend()
        self._default_backend()
        require(type(allow_tag_host) is bool,'Explicit tag-host option must be boolean')
        self.allow_tag_host=allow_tag_host
        self.store=Path(store) if store is not None else None
        self.identity=validate_identity(dict(pid=pid,creation=creation,session=secrets.token_hex(16),
            dll_sha256=self.backend.manifest['dll']['sha256'],manifest_sha256=self.backend.manifest_sha))

    def _default_backend(self):
        require(Path(self.backend.manifest_path).resolve()==DEFAULT_MANIFEST.resolve()
            and Path(self.backend.build).resolve()==DEFAULT_MANIFEST.parent.resolve(),
            'Only the default TAG host metadata is permitted')
        raw=read(DEFAULT_MANIFEST,1024*1024);expected=decode(raw)
        require(self.backend.manifest_sha==digest(raw) and self.backend.manifest==expected,
            'Default TAG host metadata differs')

    def capture_pair(self,action,actor,target):
        validate_pair(action,actor,target)
        initial=source_pins();self._default_backend();started=time.perf_counter()
        with RuntimeCapture(self.identity,self.backend) as cap:
            r=BudgetReader(HeldRPMPort(cap.held))
            research=[(b,p) for b,p in cap.modules if Path(p).name.lower().startswith(
                ('eu4_bridge_','eu4_pair_','eu4_spy_','eu4_tag_command_','tag_diplomacy'))]
            canonical=cap.held.injector._canonical
            expected=self.backend.build/self.backend.manifest['DLL']
            require(not research or (self.allow_tag_host and len(research)==1
                and canonical(research[0][1])==canonical(expected)),'Unexpected research module')
            if research:
                header=cap.runtime.readonly.pe_header(r.read(ptr(research[0][0]),8192))
                require(header['machine']==0x8664 and header['timestamp']==self.backend.manifest['PE_timestamp']
                    and header['size_of_image']==self.backend.manifest['SizeOfImage'],'Loaded default TAG host header differs')
            root=roots(r,cap.base)
            require(root['manual_pause']==1,'Current relation observation requires an explicitly manually paused checkpoint')
            table=r.read(int(root['array'],16),root['count']*8)
            selected={}
            for address, in struct.iter_unpack('<Q',table):
                if not address:continue
                value=r.q(ptr(address)+0x20);tag=(value&0xffffff).to_bytes(3,'little')
                for name in (actor,target):
                    if tag==name.encode('ascii'):
                        require(name not in selected,'Duplicate selected country tag')
                        full_handle(value,root['count'],tag=name)
                        selected[name]=country(r,cap.base,root,value,name)
            require(set(selected)=={actor,target},'Selected country unavailable')
            capture=read_relation_pair(r,cap.base,action,int(selected[actor]['handle'],16),
                int(selected[target]['handle'],16),self.identity)
            require(all(item['roots']==root for item in capture['passes']), 'Relation roots changed after TAG scan')
            require(roots(r,cap.base)==root and r.read(int(root['array'],16),root['count']*8)==table,
                'Current country table or world guards changed')
            cap.held.identity_check()
            require(cap.held.modules()==cap.modules and effect_pins()==cap.initial_pins,
                'Process modules or frozen R1 sources changed')
            self._default_backend();self.backend.verify()
            require(source_pins()==initial,'Relation host sources changed during capture')
            capture.update(identity_purpose=IDENTITY_PURPOSE,native_session_installed=False,
                process_identity_authenticated_by_host=True,captured_utc=datetime.now(timezone.utc).isoformat(),
                source_pins=initial,total_rpm_budget=dict(calls=r.calls,bytes=r.bytes,largest_read=r.largest),
                duration_ms=round((time.perf_counter()-started)*1000,3),saves_written=0,reloads=0)
        return capture

    def observe_pair(self,action,actor,target):
        capture=self.capture_pair(action,actor,target);record=None
        if self.store is not None:
            raw=json.dumps(capture,ensure_ascii=True,allow_nan=False,indent=2).encode('ascii')
            require(len(raw)<=2*1024*1024,'Complete relation journal bound')
            self.store.mkdir(parents=True,exist_ok=True)
            path=self.store/f'relation-{action}-{actor}-{target}-{time.time_ns()}.json'
            with path.open('xb') as f:require(f.write(raw)==len(raw),'Short local journal write')
            record=dict(path=str(path),bytes=len(raw),sha256=digest(raw))
        return compact_capture(capture,record)


def make_relation_server(observer,base_server):
    """Add one GET namespace to a caller-supplied authenticated HTTP server.

    The original catalog, authentication and all other routes remain owned by
    the caller. This factory does not construct a listener or an effect catalog.
    """
    original=base_server.RequestHandlerClass
    require(issubclass(original,BaseHTTPRequestHandler) and callable(getattr(original,'authorized',None))
        and callable(getattr(original,'send_json',None)),'Authenticated base handler required')

    class Handler(original):
        def do_GET(self):
            if not self.path.startswith('/observer/v1/relations/'):
                return super().do_GET()
            if not self.authorized():return self.send_json(403,dict(error='unauthorized'))
            try:
                require(len(self.path)<=512,'Path bound')
                parts=urlsplit(self.path)
                require(not parts.query and not parts.fragment,'Query/fragment unsupported')
                match=re.fullmatch('/observer/v1/relations/([a-z_]+)/([A-Z0-9]{3})/([A-Z0-9]{3})',parts.path)
                require(match is not None,'Invalid relation pair path')
                action,actor,target=match.groups();validate_pair(action,actor,target)
                return self.send_json(200,observer.observe_pair(action,actor,target))
            except (ValueError,KeyError,TypeError,UnicodeError) as exc:
                return self.send_json(422,dict(error='invalid_or_refused',message=str(exc)))
            except (OSError,RuntimeError,struct.error) as exc:
                return self.send_json(409,dict(status='unknown',message=str(exc),automatic_command_retry=False,
                    runtime_effect_verified=False,native_calls=0,requests_published=0))

    base_server.RequestHandlerClass=Handler
    return base_server
