"""R24 retained-file audit only. Never import producers or access a process."""
import argparse
import ast
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT/'work/reports/war-peace-api-20261015-r24-direct-truce-current'
PREP = ROOT/'work/reports/war-peace-api-20261015-r24-direct-truce-source-prep'
READY = ROOT/'work/reports/direct-truce-current-source-review-20261015-r1'
STATIC_REVIEW = ROOT/'work/reports/war-peace-api-20261015-r23-independent-review/war'
HOST = ROOT/'work/candidates/frida-entry-observer-1375-v1'
PRODUCER = ROOT/'work/capture_direct_truce_flags_20261015.py'
OUT = ROOT/'work/reports/direct-truce-current-live-review-20261015-r1'
FROZEN_LOADER = ROOT/'work/candidates/v19-spy-real-client-r2-1375'
PAIRS = [('FRA','ENG'), ('ENG','FRA'), ('TUR','HUN'), ('HUN','TUR'),
         ('TUR','VEN'), ('VEN','TUR'), ('MOS','NOV'), ('NOV','MOS')]


def pin(path):
    count = 0; h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(65536):
            count += len(chunk); h.update(chunk)
    return {'bytes': count, 'sha256': h.hexdigest()}


def load(path):
    assert path.stat().st_size <= 1024*1024
    def unique(pairs):
        out = {}
        for key, value in pairs:
            assert key not in out, 'Duplicate JSON key'; out[key] = value
        return out
    def invalid(_):
        raise ValueError('Nonfinite JSON constant')
    value = json.loads(path.read_bytes().decode('utf-8'), object_pairs_hook=unique, parse_constant=invalid)
    nodes = [value]; visited = 0
    while nodes:
        node = nodes.pop(); visited += 1; assert visited <= 32000
        if type(node) is dict:
            assert len(node) <= 1024 and all(type(k) is str for k in node); nodes.extend(node.values())
        elif type(node) is list:
            assert len(node) <= 4096; nodes.extend(node)
        elif type(node) is float:
            assert math.isfinite(node)
        else:
            assert node is None or type(node) in (str, int, bool)
    return value  # General Python host journal: finite floats and full64 handles are valid.


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2)+'\n')


def address(text, size=8):
    assert type(text) is str and re.fullmatch('0x[0-9a-f]+', text)
    value = int(text, 16)
    assert type(size) is int and 0 < size <= 65536 and 0x10000 <= value < value+size <= 2**47
    assert size < 8 or value % 8 == 0
    return value


def owned_hex(text, size):
    assert type(text) is str and re.fullmatch('[0-9a-f]{'+str(size*2)+'}', text)
    return bytes.fromhex(text)


def handle(text, tag, count):
    assert type(text) is str and re.fullmatch('0x[0-9a-f]+', text)
    value = int(text, 16); slot = value >> 32 & 0xffff
    assert 0 < value < 2**64 and value >> 56 != 0
    assert (value >> 48 & 255) == (value >> 24 & 255) == 0
    assert 0 < slot < min(count,32768)
    assert (value & 0xffffff).to_bytes(3,'little') == tag.encode('ascii')
    return value, slot


def check():
    m = load(OUT/'manifest.json'); assert m['sealed'] is True
    for name, wanted in m['source_pins'].items():
        assert pin(ROOT/name) == wanted, name
    for name, wanted in m['selected_external_pins'].items():
        assert pin(Path(name)) == wanted, name
    print(json.dumps({'status':'pass', 'local_pins':len(m['source_pins']),
        'selected_external_pins':len(m['selected_external_pins']), 'process_accessed':False,
        'producer_executed':False, 'tests_reexecuted':False}))


