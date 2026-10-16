"""Fixed five-action manual-UI batch evidence review. Files and pure data only."""
import argparse
import ast
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORDER = ('corrupt_officials', 'sabotage_reputation', 'sow_discontent',
         'slander_merchants', 'sabotage_recruitment')
PID = 38232
CREATION = '01dd56e0cbe2c7f7'
WORLD = 0x1a0cb39c020
DATE = 56456976
INITIAL_SHA = '21d40a44976fdc053c575740442bd99180b192ec87210c27e9989247270de81c'
INITIAL_PATH = 'work/runtime/spy-test-setup-ro-38232-after_fixture.json'
FINAL_PATH = 'work/runtime/spy5-ui-batch-final-ro-38232.json'
JOURNAL_PATH = 'work/runtime/spy5-ui-batch-38232.jsonl'
FALSE_OUTPUT = ('native_request_receipt_verified', 'native_call_authorized', 'runtime_verified',
                'execution_verified', 'individual_effect_verified', 'request_causality_verified',
                'actual_individual_cost_verified', 'strict_single_player_verified',
                'world_epoch_verified', 'object_lifetime_verified', 'whole_world_unchanged_verified',
                'save_reload_verified', 'production_ready')
MAX_CENSUS = 16 * 1024 * 1024
MAX_JOURNAL = 65536
_DEPS = None
PINS_SHA = '4d5c35619e41e81abf849826e3a5318541305f68f294f645d2d0207db0d057b6'

def require(condition, message):
    if not condition:
        raise ValueError(message)

def integer(value, lo=0, hi=2**64-1):
    require(type(value) is int and lo <= value <= hi, 'strict bounded integer')
    return value

def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys.split()), 'exact object fields')

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def same(left, right, message):
    require(canonical(left) == canonical(right), message)

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(262144), b''):
            h.update(block)
    return h.hexdigest()

def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'SHA256')
    return value

def decode(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, 'duplicate JSON key')
            out[key] = value
        return out
    def nonfinite(value):
        raise ValueError('nonfinite JSON')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)

def bounded(path, limit):
    require(path.is_file() and not path.is_symlink(), 'regular file')
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    require(len(raw) <= limit, 'file budget')
    return raw

def import_fixed(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(Path(module.__file__).resolve() == path.resolve(), 'module origin')
    require(module.ROOT == ROOT, 'module root')
    return module

def verify_sources():
    raw = bounded(HERE/'input-pins.json', 65536)
    require(hashlib.sha256(raw).hexdigest() == PINS_SHA, 'fixed source index')
    pins = decode(raw)
    require(type(pins) is dict and 1 <= len(pins) <= 64, 'source inventory budget')
    for path, value in pins.items():
        require(type(path) is str and not Path(path).is_absolute() and '..' not in Path(path).parts,
                'source relative path')
        require(sha(ROOT/path) == digest(value), 'source pin: '+path)
    return pins

def dependencies():
    global _DEPS
    if _DEPS is None:
        verify_sources()
        full = import_fixed('_spy5_full', 'work/candidates/spy-dense-full-observer-r2-1375/observer.py')
        spy, dense = full.dependencies()
        # The producer is only parsed. Its main/process/installed-config methods never run.
        tree = ast.parse((ROOT/'work/sample_spy_test_setup_ro_38232_1375.py').read_text('utf-8'))
        producer_pins = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                             and any(isinstance(t, ast.Name) and t.id == 'PINS' for t in n.targets))
        _DEPS = full, spy, dense, producer_pins
    return _DEPS

def budget(record, trace, max_bytes, max_calls, max_single):
    exact(record, 'bytes calls max_bytes max_calls')
    integer(record['max_bytes'], max_bytes, max_bytes)
    integer(record['max_calls'], max_calls, max_calls)
    n = integer(record['calls'], 1, max_calls)
    count = integer(record['bytes'], 1, max_bytes)
    if trace is None:
        return count
    require(type(trace) is list and len(trace) == n, 'trace count')
    total = 0
    for row in trace:
        exact(row, 'address size sha256')
        address = integer(row['address'], 0x10000, 0x7fffffffffff)
        width = integer(row['size'], 1, max_single)
        require(address+width <= 0x800000000000, 'trace address span')
        digest(row['sha256']); total += width
    require(total == count, 'trace byte total')
    return count

