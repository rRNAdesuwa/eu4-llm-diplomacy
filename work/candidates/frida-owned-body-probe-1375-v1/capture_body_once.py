"""A separate, fixed, once-only raw ABI body probe; never a diplomacy sender.

check is file-only. capture requires a sealed manifest and independent review.
The native body receives only explicitly owned raw buffers, not a C++ object.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import struct
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REL = HERE.relative_to(ROOT).as_posix()
MANIFEST = HERE/'body-host-manifest.json'
OUT = ROOT/'work/reports/war-peace-api-20261015-r19-body-live'
OLD_HOST = ROOT/'work/candidates/frida-entry-observer-1375-v1/capture_once.py'
OLD_SHA = 'b39823564ab26a9da7093e1812b2a1fec28a17141e3c4a1024460664b1943b6e'
PROFILE = ROOT/'work/reports/war-peace-api-20261015-r17-owned-goal-independent-review/war/profiles.json'
PROFILE_SHA = 'c76853c78cd10cb8e1748ec4e3dbbd19bd53905fd3ecf2f40111379c0ac3b283'
FFI = ROOT/'work/reports/rea-frida-owned-ffi-smoke-20261015/f724e4537abba85248a900c51ca487c3/launcher-receipt.json'
FFI_SHA = '0b164e895bad4aa131b24c84f94c41ea5b9e459d017efbe6e1372d58ca900d03'
PID, CREATION, BASE = 80340, '01dd5c075fcf8c26', 0x7ff7034b0000
CODE_RANGES = ((0x500560,109),(0x8eac0,91),(0x8f450,3))


def require(value, message):
    if not value:
        raise ValueError(message)


def read_bound(path, maximum=1024*1024):
    with Path(path).open('rb') as stream:
        raw = stream.read(maximum+1)
    require(0 < len(raw) <= maximum, 'File bound: '+str(path))
    return raw


def pin(path):
    raw = read_bound(path,16*1024*1024)
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def exact_load(path, sha, name):
    raw = read_bound(path)
    require(hashlib.sha256(raw).hexdigest() == sha,'Changed module before exact compilation')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def fixed_host():
    require(pin(OLD_HOST)['sha256'] == OLD_SHA,'Frozen entry host changed')
    return exact_load(OLD_HOST,OLD_SHA,'_frozen_host_for_owned_body')


def code_profile():
    raw = read_bound(PROFILE)
    require(hashlib.sha256(raw).hexdigest() == PROFILE_SHA,'Static independent profile changed')
    doc = json.loads(raw.decode('utf-8'))
    result = []
    for rva,size in CODE_RANGES:
        rows = [r for r in doc['complete_retained_functions'] if int(r['start'],16) == rva]
        require(len(rows) == 1,'Missing unique retained function')
        row = rows[0]
        body = bytes.fromhex(row['raw_hex'])
        require(row['bytes'] == len(body) == size and int(row['end_exclusive'],16) == rva+size
                and hashlib.sha256(body).hexdigest() == row['sha256'],'Retained function bytes differ')
        result.append((rva,body))
    return result


def loaded_sample(cap, observer, profile):
    reader = observer.BudgetReader(observer.HeldRPMPort(cap.held))
    rows = []
    for rva,expected in profile:
        raw = reader.read(cap.base+rva,len(expected))
        rows.append(dict(rva=hex(rva),address=hex(cap.base+rva),size=len(raw),raw_hex=raw.hex()))
        require(raw == expected,'Selected loaded function bytes differ')
    slot = reader.read(cap.base+0x1d20870,8)
    require(slot == struct.pack('<Q',cap.base+0x8f450),'Relocated virtual slot differs')
    return dict(code=rows,slot=dict(rva='0x1d20870',address=hex(cap.base+0x1d20870),
        raw8_hex=slot.hex(),value=hex(struct.unpack('<Q',slot)[0])),
        rpm_budget=dict(calls=reader.calls,bytes=reader.bytes,largest=reader.largest))


def verify():
    host = fixed_host()
    raw = read_bound(MANIFEST)
    manifest = host.strict_json(raw,evidence_scalars=False)
    require(manifest['schema'] == 'EU4-OWNED-BODY-HOST-MANIFEST/1'
            and manifest['sealed'] is True and manifest['pid'] == PID
            and type(manifest['pid']) is int and manifest['creation'] == CREATION
            and manifest['base'] == hex(BASE),'A sealed fixed reviewed body manifest is required')
    sources = manifest['source_pins']
    required = {REL+'/'+name for name in ('capture_body_once.py','body_probe.js','body_parser.py',
        'PROTOCOL.md','test_capture_body_once.py')}
    require(type(sources) is dict and required <= set(sources) and len(sources) <= 64,'Selected source set')
    total = 0
    for rel,expected in sources.items():
        path = host.local_path(rel)
        actual = pin(path)
        require(actual == expected,'Body source/evidence changed: '+rel)
        total += actual['bytes']
        require(total <= 32*1024*1024,'Selected source total bound')
    for path,sha in ((OLD_HOST,OLD_SHA),(PROFILE,PROFILE_SHA),(FFI,FFI_SHA)):
        require(sources.get(path.relative_to(ROOT).as_posix(),{}).get('sha256') == sha
                and pin(path)['sha256'] == sha,'Fixed reviewed dependency omitted or changed')
    review = host.local_path(manifest['independent_review'])
    require(pin(review) == manifest['independent_review_pin'],'Body source review changed')
    ffi = host.strict_json(read_bound(FFI),evidence_scalars=False)
    require(ffi['status'] == 'owned_fixture_kernel32_ffi_observed' and ffi['error'] is None
            and ffi['source_postcheck'] is True,'Owned system FFI observation required')
    require(manifest.get('native_ready') is False and manifest.get('sender_authorized') is False
            and manifest.get('lifetime_lease') is False,'Scope flags differ')
    frozen = host.verify_manifest()
    code_profile()
    return host,dict(manifest_sha256=hashlib.sha256(raw).hexdigest(),source_pins=sources,
        independent_review_pin=manifest['independent_review_pin'],frozen_host=frozen)


def capture(initial,host):
    OUT.mkdir(parents=True,exist_ok=True)
    host.write_new(OUT/'claim.json',dict(schema='EU4-OWNED-BODY-CLAIM/1',pid=PID,creation=CREATION,
        manifest_sha256=initial['manifest_sha256'],claimed_utc=datetime.now(timezone.utc).isoformat(),
        automatic_retry=False,requests_published=0))
    result = dict(schema='EU4-OWNED-BODY-HOST-CAPTURE/1',status='unknown',
        captured_utc=datetime.now(timezone.utc).isoformat(),pid=PID,creation=CREATION,source_graph=initial,
        errors=[],precheck=None,postcheck=None,loaded_precheck=None,loaded_postcheck=None,job=None,
        REA_evidence_id=None,payload_evaluation=None,attach_may_have_been_attempted=False,
        top_level_native_game_calls_attempted_observed=0,top_level_native_game_calls_returned_observed=0,
        native_game_objects_constructed=0,raw_owned_ABI_test_double=True,
        legal_Cplusplus_object_construction_proven=False,full_native_lifecycle=False,
        field_game_data_writes=0,requests_published=0,saves_written=0,reloads=0,
        new_API_effect_tested=False,war_declared=False,peace_concluded=False,
        pure_RPM=False,temporary_code_hook=False,native_ready=False,sender_authorized=False,
        native_entry_authenticated=False,lifetime_lease=False,atomic_snapshot=False,
        code_restore_verified=False,selected_cleanup_checks_passed=False,
        target_full_cleanup_or_agent_unmapping_proven=False,automatic_retry=False)
    try:
        _,current = verify()
        require(current == initial,'Sources changed before capture')
        parser_path = HERE/'body_parser.py'
        parser = exact_load(parser_path,initial['source_pins'][REL+'/body_parser.py']['sha256'],'_body_parser')
        frozen = initial['frozen_host']
        jobs = host.load_local('work/candidates/frida-entry-observer-1375-v1/job_tree.py',frozen)
        sys.path.insert(0,str(ROOT))
        try:
            observer = host.load_local('bridge/diplomacy_effect_observer.py',frozen)
        finally:
            sys.path.pop(0)
        backend = observer.TagCommandBackend()
        identity = dict(pid=PID,creation=CREATION,session=secrets.token_hex(16),
            dll_sha256=backend.manifest['dll']['sha256'],manifest_sha256=backend.manifest_sha)
        with observer.RuntimeCapture(identity,backend) as cap:
            require(cap.base == BASE,'Fixed loaded base differs')
            require(not any(Path(p).name.lower().startswith(('eu4_bridge_','eu4_pair_','eu4_spy_',
                'eu4_tag_command_','tag_diplomacy')) for _,p in cap.modules),'Unexpected research module')
            result['precheck'] = host.host_sample(cap,observer)
            result['loaded_precheck'] = loaded_sample(cap,observer,code_profile())
            config = dict(schema='EU4-FRIDA-BODY-PROBE-CONFIG/1',pid=PID,creation=CREATION,
                game_sha256=host.GAME_SHA,base='0x'+format(BASE,'016x'),expected_prefix_hex=host.PREFIX.hex(),
                observer_nonce=secrets.token_hex(16),max_attempts=16)
            result['config'] = config
            script = OUT/'rendered-body-probe.js'
            source = read_bound(HERE/'body_probe.js',65536)
            require(dict(bytes=len(source),sha256=hashlib.sha256(source).hexdigest()) ==
                    initial['source_pins'][REL+'/body_probe.js'],'Script changed before rendering')
            rendered = ('const EU4_BODY_PROBE_CONFIG = '+json.dumps(config,separators=(',',':'))+';\n').encode('ascii')+source
            with script.open('xb') as stream:
                require(stream.write(rendered) == len(rendered),'Short rendered script write')
            result['rendered_script_pin'] = pin(script)
            try:
                _,current = verify()
                require(current == initial and pin(script) == result['rendered_script_pin'],'Sources changed before attach')
                result['attach_may_have_been_attempted'] = True
                result['temporary_code_hook'] = None
                result['top_level_native_game_calls_attempted_observed'] = None
                result['top_level_native_game_calls_returned_observed'] = None
                result['job'] = jobs.run_cli_tree(host.registered_argv(script),str(ROOT),
                    OUT/'rea.stdout.json',OUT/'rea.stderr.txt')
                host.accepted_job(result['job'])
                require(result['job']['completed_command_descendants_terminated'] is False
                        and type(result['job']['job_total_processes']) is int
                        and 1 <= result['job']['job_total_processes'] <= 8,'Forced cleanup or job count differs')
                require((OUT/'rea.stderr.txt').stat().st_size == 0,'Nonempty REA stderr')
                evidence,payload = host.extract_evidence(read_bound(OUT/'rea.stdout.json',2*1024*1024),
                    config,str(script.resolve()),result['rendered_script_pin']['sha256'])
                result['REA_evidence_id'] = evidence['evidence_id']
                host.write_new(OUT/'owned-payload.json',payload)
                evaluation = parser.evaluate(payload,config)
                result['payload_evaluation'] = evaluation
                require(evaluation['status'] == 'raw_abi_postcondition_match','Body observation is unknown')
                result['top_level_native_game_calls_attempted_observed'] = payload['native_game_calls_attempted']
                result['top_level_native_game_calls_returned_observed'] = payload['native_game_calls_returned']
                result['temporary_code_hook'] = payload['temporary_code_hook']
                result['REA_cleanup_reported_success'] = True
            except Exception as exc:
                result['errors'].append(dict(stage='instrument',type=type(exc).__name__,message=str(exc)))
            finally:
                try:
                    cap.held.identity_check()
                    r = observer.BudgetReader(observer.HeldRPMPort(cap.held))
                    prefix = r.read(cap.base+host.ENTRY_RVA,32)
                    result['post_prefix32_hex'] = prefix.hex()
                    require(prefix == host.PREFIX,'Independent hook prefix differs')
                    result['code_restore_verified'] = True
                    result['loaded_postcheck'] = loaded_sample(cap,observer,code_profile())
                    result['postcheck'] = host.host_sample(cap,observer)
                    require(result['postcheck'] == result['precheck']
                            and result['loaded_postcheck'] == result['loaded_precheck'],'Selected host projection changed')
                    _,current = verify()
                    require(current == initial and observer.pins() == cap.initial_pins
                            and pin(script) == result['rendered_script_pin'],'Post-operation sources changed')
                except Exception as exc:
                    result['errors'].append(dict(stage='postcheck',type=type(exc).__name__,message=str(exc)))
        if not result['errors']:
            result.update(status='raw_abi_postcondition_match',selected_cleanup_checks_passed=True,
                held_process_identity_bound=True,host_image_and_base_verified=True)
    except Exception as exc:
        result['errors'].append(dict(stage='host',type=type(exc).__name__,message=str(exc)))
    host.write_new(OUT/'capture.json',result)
    return result


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('operation',choices=('check','capture'))
    operation = args.parse_args().operation
    try:
        host,initial = verify()
        if operation == 'check':
            print(json.dumps(dict(status='file_check_passed',manifest_sha256=initial['manifest_sha256'],
                process_opened=False,native_ready=False)))
            return 0
        result = capture(initial,host)
        print(json.dumps(dict(status=result['status'],output=str(OUT/'capture.json'),errors=result['errors'],
            REA_evidence_id=result['REA_evidence_id'],native_ready=False,requests_published=0)))
        return 0 if result['status'] == 'raw_abi_postcondition_match' else 2
    except Exception as exc:
        print(json.dumps(dict(status='unknown',error=dict(type=type(exc).__name__,message=str(exc)),
            automatic_retry=False,native_ready=False)))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
