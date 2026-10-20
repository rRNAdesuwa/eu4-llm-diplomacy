"""One held-process RPM capture of direct pair cache flags; no native getter.

This reports the cache bit consumed by native truce code, not its additional
linked-country predicate, an expiry, a truce object or peace completion.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import struct
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT/'work/candidates/frida-entry-observer-1375-v1/capture_once.py'
HOST_SHA = 'b39823564ab26a9da7093e1812b2a1fec28a17141e3c4a1024460664b1943b6e'
HOST_MANIFEST = HOST.parent/'host-manifest.json'
STATIC = ROOT/'work/reports/war-peace-api-20261015-r23-truce-observation-contract/war'
STATIC_REVIEW = ROOT/'work/reports/war-peace-api-20261015-r23-independent-review/war/findings.json'
STATIC_REVIEW_SHA = '8d78398749fd0845ff4abbf8c297819aee58ea0ae3ce6ed1cf3c6f233d0017be'
OUT = ROOT/'work/reports/war-peace-api-20261015-r24-direct-truce-current'
PAIRS = (('FRA','ENG'),('ENG','FRA'),('TUR','HUN'),('HUN','TUR'),
         ('TUR','VEN'),('VEN','TUR'),('MOS','NOV'),('NOV','MOS'))


def require(value,message):
    if not value:
        raise ValueError(message)


def pin(path):
    count,digest = 0,hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024*1024):
            count += len(block)
            require(count <= 16*1024*1024,'Selected source byte bound')
            digest.update(block)
    require(count > 0,'Empty selected source')
    return dict(bytes=count,sha256=digest.hexdigest())


def read_bound(path,maximum):
    with path.open('rb') as stream:
        raw = stream.read(maximum+1)
    require(0 < len(raw) <= maximum,'Selected file byte bound')
    return raw


def exact_load(path,sha,name):
    raw = read_bound(path,1024*1024)
    require(hashlib.sha256(raw).hexdigest() == sha,'Source changed before import')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


class AlignedPort:
    """Extra selected structural alignment guard before underlying RPM.

    The frozen reader already checks canonical spans/budgets, but its ptr()
    does not establish alignment. This wrapper does not change frozen code.
    """
    def __init__(self,port):
        self.port = port

    def read(self,address,size):
        require(type(address) is int and type(size) is int and 0 < size <= 65536
                and 0x10000 <= address < address+size <= 2**47,'Selected read span/type')
        require(size < 8 or address % 8 == 0,'Selected structural read is not aligned')
        return self.port.read(address,size)


def owned_country(r,observer,base,root,handle,tag):
    item = observer.country(r,base,root,handle,tag)
    address = int(item['address'],16)
    raw = r.read(address,0x28)
    require(struct.unpack_from('<Q',raw)[0] == base+observer.COUNTRY_VT
            and struct.unpack_from('<I',raw,8)[0] == 357
            and struct.unpack_from('<Q',raw,0x20)[0] == handle,'Owned country header changed')
    return dict(**item,header_raw_hex=raw.hex())


def pair_sample(r,observer,base,root,selected,actor_tag,target_tag):
    actor = owned_country(r,observer,base,root,selected[actor_tag],actor_tag)
    target = owned_country(r,observer,base,root,selected[target_tag],target_tag)
    pair = observer.relation(r,actor,target,base)
    raw_root = r.read(pair['root'],0x30)
    begin,end,capacity = struct.unpack_from('<QQQ',raw_root,0x18)
    require(struct.unpack_from('<QI',raw_root) == (base+0x1c4f5f8,357)
            and struct.unpack_from('<Q',raw_root,0x10)[0] == int(actor['address'],16),
            'Owned relation root type/owner changed')
    require(all(value % 8 == 0 for value in (pair['root'],pair['record'],begin,end,capacity))
            and 0x10000 <= begin <= end <= capacity < 2**47
            and (end-begin) % 0x48 == (capacity-begin) % 0x48 == 0
            and capacity-begin <= 4096*0x48
            and pair['record'] == begin+target['slot']*0x48
            and pair['record']+0x48 <= end,'Owned relation vector metadata changed')
    raw = pair['data']
    require(type(raw) is bytes and len(raw) == 0x48
            and struct.unpack_from('<QQQ',raw) ==
                (pair['root'],selected[actor_tag],selected[target_tag]),'Owned complete pair mismatch')
    return dict(actor=actor,target=target,relation_root=hex(pair['root']),
        relation_record=hex(pair['record']),root_raw_hex=raw_root.hex(),record_raw_hex=raw.hex(),
        field_offset='0x45',mask=1,raw_byte45=raw[0x45],direct_pair_cache_flag_set=bool(raw[0x45]&1))


def check_country_table_binding(samples,table):
    require(type(table) is bytes and len(table) % 8 == 0,'Owned country pointer table shape')
    for sample in samples:
        for pair in sample['directional_pairs']:
            for role in ('actor','target'):
                item = pair[role]
                slot = item['slot']
                require(type(slot) is int and 0 < slot < len(table)//8,'Owned country pointer table slot')
                require(int(item['address'],16) == struct.unpack_from('<Q',table,slot*8)[0],
                        'Owned country table and sampled address differ')


def main():
    require(STATIC_REVIEW_SHA != 'PENDING_INDEPENDENT_STATIC_REVIEW','Independent static review required')
    fixed = {HOST:HOST_SHA,HOST_MANIFEST:'e7673b0e07c052788d6d2c6378939e176f57e79a45ea09888b957741b7370166',
        STATIC/'manifest.json':'27173b65e73e13f64c42c0891b7b299602a6a7944b2946f48907d17a3d9f7778',
        STATIC/'contract.json':'da506a026f1cbfa9c95929d43313283c12fc34ac073dfa711686a5e48f0ffab6',
        STATIC_REVIEW:STATIC_REVIEW_SHA}
    for path,sha in fixed.items():
        require(pin(path)['sha256'] == sha,'Fixed source/evidence changed')
    manifest = json.loads(read_bound(STATIC/'manifest.json',65536))
    for rel,expected in manifest['files'].items():
        path = (STATIC/rel).resolve()
        require(path.is_relative_to(STATIC.resolve()) and pin(path) == expected,'R23 selected file changed')
        fixed[path] = expected['sha256']
    for rel,expected in manifest['sources'].items():
        path = (ROOT/rel).resolve()
        require(path.is_relative_to(ROOT.resolve()) and pin(path) == expected,'R23 source changed')
        fixed[path] = expected['sha256']
    fixed[Path(__file__).resolve()] = pin(Path(__file__).resolve())['sha256']
    def sources():
        values = {path.relative_to(ROOT).as_posix():pin(path) for path in fixed}
        require(all(values[path.relative_to(ROOT).as_posix()]['sha256'] == sha for path,sha in fixed.items()),
                'Selected sources changed during capture')
        return values
    initial = sources()
    host = exact_load(HOST,HOST_SHA,'_frozen_host_for_direct_truce_flags')
    frozen = host.verify_manifest()
    OUT.mkdir(parents=True,exist_ok=True)
    host.write_new(OUT/'claim.json',dict(schema='EU4-DIRECT-TRUCE-FLAG-CLAIM/1',
        claimed_utc=datetime.now(timezone.utc).isoformat(),source_pins=initial,automatic_retry=False))
    sys.path.insert(0,str(ROOT))
    try:
        observer = host.load_local('bridge/diplomacy_effect_observer.py',frozen)
    finally:
        sys.path.pop(0)
    backend = observer.TagCommandBackend()
    identity = dict(pid=80340,creation='01dd5c075fcf8c26',session=secrets.token_hex(16),
        dll_sha256=backend.manifest['dll']['sha256'],manifest_sha256=backend.manifest_sha)
    result = dict(schema='EU4-DIRECT-PAIR-TRUCE-CACHE-CURRENT/1',status='unknown',identity=identity,
        identity_purpose='fresh read-only nonce; not an installed TAG/request session',
        captured_utc=datetime.now(timezone.utc).isoformat(),source_pins=initial,
        frozen_host_manifest_sha256=frozen['manifest_sha256'],pairs=list(PAIRS),samples=[],errors=[],
        precheck=None,postcheck=None,selected_rpm_budget=None,pure_RPM=True,
        accounting_scope='this_capture_only_not_historical_R19',native_game_calls=0,
        game_fields_written=0,hooks_installed=0,Frida_called=False,requests_published=0,saves=0,reloads=0,
        native_truce_helper_evaluated=False,linked_country_predicate_evaluated=False,
        truce_object_verified=False,expiry_verified=False,removed_state_verified=False,
        peace_completion_verified=False,new_API_effect_tested=False,native_ready=False,
        sender_authorized=False,lifetime_lease=False,atomic_snapshot=False,automatic_retry=False)
    started = time.perf_counter()
    try:
        with observer.RuntimeCapture(identity,backend) as cap:
            require(not any(Path(path).name.lower().startswith(('eu4_bridge_','eu4_pair_','eu4_spy_',
                'eu4_tag_command_','tag_diplomacy')) for _,path in cap.modules),'Unexpected research module')
            result['precheck'] = host.host_sample(cap,observer)
            r = observer.BudgetReader(AlignedPort(observer.HeldRPMPort(cap.held)))
            try:
                root = observer.roots(r,cap.base)
                wanted = {tag for pair in PAIRS for tag in pair}
                table = r.read(int(root['array'],16),root['count']*8)
                result['country_pointer_table_raw_hex'] = table.hex()
                selected = {}
                for slot,(address,) in enumerate(struct.iter_unpack('<Q',table)):
                    if not address:
                        continue
                    value = r.q(observer.ptr(address)+0x20)
                    tag_bytes = (value&0xffffff).to_bytes(3,'little')
                    if tag_bytes not in {tag.encode('ascii') for tag in wanted}:
                        continue
                    tag = tag_bytes.decode('ascii')
                    parsed_slot,_ = observer.full_handle(value,root['count'],tag=tag)
                    require(parsed_slot == slot and tag not in selected,'Selected country table identity mismatch')
                    selected[tag] = value
                require(set(selected) == wanted,'Selected current TAG unavailable')
                for _ in range(2):
                    current_root = observer.roots(r,cap.base)
                    require(current_root == root,'Country/date roots changed')
                    sample = dict(roots=current_root,selected_handles={k:hex(v) for k,v in selected.items()},
                        directional_pairs=[pair_sample(r,observer,cap.base,current_root,selected,*pair) for pair in PAIRS])
                    result['samples'].append(sample)
                require(result['samples'][0] == result['samples'][1],'Two direct pair projections differ')
                check_country_table_binding(result['samples'],table)
                result['selected_two_pass_equal'] = True
            except Exception as exc:
                result['errors'].append(dict(stage='selected',type=type(exc).__name__,message=str(exc)))
            finally:
                result['selected_rpm_budget'] = dict(calls=r.calls,bytes=r.bytes,largest=r.largest)
                result['postcheck'] = host.host_sample(cap,observer)
                require(result['postcheck'] == result['precheck'] and observer.pins() == cap.initial_pins
                        and host.verify_manifest() == frozen and sources() == initial,'Post guards changed')
        if not result['errors']:
            result['status'] = 'sampled_equal_direct_pair_cache_flags'
    except Exception as exc:
        result['errors'].append(dict(stage='host',type=type(exc).__name__,message=str(exc)))
    result['duration_ms_including_host_checks'] = round((time.perf_counter()-started)*1000,3)
    host.write_new(OUT/'capture.json',result)
    print(json.dumps(dict(output=str(OUT/'capture.json'),status=result['status'],errors=result['errors'],
        selected_rpm_budget=result['selected_rpm_budget'],native_game_calls=0,peace_completion_verified=False)))
    return 0 if result['status'] == 'sampled_equal_direct_pair_cache_flags' else 2


if __name__ == '__main__':
    raise SystemExit(main())
