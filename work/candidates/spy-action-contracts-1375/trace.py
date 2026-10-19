"""Bounded exact-build disk analysis. No process access, engine calls or writes.

Default creates report.json exclusively; --check reproduces it without writing.
No call recursion. All imported instruction bytes are checked against the PE.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'work'))
from discover_diplomacy import PE, make_disassembler, check_memory_budget
from map_diplomacy_fields import bounded_cfg
from trace_change_subject_type import rows

EXE_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
MAX_INPUT = 10 * 1024 * 1024
MAX_DECODE = 40 * 1024
NAMES = ('corrupt_officials', 'sabotage_reputation', 'sow_discontent',
         'slander_merchants', 'sabotage_recruitment')
EXTRAS = (0x4f3b00, 0x4f3b10, 0x4e99d0, 0x4ec160, 0x4eb900, 0x4ebdb0,
          0x328c70, 0x8ecec0, 0x4ea820, 0x4e9930, 0x4e8630, 0x4ea610,
          0x576840, 0x8f440, 0x129450, 0xb357b0, 0x3283c0, 0x4e7c50,
          0x13b810, 0x4e99e0)
IMPORTS = {
 'work/reports/native-pair-cancel-1375.json': ('0x4e9d00',),
 'work/reports/native-coalition-queue-1375.json': ('0x129b60',),
}
FACTORY_WINDOWS = ((0x35d210,0x35d228),(0x35f1f1,0x35f270),(0x35e172,0x35e1f1),
                   (0x35e070,0x35e0ef),(0x35f172,0x35f1f1),
                   (0x35f0f3,0x35f172),(0x36044d,0x360478))
# Stock key links remain candidates until the live definition's bounded name is
# independently observed. Offset/call/data-flow evidence itself is exact bytes.
PARAMS = {
 'corrupt_officials': (0x160,0x86,0x233fae0,1,'corrupt_officials',25,1825),
 'sabotage_reputation': (0x150,0x80,0x233fae4,1,'reputation_sabotaged',60,1825),
 'sow_discontent': (0x140,0x83,0x233faf8,1,'discontent_sowed',80,1825),
 'slander_merchants': (0x170,0x81,0x233faf0,30,'merchants_slandered',70,60),
 'sabotage_recruitment': (0x180,0x82,0x233faf4,30,'recruitment_sabotaged',80,60),
}

def bounded_bytes(path: Path, limit=MAX_INPUT):
    with path.open('rb') as f:
        value = f.read(limit + 1)
    if len(value) > limit:
        raise ValueError(f'input exceeds {limit}: {path.name}')
    return value

def load(path):
    return json.loads(bounded_bytes(path).decode('utf-8'))

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024*1024), b''): h.update(part)
    return h.hexdigest()

def verify_rows(pe, values):
    for x in values:
        raw=bytes.fromhex(x['bytes'])
        if not raw or pe.bytes_at(int(x['rva'],16),len(raw)) != raw:
            raise ValueError('instruction bytes differ: '+x['rva'])

def render():
    pins=load(HERE/'input-pins.json')
    for path, expected in pins.items():
        if sha(ROOT/path) != expected: raise ValueError('input pin differs: '+path)
    pe=PE(ROOT.parent/'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest()!=EXE_SHA: raise ValueError('EXE SHA differs')
    md, version=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
    inv=load(ROOT/'work/reports/native-diplomacy-1.37.5.json')
    actions={a['name']:a for a in inv['native_actions']['actions']}
    entries=set(EXTRAS)
    for name in NAMES:
        entries.update(int(actions[name]['slots'][s],16)
                       for s in ('0x48','0x80','0x88','0xb0','0xe8','0xd0','0x68','0x118'))
    functions={}; total=0
    for entry in sorted(entries):
        ins, edges=bounded_cfg(pe,md,entry,window=0x4000,max_instructions=4000)
        count=sum(i.size for i in ins); total+=count
        if total>MAX_DECODE: raise ValueError('aggregate decode budget exceeded')
        functions[hex(entry)]={'instructions':rows(pe,ins),'edges':edges,'decoded_bytes':count}
    imported={}
    for path, names in IMPORTS.items():
        source=load(ROOT/path)
        for name in names:
            value=source['functions'][name]
            verify_rows(pe,value['instructions'])
            imported[name]={'source':path,'json_pointer':'/functions/'+name,'instructions':value['instructions']}
    src=load(ROOT/'work/reports/action-factories.json')['functions'][0]['instructions']
    factory=[]
    for x in src:
        if any(lo<=int(x['rva'],16)<hi for lo,hi in FACTORY_WINDOWS):
            factory.append({'rva':x['rva'],'bytes':x['bytes'],
                            'instruction':x['mnemonic']+' '+x['operands']})
    verify_rows(pe,factory)
    at={x['rva']:x for f in functions.values() for x in f['instructions']}
    def anchors(*rvas):
        return [at[hex(n)] for n in rvas]
    families=[]; slot_rows=[]
    for name in NAMES:
        a=actions[name]; vt=int(a['vtable_rva'],16)
        for offset, target in a['slots'].items():
            raw=pe.bytes_at(vt+int(offset,16),8)
            if struct.unpack('<Q',raw)[0] != 0x140000000+int(target,16):
                raise ValueError('vtable slot mismatch')
            slot_rows.append({'family':name,'offset':offset,'rva':hex(vt+int(offset,16)),
                              'bytes':raw.hex(),'target_rva':target})
        d,cap,dur,mult,key,cost,days=PARAMS[name]
        cf=functions[a['slots']['0x118']]['instructions']
        families.append({
          'name':name,'token':a['token_id'],'vtable_rva':a['vtable_rva'],
          'size':64,'destructor_rva':'0x129450','factory_reference':a['factory_branch']['reference_rva'],
          'slots':a['slots'],'factory_state':0,'factory_value':True,'factory_envoy':-1,
          'factory_date_sentinel':0x29c77f8,'factory_handle_sentinel':'0x00000000002d2d2d',
          'clone_copies':['0x10:QWORD','0x18:QWORD','0x20:QWORD','0x28:DWORD',
                          '0x30:DWORD','0x34:DWORD','0x38:BYTE','0x3c:DWORD'],
          'clone_special':['destination+0x2c=source+0x28','destination+0x39=0'],
          'derived_fields':[], 'initialization_normal_caller_verified':name=='corrupt_officials',
          'positive_only_candidate':True,'false_is_undo_verified':False,
          'capability_pointer_country_offset':0x2440,'capability_byte_offset':cap,
          'static_modifier_registry_global_rva':'0x242bd08','definition_slot':d,
          'stock_definition_name_candidate':key,'definition_name_live_verified':False,
          'duration_global_rva':hex(dur),'duration_to_days_multiplier':mult,
          'stock_cost_points':cost,'stock_duration_setting':days,
          'stock_duration_result_days':days*mult,
          'raw_cost_getter':cf,'runtime_verified':False,'production_ready':False,
        })
    facts=[
      {'id':'corrupt_normal_ai_initialization','claim':'Normal AI stack action uses full actor in +10/+18, target in +20, current date in +28/+2c, envoy -1, state/id 0, value true/flag39 false; calls 129b60.',
       'anchors':anchors(0x13c241,0x13c365,0x13c369,0x13c374,0x13c381,0x13c385,0x13c389,0x13c38d,0x13c390,0x13c393,0x13c39a,0x13c39e,0x13c3a4,0x13c3a8,0x13c3c4),
       'cross_reference':'129b60+0x245 calls virtual88(null,false); +0xb83 virtual40; +0xb9b owning AI queue. See imported function.'},
      {'id':'corrupt_effect_target_modifier','claim':'Effect first executes scripted hook; then target-country definition registry+160 and duration to add-modifier. Not an undo branch, not an AI acceptance request.',
       'anchors':anchors(0x581ae7,0x581aec,0x581b0a,0x581b10,0x581b1d,0x581b2d,0x581b37,0x581b49)},
      {'id':'full_preview_needed','claim':'Corrupt virtual88 calls generic preview, then actor capability+86. Generic4e9d00 and command gate invoke virtual80, not virtual88; a future adapter must preserve the extra family gate.',
       'anchors':anchors(0x582750,0x582780,0x5827c0,0x4e8775)},
      {'id':'native_preview_not_read_only','claim':'Definition getter may allocate global registry; family checks may initialize TLS; scripted prerequisite registry and condition evaluation may allocate or execute unknown virtual code.',
       'anchors':anchors(0x8eced7,0x8ecee4,0x8ecef1,0x582445,0x4ebdec,0x4ebe0a,0x4ebfb6)},
      {'id':'spy_cost','claim':'Cost getter118 feeds4ea610 fixed-point modifier calculation. Gate compares signed relationWORD+18 *10 to cost_milli. Dispatch falls through state0 statistics branch to debit the resolved target relationWORD, clamped 0..10000; subject targeting is resolved, not necessarily literal target.',
       'anchors':anchors(0x4ea631,0x4ea7d8,0x4ea802,0x4e871b,0x4e8733,0x4e8763,0x4eaa23,0x4eaa68,0x4eaa9d,0x4eaad5,0x4eaadc,0x4eab02,0x4eab18,0x4eab20)},
      {'id':'no_normal_envoy_or_reply','claim':'For all five, +100/+f8/+d0 are constant false, +108 true. Command gate bypasses ordinary cooldown predicate when100=false; execute jumps past ordinary envoy allocation. d0=false skips pending reply branch. This does not prove all script-hook effects or successful application.',
       'anchors':anchors(0x8f440,0x8f450,0x4e864f,0x4e8657,0x4e7c86,0x4e7c90,0x4e8125,0x4e812d)},
      {'id':'country_modifier_observer','claim':'328c70 allocates0x50 and b357b0 writes vt1ce8040, def+30, null associated pointer+38, expiry+44. Expiry=date+days*24. Target country list head1f0/tail1f8/count200, node20B: object0/prev8/next10/flag18. No actor handle is stored by this constructor invocation; attribution is correlated evidence only.',
       'anchors':anchors(0x328d8a,0x328d8e,0x328d91,0x328d97,0x328dcf,0xb357c5,0xb357cc,0xb357ff,0xb3581a,0xb3581e,0x3283fe,0x328405,0x328413,0x328416,0x32841a,0x328422,0x328430)},
      {'id':'conditional_script_hook_not_cost','claim':'4eb900 itself checks target+14b0/value/envoy, then4ec4d0 resolves token-defined scripted callback+88/virtual78. It is not the cost debit helper. Primary effect4ec160 has separate scripted hook+50/virtual78.',
       'anchors':anchors(0x4eb91e,0x4eb928,0x4eb92e,0x4eb932,0x4ec6c5,0x4ec6d7)},
    ]
    other=[]
    for name in ('support_rebels','stealmap','infiltrate_administration','agitate_for_liberty',
                 'counterespionage','justify_trade_conflict','scriptable_diplomatic_action'):
        a=actions[name]
        other.append({'name':name,'token':a['token_id'],'vtable_rva':a['vtable_rva'],
                      'factory_branch':a.get('factory_branch'),'layout':a.get('layout'),
                      'source':'work/reports/native-diplomacy-1.37.5.json',
                      'runtime_verified':False,'closed_by_this_report':False})
    return {'schema':1,'analysis_kind':'bounded_static_disk_only','game_sha256':EXE_SHA,
            'runtime_verified':False,'production_ready':False,'process_accessed':False,
            'input_sha256':pins,'families':families,'vtable_rows':slot_rows,
            'functions':functions,'imported_functions':imported,'factory_slices':factory,
            'facts':facts,'deferred_families':other,
            'limitations':[
              'CFG follows direct branches within16KiB, max4000 instructions; does not recurse calls or prove unknown script/virtual paths.',
              'No DLL compiled or changed; no hooks/process/engine calls/native adapter implemented.',
              'Only corrupt initialization has a newly bound normal AI caller; its owned queue is reused exact-checked prior evidence, not a human GUI or live execution proof.',
              'Definition registry slot to stock key is a candidate until bounded live name/vtable verification; no dynamic TLS instance or definition predicate is called.',
              'false mode is not an inverse-effect contract; no false mode proposed for any of the five.',
              'Context submit ownership is inherited research evidence, not re-proved here and not applied-effect evidence.',
              'Modifier addition, script hooks, notifications, spy-network cost and caches can mutate world; pause/preview do not prove purity or thread safety.',
              'Study technology passive network benefit and steal_modern_ideas scripted action are distinct; no fabricated research_technology native token.',
            ],
            'limits':{'new_functions':len(functions),'new_decoded_bytes':total,'max_new_decoded_bytes':MAX_DECODE,
                      'window_per_cfg':16384,'max_instructions_per_cfg':4000,
                      'imported_instruction_bytes':sum(len(bytes.fromhex(x['bytes'])) for f in imported.values() for x in f['instructions'])+sum(len(bytes.fromhex(x['bytes'])) for x in factory),
                      'memory_hard_limit':1073741824}}

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    r=render();raw=(json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    path=HERE/'report.json'
    if a.check:
        if bounded_bytes(path)!=raw:raise ValueError('report differs')
    else:
        with path.open('xb') as f:f.write(raw)
    print(json.dumps({'check':a.check,'report_sha256':hashlib.sha256(raw).hexdigest(),
                      'report_bytes':len(raw),'limits':r['limits'],'peak_committed_bytes':check_memory_budget()}))

if __name__=='__main__':main()