def main():
    assert pin(LIVE/'capture.json') == {'bytes':48671,'sha256':'153d4ac8ae4042dde28dbdf70abe77e891737c507c8258aa906275d0e49a5f1e'}
    assert pin(PRODUCER) == {'bytes':12011,'sha256':'1677ccf7f03b93c44d3bb5313bae3350605f51c58855f381f5b516504f4bb904'}
    assert pin(READY/'independent-source-ready.json') == {'bytes':4605,'sha256':'98b673b5e7c823d01b85988839ad1c7479f20439e8254be789b510e740be474b'}
    assert pin(HOST/'host-manifest.json') == {'bytes':43987,'sha256':'e7673b0e07c052788d6d2c6378939e176f57e79a45ea09888b957741b7370166'}
    result = load(LIVE/'capture.json'); host = load(HOST/'host-manifest.json')
    ready = load(READY/'independent-source-ready.json'); claim = load(LIVE/'claim.json')
    invocation = load(PREP/'root-invocation-claim.json'); selected = {}
    def add(path, wanted=None):
        actual = pin(path)
        assert wanted is None or wanted == actual, str(path)
        assert path.resolve().is_relative_to(ROOT.resolve())
        key = path.relative_to(ROOT).as_posix()
        assert key not in selected or selected[key] == actual
        selected[key] = actual
    assert host['sealed'] is True and len(host['source_pins']) == 215 and len(host['selected_external_pins']) == 11
    for name, wanted in host['source_pins'].items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        add(ROOT/name, wanted)
    for name, wanted in host['selected_external_pins'].items():
        assert Path(name).is_absolute() and pin(Path(name)) == wanted, name
    assert ready['sealed'] is True and ready['findings'] == []
    assert ready['status'] == 'source_ready_for_root_one_readonly_capture_at_1677_pins'
    source_review = load(READY/'manifest.json')
    assert source_review['sealed'] is True and len(source_review['source_pins']) == 26
    for name, wanted in source_review['source_pins'].items(): add(ROOT/name, wanted)
    assert len(result['source_pins']) == 18
    for name, wanted in result['source_pins'].items(): add(ROOT/name, wanted)
    assert claim['schema'] == 'EU4-DIRECT-TRUCE-FLAG-CLAIM/1'
    assert claim['source_pins'] == result['source_pins'] and claim['automatic_retry'] is False
    assert datetime.fromisoformat(claim['claimed_utc']) < datetime.fromisoformat(result['captured_utc'])
    assert invocation['automatic_retry'] is False and invocation['native_game_calls'] == 0
    assert set(invocation['source_checks']) == {str(PRODUCER.relative_to(ROOT)),str((READY/'independent-source-ready.json').relative_to(ROOT))}
    for name, wanted in invocation['source_checks'].items(): assert pin(ROOT/name)['sha256'] == wanted
    assert result['schema'] == 'EU4-DIRECT-PAIR-TRUCE-CACHE-CURRENT/1'
    assert result['status'] == 'sampled_equal_direct_pair_cache_flags' and result['errors'] == []
    assert result['identity']['pid'] == 80340 and type(result['identity']['pid']) is int
    assert result['identity']['creation'] == '01dd5c075fcf8c26'
    assert re.fullmatch('[0-9a-f]{32}',result['identity']['session'])
    assert result['identity']['dll_sha256'] == '6a0683dacc069b743979b7442ad02205f13e8be972ce5c4f26a46fd9b530ed2a'
    assert result['identity']['manifest_sha256'] == 'd4b3069cfac70cf9ff8e1270733ad64592c3d545a6d005fd0ed8b26c6070728a'
    assert result['identity_purpose'] == 'fresh read-only nonce; not an installed TAG/request session'
    assert datetime.fromisoformat(result['captured_utc']).tzinfo is not None
    assert result['frozen_host_manifest_sha256'] == pin(HOST/'host-manifest.json')['sha256']
    assert result['pairs'] == [list(pair) for pair in PAIRS]
    assert result['selected_two_pass_equal'] is True
    assert len(result['samples']) == 2 and result['samples'][0] == result['samples'][1]
    pre = result['precheck']; assert pre == result['postcheck']
    base = address(pre['prefix_address'],32)-0x10a6ec0
    assert base == 0x7ff7034b0000 and base % 65536 == 0
    table = owned_hex(result['country_pointer_table_raw_hex'],11040)
    pointers = list(struct.unpack('<1380Q',table))
    assert sum(bool(value) for value in pointers) == 1380
    table_replay = []; raw_bytes = len(table)
    for sample in result['samples']:
        roots = sample['roots']; assert roots == pre['roots']
        assert roots['count'] == roots['capacity'] == 1380
        for name in ('game','database','array','server','pause'): address(roots[name])
        assert roots['date'] == 56461512 and roots['manual_pause'] == 1
        assert roots['reset'] == roots['load_source'] == roots['recalculating'] == roots['ironman'] == roots['selector'] == 0
        assert roots['alternate_player'] == 0x2d2d2d
        assert handle(hex(roots['current_player']),'FRA',1380)[0] == roots['current_player']
        assert set(sample['selected_handles']) == {'FRA','ENG','TUR','HUN','VEN','MOS','NOV'}
        assert len(sample['directional_pairs']) == 8
        for (actor_tag,target_tag), pair in zip(PAIRS,sample['directional_pairs']):
            items = {}
            for role, tag in (('actor',actor_tag),('target',target_tag)):
                item = pair[role]; assert item['tag'] == tag
                full, slot = handle(item['handle'],tag,1380)
                assert type(item['slot']) is int and item['slot'] == slot
                assert item['handle'] == sample['selected_handles'][tag]
                a = address(item['address'],0x28); assert pointers[slot] == a
                raw = owned_hex(item['header_raw_hex'],0x28); raw_bytes += len(raw)
                assert struct.unpack_from('<QI',raw) == (base+0x1c574a0,357)
                assert struct.unpack_from('<Q',raw,0x20)[0] == full
                items[role] = (a, full, slot)
            actor, target = items['actor'], items['target']
            rr = address(pair['relation_root'],0x30)
            record = address(pair['relation_record'],0x48)
            assert rr == actor[0]+0x14f8
            rootraw = owned_hex(pair['root_raw_hex'],0x30)
            rowraw = owned_hex(pair['record_raw_hex'],0x48); raw_bytes += len(rootraw)+len(rowraw)
            assert struct.unpack_from('<QI',rootraw) == (base+0x1c4f5f8,357)
            assert struct.unpack_from('<Q',rootraw,0x10)[0] == actor[0]
            begin,end,capacity = struct.unpack_from('<QQQ',rootraw,0x18)
            assert all(value % 8 == 0 for value in (rr,record,begin,end,capacity))
            assert 0x10000 <= begin <= end <= capacity < 2**47
            assert (end-begin) % 0x48 == (capacity-begin) % 0x48 == 0
            assert capacity-begin <= 4096*0x48
            assert record == begin+target[2]*0x48 and record+0x48 <= end
            assert struct.unpack_from('<QQQ',rowraw) == (rr,actor[1],target[1])
            assert pair['field_offset'] == '0x45' and type(pair['mask']) is int and pair['mask'] == 1
            assert type(pair['raw_byte45']) is int and pair['raw_byte45'] == rowraw[0x45]
            assert type(pair['direct_pair_cache_flag_set']) is bool
            assert pair['direct_pair_cache_flag_set'] is bool(rowraw[0x45]&1)
            table_replay.append({'actor':actor_tag,'target':target_tag,'actor_slot':actor[2],
                'target_slot':target[2],'raw_byte45':rowraw[0x45],'mask1_set':bool(rowraw[0x45]&1)})
    assert raw_bytes == 14240
    assert [item['raw_byte45'] for item in table_replay[:8]] == [24,0,0,0,0,8,28,24]
    assert all(item['mask1_set'] is False for item in table_replay)
    budget_breakdown = {'roots_three':{'calls':54,'bytes':315}, 'pointer_table':{'calls':1,'bytes':11040},
        'nonnull_table_handle_scan':{'calls':1380,'bytes':11040}, 'sixteen_pair_samples':{'calls':160,'bytes':6272}}
    assert sum(item['calls'] for item in budget_breakdown.values()) == result['selected_rpm_budget']['calls'] == 1595
    assert sum(item['bytes'] for item in budget_breakdown.values()) == result['selected_rpm_budget']['bytes'] == 28667
    assert result['selected_rpm_budget']['largest'] == 11040
    assert pre['process_identity_checked'] is pre['module_set_equal'] is True
    assert pre['rpm_budget'] == {'calls':46,'bytes':300,'largest':32}
    assert pre['prefix32_hex'] == '4c89442418555357488d6c24b04881ec50010000488b159d8f2901488bf9440f'
    outer = address(pre['outer']); address(pre['prefix_address'],32)
    assert [struct.unpack('<Q',owned_hex(value,8))[0] for value in pre['outer_vtable_hex']] == [base+0x1c48bf8,base+0x1c48c80]
    assert struct.unpack('<Q',owned_hex(pre['children_hex'][0],8))[0] == address(pre['roots']['server'])
    assert pre['children_hex'][1:] == ['00','0000000000000000','0000000000000000','00']
    assert result['duration_ms_including_host_checks'] == 1691.943 and type(result['duration_ms_including_host_checks']) is float
    for name in ('Frida_called','atomic_snapshot','automatic_retry','expiry_verified','lifetime_lease',
        'linked_country_predicate_evaluated','native_ready','native_truce_helper_evaluated','new_API_effect_tested',
        'peace_completion_verified','removed_state_verified','sender_authorized','truce_object_verified'):
        assert result[name] is False,name
    for name in ('game_fields_written','hooks_installed','native_game_calls','reloads','requests_published','saves'):
        assert type(result[name]) is int and result[name] == 0,name
    assert result['pure_RPM'] is True and result['accounting_scope'] == 'this_capture_only_not_historical_R19'
    # Source-only control-flow checks: no import/compile/exec of any producer.
    source = PRODUCER.read_text(encoding='utf-8'); tree = ast.parse(source)
    main_node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == 'main')
    outer_try = next(n for n in main_node.body if isinstance(n,ast.Try) and any(isinstance(v,ast.With) for v in n.body))
    assert isinstance(outer_try.body[0],ast.With) and isinstance(outer_try.body[1],ast.If)
    assert len(outer_try.handlers) == 1 and outer_try.handlers[0].type.id == 'Exception'
    assert "if not result['errors']:\n            result['status'] = 'sampled_equal_direct_pair_cache_flags'" in source
    selected_try = next(n for n in ast.walk(outer_try.body[0]) if isinstance(n,ast.Try) and n.finalbody)
    assert selected_try.handlers[0].type.id == 'Exception'
    assert any(isinstance(n,ast.For) and isinstance(n.iter,ast.Call) and n.iter.func.id == 'range'
               and len(n.iter.args) == 1 and n.iter.args[0].value == 2 for n in selected_try.body)
    for fragment in ("check_country_table_binding(result['samples'],table)",
        "result['postcheck'] == result['precheck'] and observer.pins() == cap.initial_pins",
        "host.verify_manifest() == frozen and sources() == initial", "host.write_new(OUT/'claim.json'",
        "0 < slot < len(table)//8", "value % 8 == 0", "size < 8 or address % 8 == 0"):
        assert fragment in source,fragment
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert not attrs.intersection({'attach','spawn','inject','instrument_with_frida','WriteProcessMemory',
        'CreateRemoteThread','SuspendThread','SetThreadContext','publish','submit'})
    observer = (ROOT/'bridge/diplomacy_effect_observer.py').read_text()
    host_source = (HOST/'capture_once.py').read_text()
    assert "except BaseException:\n            self.held.close()" in observer
    assert "def __exit__(self, *unused):\n        if self.held:\n            self.held.close()" in observer
    assert "cap.held.identity_check()" in host_source and "cap.held.modules() == cap.modules" in host_source
    assert "first == second and first['manual_pause'] == 1" in host_source
    # Selected old held-reader close implementation is bound by its literal launcher inventory.
    launcher = FROZEN_LOADER/'launcher.py'; inventory_path = FROZEN_LOADER/'inventory.json'
    assert pin(launcher)['sha256'] == 'a7944c63e044e195a242b417afbea27c001ef2cae1f9d1a721bf3b83352845fe'
    assert pin(inventory_path)['sha256'] == 'fe47d0dc016fbaa523d0f5b0010cd879fb57f7dcd33fd4edce39800b9c0b5e9d'
    inventory = load(inventory_path)
    old_reader = FROZEN_LOADER/'readonly.py'
    assert pin(old_reader)['sha256'] == inventory['files'][old_reader.relative_to(ROOT).as_posix()]
    close_source = old_reader.read_text()
    assert "OpenProcess(0x0400|0x1000|0x0010|0x00100000,False,identity['pid'])" in close_source
    assert 'if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None' in close_source
    report = {'schema':'EU4-DIRECT-TRUCE-CURRENT-INDEPENDENT-LIVE-FILE-AUDIT/1',
        'status':'pass_selected_directional_direct_cache_only','findings':[],
        'capture':pin(LIVE/'capture.json'),'producer':pin(PRODUCER),'source_ready':pin(READY/'independent-source-ready.json'),
        'verified_host_local_pins':215,'verified_selected_external_pins':11,'verified_source_review_pins':26,
        'verified_capture_source_pins':18,'claim_source_pins_equal':True,'exclusive_claim_precedes_capture':True,
        'pid':80340,'creation':'01dd5c075fcf8c26','installed_TAG_session':False,
        'two_pass_equal':True,'raw_pointer_table_bytes':11040,'raw_pointer_table_entries':1380,
        'nonnull_table_entries':1380,'selected_distinct_countries':7,
        'selected_country_addresses_match_retained_pointer_table':True,'typed_country_complete_handles':True,
        'typed_relation_roots_full_pair_handles_and_bounds':True,'directions':table_replay[:8],
        'selected_total_reads':1595,'selected_total_bytes':28667,'selected_max_read':11040,
        'selected_accounting_breakdown':budget_breakdown,'selected_retained_raw_bytes':14240,
        'selected_unretained_read_bytes':28667-14240,
        'host_pre_post_projection_equal':True,'host_each_counter':pre['rpm_budget'],
        'host_each_retained_raw_bytes':74,'duration_ms_including_host_checks':1691.943,
        'producer_flow':{'source_guard_before_verified_import':True,'fixed_host_graph_guard_before_and_after':True,
            'selected_exception_records_unknown':True,'postchecks_in_finally':True,'success_only_after_normal_with_exit':True,
            'RuntimeCapture_enter_failure_closes':True,'RuntimeCapture_exit_calls_Held_close':True,
            'CloseHandle_return_checked':False,'independent_OS_handle_close_proof':False},
        'R23_precision_scope':{'index_formula':'Only validated positive slot<min(count,32768); no malformed negative-slot interpretation.',
            'alignment':'R24 independent AlignedPort checks selected size>=8 before underlying RPM; frozen reader remains canonical-only.',
            'helper_evaluated':False,'unfollowed_callees':['0x2f1590','0x40a6d0','0x7ae260']},
        'limits':['All8 direct-cache mask1 values are false. This does not prove complete absence of truce, helperfalse, expiry or peace completion.',
            'Fulltable raw is one initial table snapshot; selected pass addresses are checked against it. The entire table is not independently reread twice.',
            'All16 selected pair/country/root records and the full initial table replay from ownedraw. Nonselected scanned handles and all intermediate headers/rechecks were not retained.',
            'Raw fullrelation bytes do not assign semantics to other masks or relation+30 deadline; object/index/expiry/dateunits/removed remain unknown.',
            'Host each46reads300B retains74B raw. Complete roots/PE/modulelist/identity and normal close are fixed-producer witnesses, not complete raw or independent OS replay.',
            'RuntimeCapture loaded-image setup includes reads outside selected1595 and twohost46 counters. This is not exhaustive process-read accounting.',
            'Current215/11 selected files and26 source-review pins match. The old heldreader is additionally checked against its pinnedloader/inventory; this audit does not expand that entire inventory or all Python/REA dependencies.',
            'Equal ordered external passes may miss transient mutation, ABA or release. No reference/lock/lease/atomicity is acquired.',
            'This capture is pureRPM, separate from historicalR19 onebodycall. No new request, save, reload, hook, Frida or game nativecall occurred on the selected source path.',
            'Auditor only reads files, parses JSON/AST and reconstructs bytes. No capture, authorproducer, oldtests, process, Frida/REA or native execution.'],
        'pure_RPM':True,'temporary_code_hook':False,'native_game_calls':0,'game_fields_written':0,
        'requests_published':0,'saves':0,'reloads':0,'new_API_effects':0,'truce_helper_result_verified':False,
        'truce_object_verified':False,'expiry_verified':False,'peace_completion_verified':False,
        'native_ready':False,'sender_authorized':False,'lifetime_lease':False,'atomic_snapshot':False,
        'process_accessed_by_auditor':False,'tests_reexecuted':False,'producer_executed':False}
    assert not OUT.exists(); OUT.mkdir(parents=True)
    write_new(OUT/'independent-file-audit.json',report)
    write_new(OUT/'independent-file-audit.md',
        '# R24 方向性停战缓存实采文件审计\n\n'
        '通过。完整11040B国家指针表与7个选中国家的地址、完整handle、country/root类型及16个方向性关系记录相符；双遍投影一致。'
        'FRA→ENG、ENG→FRA、TUR→HUN、HUN→TUR、TUR→VEN、VEN→TUR、MOS→NOV、NOV→MOS的byte45为24/0/0/0/0/8/28/24，mask1均false。\n\n'
        '宿主215本地/11所选外部、26源审pin与18本次来源pin均核对通过。1595读/28667B预算可重算，14240B所选raw留存；'
        '宿主前后投影一致，1691.943ms含hostchecks。成功仅在with正常退出后提交；CloseHandle返回未留存且旧实现未检查，只确认关闭调用路径。\n\n'
        '保留R23范围：合法正slot、独立新alignment守卫；helper及3callee未调用。8个cachefalse不能称完整无truce、helperfalse或议和完成。'
        '无新采样/进程/Frida/native/旧测试；所有nativeReady/lease/因果门保持false。\n')
    for path in (LIVE/'capture.json',LIVE/'claim.json',PREP/'root-invocation-claim.json',READY/'manifest.json',
        STATIC_REVIEW/'manifest.json',launcher,inventory_path,old_reader,Path(__file__).resolve(),
        OUT/'independent-file-audit.json',OUT/'independent-file-audit.md'):
        add(path)
    write_new(OUT/'manifest.json',{'schema':'EU4-DIRECT-TRUCE-CURRENT-INDEPENDENT-LIVE-AUDIT-MANIFEST/1',
        'sealed':True,'source_pins':dict(sorted(selected.items())), 'selected_external_pins':host['selected_external_pins'],
        'native_ready':False,'lifetime_lease':False})
    print(json.dumps({'status':report['status'],'report':pin(OUT/'independent-file-audit.json'),
        'manifest':pin(OUT/'manifest.json'),'local_pins':len(selected),'selected_external_pins':11}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--check',action='store_true')
    check() if parser.parse_args().check else main()
