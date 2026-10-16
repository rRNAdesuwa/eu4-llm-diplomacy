"""One fresh-root QUERY/VM_READ capture of R15 child context. No retry/calls."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT/'work/candidates/frida-entry-observer-1375-v1/capture_once.py'
HOST_MANIFEST = ROOT/'work/candidates/frida-entry-observer-1375-v1/host-manifest.json'
READER = ROOT/'work/candidates/child-context-observer-1375-v1/reader.py'
CONTRACT_DIR = ROOT/'work/reports/war-peace-api-20261015-r15-child-context/war'
STATIC_REVIEW = ROOT/'work/reports/war-peace-api-20261015-r15-child-context-independent-review/war/findings.json'
READER_REVIEW = ROOT/'work/reports/current-child-reader-review-20261015-r1/independent-source-ready.json'
READER_REVIEW_SHA = '5e368dc3203b7a979f96643e851581e9fb2fbb72a854b43eedd5fe922157dcaf'
OUT = ROOT/'work/reports/war-peace-api-20261015-r16-child-current/live-80340-child-current.json'


def require(value,message):
    if not value:
        raise ValueError(message)


def pin(path):
    size,h = 0,hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024*1024):
            size += len(block)
            require(size <= 16*1024*1024,'Source/evidence size bound')
            h.update(block)
    return dict(bytes=size,sha256=h.hexdigest())


def checked_load(path,sha,name):
    raw = path.read_bytes()
    require(len(raw) <= 1024*1024 and hashlib.sha256(raw).hexdigest() == sha,'Fixed source changed before import')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def main():
    require(not OUT.exists(),'Exclusive capture output already exists; no retry')
    require(re.fullmatch('[0-9a-f]{64}',READER_REVIEW_SHA),'Independent reader review pending')
    fixed = {HOST:'b39823564ab26a9da7093e1812b2a1fec28a17141e3c4a1024460664b1943b6e',
        HOST_MANIFEST:'e7673b0e07c052788d6d2c6378939e176f57e79a45ea09888b957741b7370166',
        READER:'002ae678831a5e62de245206fba2e5ed5d473739ec980486125fa5a1b0efda8a',
        CONTRACT_DIR/'manifest.json':'4e99f20e76cdd5059a52f90334f969ba66f3c602375b15a15d45e1bdc08730fd',
        CONTRACT_DIR/'current-read-contract.json':'829cc4b59c2610c47503821b2cb04cc3c70576eb6787f1ea711fa7e4d7599e07',
        STATIC_REVIEW:'4d58fe7e97c43b18e6e44781b6a5b695b018acc0981ce209aeddb02771cc44d7',
        READER_REVIEW:READER_REVIEW_SHA}
    for p,sha in fixed.items():
        require(pin(p)['sha256'] == sha,'Fixed source/evidence identity changed: '+str(p))
    manifest = json.loads((CONTRACT_DIR/'manifest.json').read_bytes())
    for row in manifest['files']:
        path = (ROOT/row['path']).resolve()
        require(path.is_relative_to(ROOT.resolve()) and pin(path) == {k:row[k] for k in ('bytes','sha256')},
                'R15 retained source differs')
        fixed[path] = row['sha256']
    fixed[Path(__file__).resolve()] = pin(Path(__file__).resolve())['sha256']
    def sources():
        values = {str(p.relative_to(ROOT)).replace('\\','/'):pin(p) for p in fixed}
        require(all(values[str(p.relative_to(ROOT)).replace('\\','/')]['sha256'] == sha for p,sha in fixed.items()),
                'Producer/reader/contract/review changed during capture')
        return values
    initial_sources = sources()
    host = checked_load(HOST,fixed[HOST],'frozen_host_for_child_context')
    frozen = host.verify_manifest()
    reader_module = checked_load(READER,fixed[READER],'pure_child_context_reader')
    sys.path.insert(0,str(ROOT))
    try:
        observer = host.load_local('bridge/diplomacy_effect_observer.py',frozen)
    finally:
        sys.path.pop(0)
    backend = observer.TagCommandBackend()
    identity = dict(pid=80340,creation='01dd5c075fcf8c26',session=secrets.token_hex(16),
        dll_sha256=backend.manifest['dll']['sha256'],manifest_sha256=backend.manifest_sha)
    result = dict(schema='EU4-CHILD-CONTEXT-CURRENT-READONLY/1',status='unknown',
        captured_utc=datetime.now(timezone.utc).isoformat(),identity=identity,
        identity_purpose='Fresh read-only nonce, not TAG installation/request',source_pins=initial_sources,
        host_manifest_sha256=frozen['manifest_sha256'],samples=[],precheck=None,postcheck=None,errors=[],
        native_callback_observed=False,historical_Q_or_heap_used=False,pure_RPM=True,
        native_game_calls=0,game_fields_written=0,hooks_installed=0,Frida_called=False,
        requests_published=0,saves=0,reloads=0,new_API_effect_tested=False,
        native_ready=False,native_entry_authenticated=False,sender_authorized=False,
        lifetime_lease=False,sentinel_header_lease=False,atomic_snapshot=False,automatic_retry=False)
    started = time.perf_counter()
    try:
        with observer.RuntimeCapture(identity,backend) as cap:
            require(not any(Path(p).name.lower().startswith(('eu4_bridge_','eu4_pair_','eu4_spy_',
                'eu4_tag_command_','tag_diplomacy')) for _,p in cap.modules),'Unexpected research module')
            result['module_base'] = '0x'+format(cap.base,'016x')
            result['precheck'] = host.host_sample(cap,observer)
            r = observer.BudgetReader(observer.HeldRPMPort(cap.held))
            try:
                first = reader_module.sample(r,cap.base)
                result['samples'].append(first)
                require(first['status'] != 'unknown','First selected projection unknown; stop without retry')
                second = reader_module.sample(r,cap.base)
                result['samples'].append(second)
                require(second['status'] != 'unknown' and first == second,'Two current projections differ or are unknown')
                require(r.calls <= 50 and r.bytes <= 328,'Shared selected two-pass budget exceeded')
                result['selected_two_pass_equal'] = True
                result['selected_current_state'] = first['status']
            except Exception as exc:
                result['errors'].append(dict(stage='selected',type=type(exc).__name__,message=str(exc)))
            finally:
                result['selected_rpm_budget'] = dict(calls=r.calls,bytes=r.bytes,largest=r.largest)
                result['postcheck'] = host.host_sample(cap,observer)
                require(result['postcheck'] == result['precheck'] and cap.held.modules() == cap.modules,
                        'Host world/module guards changed')
                require(observer.pins() == cap.initial_pins and host.verify_manifest() == frozen
                        and sources() == initial_sources,'Sources changed after current sample')
        if not result['errors']:
            result['status'] = 'sampled_equal'
    except Exception as exc:
        result['errors'].append(dict(stage='host',type=type(exc).__name__,message=str(exc)))
    result['duration_ms_including_host_checks'] = round((time.perf_counter()-started)*1000,3)
    host.write_new(OUT,result)
    print(json.dumps(dict(output=str(OUT),sha256=pin(OUT)['sha256'],status=result['status'],
        selected_current_state=result.get('selected_current_state'),selected_rpm_budget=result.get('selected_rpm_budget'),
        errors=result['errors'],native_ready=False,requests_published=0)))
    return 0 if result['status'] == 'sampled_equal' else 2


if __name__ == '__main__':
    raise SystemExit(main())