def dense_snapshot(snapshot, base, actor):
    exact(snapshot, 'cache_state base_milli transform_root transform aggregate status')
    integer(snapshot['cache_state'], 2, 2)
    cost = integer(snapshot['base_milli'], 0, 21474831)
    full, spy, dense, _ = dependencies()
    spy.ptr(snapshot['transform_root']); integer(snapshot['transform'], 0, 0)
    require(snapshot['status'] == 'dense_null_transform_arithmetic_candidate', 'known dense branch only')
    a = snapshot['aggregate']
    exact(a, 'address vtable type_marker dense vector_vtable data capacity count selected_record')
    require(spy.ptr(a['address']) == actor+0x28d0, 'dense owner')
    require(spy.ptr(a['vtable']) == base+0x1c42770, 'aggregate vtable')
    integer(a['type_marker'], 0x165, 0x165); integer(a['dense'], 1, 1)
    require(spy.ptr(a['vector_vtable']) == base+0x1c37fa0, 'vector vtable')
    data = spy.ptr(a['data']); count = integer(a['count'], 0x262, 4096)
    integer(a['capacity'], count, 4096)
    require(data+count*8 <= 0x800000000000, 'dense array span')
    selected = a['selected_record']; exact(selected, 'address id value_milli')
    require(spy.ptr(selected['address']) == data+0x261*8, 'selected dense address')
    ident = integer(selected['id'], -2**31, 2**31-1)
    value = integer(selected['value_milli'], -1000, 1000000)
    require(ident == 0x261 or (ident == 0x286 and value == 0), 'selected dense identity')
    return integer(cost*(1000+value)//1000, 0, 21474831)

def spy_capture(record, family):
    _, spy, _, _ = dependencies()
    exact(record, 'profile static_report_sha256 snapshot two_pass_equal selected read_budget trace source_kind '+
          ' '.join(spy.FALSE_CLAIMS))
    require(record['profile'] == 'spy_modifier_selected_ro_1375_1' and
            record['static_report_sha256'] == spy.REPORT_SHA, 'spy profile')
    require(record['source_kind'] == 'injected_readonly_reader_identity_not_attested', 'nested source')
    require(record['two_pass_equal'] is True, 'nested two passes')
    for key in spy.FALSE_CLAIMS:
        require(record[key] is False, 'unsupported claim: '+key)
    spy.inspect(record['snapshot'])
    s = record['snapshot']
    require(s['family'] == family and s['target'] == 'ENG', 'spy family/target')
    same(record['selected'], spy.selected(s), 'recomputed selection')
    budget(record['read_budget'], record['trace'], spy.MAX_TOTAL, spy.MAX_READS, spy.MAX_SINGLE)
    require(record['selected']['unknown_objects_or_selected_semantics'] is False, 'unknown modifier')
    return s

def full_report(record, family):
    full, spy, dense, _ = dependencies()
    flags = ('native_calls native_legality_verified actual_cost_verified individual_effect_verified '+
             'strict_single_player_verified world_epoch_verified paused_verified cache_freshness_verified '+
             'object_lifetime_verified production_ready').split()
    exact(record, 'schema_version profile family before dense after full_envelope_equal cost_binding '+
          'source_kind read_budget source_pins process '+' '.join(flags))
    integer(record['schema_version'], 2, 2)
    require(record['profile'] == 'spy_dense_full_ro_1375_2' and record['family'] == family, 'full profile')
    require(record['source_kind'] == 'held_process_readonly', 'held producer only')
    require(record['full_envelope_equal'] is True, 'full equal flag')
    for key in flags:
        require(record[key] is False, 'unsupported full claim: '+key)
    same(record['source_pins'], full.PINS, 'full source pins')
    before = spy_capture(record['before'], family); after = spy_capture(record['after'], family)
    same(before, after, 'full before/after snapshot equality')
    z = before['identity']
    require(z['game'] == WORLD and z['date'] == DATE, 'fixed world/date')
    require(before['capability']['raw'] == 1, 'observed capability must be present')
    process = record['process']
    exact(process, 'identity path disk_exe_sha256 loaded_full_image_hash_verified rights')
    held = process['identity']; exact(held, 'pid creation_filetime exit_filetime module_base')
    integer(held['pid'], PID, PID); integer(held['exit_filetime'], 0, 0)
    require(type(held['creation_filetime']) is str and held['creation_filetime'] == CREATION, 'held creation')
    require(spy.ptr(held['module_base']) == z['base'], 'held module base')
    require(type(process['path']) is str and process['path'] == str((ROOT.parent/'eu4.exe').resolve()), 'EXE path')
    require(process['disk_exe_sha256'] == spy.EXE_SHA and process['loaded_full_image_hash_verified'] is False,
            'disk/full-loaded hash distinction')
    same(process['rights'], ['PROCESS_QUERY_INFORMATION', 'PROCESS_VM_READ'], 'RO rights')
    d = record['dense']
    exact(d, 'schema_version family base actor before after local_two_pass_equal final_milli_candidate claims read_bytes reads')
    integer(d['schema_version'], 1, 1)
    require(d['family'] == family and spy.ptr(d['base']) == z['base'] and
            spy.ptr(d['actor']) == z['countries']['FRA']['address'], 'dense context')
    require(d['local_two_pass_equal'] is True, 'dense two-pass flag')
    values = [dense_snapshot(d[side], d['base'], d['actor']) for side in ('before', 'after')]
    same(d['before'], d['after'], 'dense snapshots typed equality')
    require(integer(d['final_milli_candidate'], 0, dense.MAX_COST) == values[0] == values[1], 'dense arithmetic')
    exact(d['claims'], ' '.join(dense.FALSE_CLAIMS))
    require(all(d['claims'][key] is False for key in dense.FALSE_CLAIMS), 'dense unsupported claims')
    require(type(d['reads']) is list and 1 <= len(d['reads']) <= dense.MAX_READS, 'dense trace budget')
    budget(dict(bytes=d['read_bytes'], calls=len(d['reads']), max_bytes=dense.MAX_BYTES,
                max_calls=dense.MAX_READS), d['reads'], dense.MAX_BYTES, dense.MAX_READS, dense.MAX_SINGLE)
    common1 = full.bind_cost(before['cost'], d['before']); common2 = full.bind_cost(after['cost'], d['after'])
    same(common1, common2, 'observed common fields')
    binding = record['cost_binding']
    exact(binding, 'observed_common_fields before_and_after_equal same_address_value_aba_excluded')
    same(binding['observed_common_fields'], common1, 'binding field list')
    require(binding['before_and_after_equal'] is True and binding['same_address_value_aba_excluded'] is False,
            'binding flags')
    outer = budget(record['read_budget'], None, full.MAX_BYTES, full.MAX_CALLS, 65536)
    require(outer >= record['before']['read_budget']['bytes']+record['after']['read_budget']['bytes']+d['read_bytes'],
            'outer includes nested payload')
    return before, d['before'], values[0], process

def census(record, phase):
    _, _, _, producer_pins = dependencies()
    common = ('kind phase pid creation expected_raw_date source_pins spy_reports subject_report diagnostic_report '+
              'game_native_calls game_memory_written individual_effect_verified production_ready group_atomic '+
              'actual_cost_verified status world')
    # References are retained hashed provenance, never used to invent a missing sample.
    extra = 'initial_reference_sha256'
    if phase == 'after_ui_spy_batch':
        extra += ' ui_journal_sha256 setup_helper_sha256 capture_helper_sha256 capture_scope native_request_receipt'
    exact(record, common+' '+extra)
    for key in ('initial_reference_sha256',):
        digest(record[key])
    if phase == 'after_ui_spy_batch':
        require(record['initial_reference_sha256'] == INITIAL_SHA, 'final references exact initial census')
        digest(record['ui_journal_sha256'])
        pins = verify_sources()
        require(record['setup_helper_sha256'] == pins['work/sample_spy_test_setup_ro_38232_1375.py'] and
                record['capture_helper_sha256'] == pins['work/sample_spy5_ui_batch_final_ro_38232_1375.py'],
                'capture producer sources')
        require(record['capture_scope'] == 'read_only_final_after_manual_ui_batch' and
                record['native_request_receipt'] is False, 'capture-only scope')
    require(record['kind'] == 'fixed_spy_mod_setup_ro_census' and record['phase'] == phase and
            record['status'] == 'captured', 'completed explicit census phase')
    integer(record['pid'], PID, PID); integer(record['world'], WORLD, WORLD)
    integer(record['expected_raw_date'], DATE, DATE)
    require(type(record['creation']) is str and record['creation'] == CREATION, 'census creation')
    for key in ('game_native_calls','game_memory_written','individual_effect_verified','production_ready',
                'group_atomic','actual_cost_verified'):
        require(record[key] is False, 'census false claim')
    same(record['source_pins'], producer_pins, 'producer source pins')
    exact(record['spy_reports'], ' '.join(ORDER))
    entries = {name:full_report(record['spy_reports'][name], name) for name in ORDER}
    first = entries[ORDER[0]]
    for value in entries.values():
        for key in ('identity','modifiers'):
            same(value[0][key], first[0][key], 'cross-family common '+key)
        same(value[3], first[3], 'cross-family held identity')
        require(value[0]['cost']['network_centipoints'] == first[0]['cost']['network_centipoints'],
                'cross-family network')
        for key in ('relations','record','owner','counterpart','cache_state','transform_root','transform','aggregate'):
            same(value[0]['cost'][key], first[0]['cost'][key], 'cross-family cost context '+key)
        same({k:v for k,v in value[1].items() if k!='base_milli'},
             {k:v for k,v in first[1].items() if k!='base_milli'}, 'cross-family dense context')
    require(len({x[0]['registry']['definition'] for x in entries.values()}) == 5, 'five distinct definitions')
    # Ancillary records are not used to authenticate selected spy state/effects.
    require(type(record['subject_report']) is dict and type(record['diagnostic_report']) is dict,
            'producer ancillary records retained')
    return entries

def journal(rows):
    require(type(rows) is list and len(rows) == 11, 'exact start+five intent/confirmation pairs')
    previous = None
    for index, row in enumerate(rows):
        keys = ('event family note recorded_utc pid creation world initial_sha256 actor target source '+
                'native_request_receipt individual_effect_verified production_ready')
        exact(row, keys+(' plan' if index == 0 else ''))
        integer(row['pid'], PID, PID)
        require(row['creation'] == CREATION and row['world'] == hex(WORLD), 'journal identity')
        require(row['actor'] == 'FRA' and row['target'] == 'ENG' and row['initial_sha256'] == INITIAL_SHA,
                'journal pair/initial')
        require(row['source'] == 'manual_game_ui_observation', 'manual UI source only')
        for key in ('native_request_receipt','individual_effect_verified','production_ready'):
            require(row[key] is False, 'manual journal no native/effect authority')
        require(type(row['note']) is str and len(row['note']) <= 1024, 'note budget')
        text = row['recorded_utc']
        require(type(text) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?\+00:00', text),
                'canonical UTC timestamp')
        stamp = datetime.fromisoformat(text)
        require(previous is None or stamp >= previous, 'journal order time')
        previous = stamp
        if index == 0:
            require(row['event'] == 'start' and row['family'] is None, 'journal start')
            same(row['plan'], list(ORDER), 'exact ordered UI plan')
        else:
            require(row['event'] == ('intent' if index%2 else 'ui_confirmed') and
                    row['family'] == ORDER[(index-1)//2], 'exact ordered UI pair, no unknown or retry')
    return True

def review_records(before, after, rows):
    _, spy, _, _ = dependencies()
    journal(rows)
    a = census(before, 'after_fixture'); b = census(after, 'after_ui_spy_batch')
    selected = {}; amounts = []
    for name in ORDER:
        sa, da, cost, pa = a[name]; sb, db, cost_after, pb = b[name]
        same(pa, pb, 'before/after same held process')
        same(da, db, 'before/after same dense candidate inputs')
        require(cost == cost_after, 'same dense cost')
        comparison = spy.compare_snapshots(sa, sb)
        require(comparison['before_absent'] is True and comparison['new_exact_expiry_count'] == 1,
                'one new selected exact-expiry modifier per family')
        found = spy.selected(sb)
        require(len(found['matching']) == 1 and found['matching'][0]['active_by_expiry_comparison'] is True,
                'one current selected modifier')
        require(sa['cost']['network_centipoints'] == 10000 and sb['cost']['network_centipoints'] == 2125,
                'fixed batch initial/final network')
        amounts.append(cost)
        selected[name] = {'definition_key':sa['registry']['name']['text'],
                          'selected_modifier':found['matching'][0], 'observed_selected_presence':True,
                          'candidate_cost_milli':cost,'individual_effect_verified':False,
                          'request_causality_verified':False,'interface_execution_verified':False}
    require(sum(amounts) == 78750, 'five static candidate costs total')
    remaining = 10000
    for cost in amounts:
        remaining = max(0,min(10000,remaining-(cost*100+500)//1000))
    require(remaining == 2125, 'batch rounded network balance')
    return {'schema':1,'status':'reviewed_manual_ui_batch_selected_observation',
            'pid':PID,'creation':CREATION,'world':WORLD,'raw_date':DATE,'actor':'FRA','target':'ENG',
            'ui_order':list(ORDER),'manual_ui_journal_consistent':True,'families':selected,
            'batch_balance':{'initial_centipoints':10000,'final_centipoints':2125,'delta_centipoints':-7875,
                             'candidate_total_milli':sum(amounts),'rounded_candidate_balance_matches':True,
                             'batch_observation_only':True,'individual_cost_attribution':False},
            'ignored_for_effect_claims':['subject_report','diagnostic_report','read trace hashes as raw-memory authentication'],
            **{key:False for key in FALSE_OUTPUT}}

def review_case(case_path, expected_sha, output):
    require(not output.exists(), 'CREATE_NEW output only')
    verify_sources()
    raw = bounded(case_path, 32768)
    require(hashlib.sha256(raw).hexdigest() == digest(expected_sha), 'explicit case hash')
    case = decode(raw)
    exact(case, 'schema purpose identity inputs')
    integer(case['schema'],1,1)
    require(case['purpose'] == 'fixed_spy5_ui_batch_38232', 'fixed case purpose')
    same(case['identity'],dict(pid=PID,creation=CREATION,world=WORLD,raw_date=DATE,actor='FRA',target='ENG'),
         'explicit fixed identity')
    exact(case['inputs'], 'before after journal')
    blobs = {}; paths = {}; specs = {}
    for name,path,limit in [('before',INITIAL_PATH,MAX_CENSUS),('after',FINAL_PATH,MAX_CENSUS),
                            ('journal',JOURNAL_PATH,MAX_JOURNAL)]:
        spec = case['inputs'][name]; exact(spec,'path sha256 bytes')
        require(spec['path'] == path, 'fixed explicit input path')
        if name == 'before':require(spec['sha256'] == INITIAL_SHA, 'fixed initial census pin')
        size = integer(spec['bytes'],1,limit);digest(spec['sha256'])
        file = ROOT/path;require(file.resolve() == file.absolute(), 'no input path redirection')
        data = bounded(file,limit)
        require(len(data) == size and hashlib.sha256(data).hexdigest() == spec['sha256'], 'input pin before decode')
        blobs[name]=data;paths[name]=file;specs[name]=spec
    require(blobs['journal'].endswith(b'\n') and len(blobs['journal'].splitlines()) == 11, 'complete journal lines')
    rows = [decode(line) for line in blobs['journal'].splitlines()]
    before, after = decode(blobs['before']),decode(blobs['after'])
    require(after['ui_journal_sha256'] == specs['journal']['sha256'], 'final binds actual journal hash')
    result = review_records(before,after,rows)
    verify_sources()
    require(bounded(case_path,32768) == raw, 'case unchanged')
    for name,path in paths.items():
        require(sha(path) == specs[name]['sha256'] and path.stat().st_size == specs[name]['bytes'], 'input unchanged')
    result.update(case_sha256=expected_sha,input_pins=specs,source_pins=verify_sources())
    with output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);stream.write('\n')
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',required=True,type=Path);parser.add_argument('--case-sha256',required=True)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    result=review_case(args.case,args.case_sha256,args.output)
    print(json.dumps({'status':result['status'],'summary_sha256':sha(args.output),'native_receipt_verified':False}))

if __name__=='__main__':main()
