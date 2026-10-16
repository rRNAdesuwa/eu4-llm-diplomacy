"""Exact-PE static evidence assembly. Bounded reports; no process/native call."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,check_memory_budget
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
SPY='work/candidates/spy-action-contracts-1375/report.json'
CALLERS='work/candidates/spy-four-normal-callers-contract-1375/report.json'
PEACE='work/reports/native-peace-gui-send-1375.json'
SUBJECT='work/candidates/subject-toggle-contracts-1375/report.json'
TRANSPORT='work/reports/preview-string-and-transport-1375.json'
def bounded(p):
    with p.open('rb') as f:b=f.read(8*1024*1024+1)
    assert len(b)<=8*1024*1024;return b
def rec(p):
    b=bounded(ROOT/p);return dict(path=p,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def generate():
    pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
    spy=json.loads(bounded(ROOT/SPY));callers=json.loads(bounded(ROOT/CALLERS))
    fs={}
    def add(source,key,fn,pointer):
        rows=[]
        for r in fn['instructions']:
            b=bytes.fromhex(r['bytes']);assert pe.bytes_at(int(r['rva'],16),len(b))==b
            rows.append(dict(rva=r['rva'],bytes=r['bytes'],instruction=r.get('instruction',(r.get('mnemonic','')+' '+r.get('operands','')).strip())))
        fs[key]=dict(source=source,source_pointer=pointer,instructions=rows,decoded_bytes=sum(len(bytes.fromhex(r['bytes'])) for r in rows))
    for key in ['0x4e7c50','0x4ea820','0x4e8630','0x4e9930']+[f['slots']['0x48'] for f in spy['families']]:
        group='functions' if key in spy['functions'] else 'imported_functions'
        add(SPY,key,spy[group][key],'/'+group+'/'+key)
    for source,keys in [(PEACE,['0x4e7470','0x14ca210']), (SUBJECT,['0x14ca2d0','0x1580370','0x1580ff0'])]:
        d=json.loads(bounded(ROOT/source))
        for k in keys:add(source,k,d['functions'][k],'/functions/'+k)
    d=json.loads(bounded(ROOT/TRANSPORT))
    idx=next(i for i,f in enumerate(d['functions']) if f['requested_rva']=='0x1580270')
    add(TRANSPORT,'0x15801c0',d['functions'][idx],'/functions/'+str(idx))
    new=0
    for n in range(1,5):
        source=str((HERE/f'exploration-{n:02}.json').relative_to(ROOT)).replace('\\','/')
        d=json.loads(bounded(ROOT/source));new+=d['new_decoded_bytes']
        for k,f in d['functions'].items():
            assert f['decoded_bytes']<=8192;add(source,k,f,'/functions/'+k)
    assert new==2718 and new<=49152
    anchors={x['rva']:x for f in fs.values() for x in f['instructions']}
    facts={
      'context_slot_consumed_before_checks':['0x14ca22a','0x14ca22d','0x14ca234','0x14ca244','0x14ca24a','0x14ca299','0x14ca29c'],
      'raw_pointer_submit_is_different_ABI':['0x14ca2df','0x14ca2e7','0x14ca323','0x14ca33d','0x14ca340'],
      'wrapper_clones_and_stamps':['0x4e9940','0x4e9957','0x4e995c','0x4e9960'],
      'transport_deletes_original_command':['0x1580c4a','0x1580c55','0x1580c5a'],
      'consumer_takes_transport_c8_queue':['0x8b0e0','0x14ca8aa','0x14ca8da','0x14ca91a','0x14ca927'],
      'consumer_rechecks_gate_and_wraps_callback':['0x14cab30','0x14cab35','0x14caf25','0x14caf31','0x14caf3b','0x14caf44'],
      'callback_reaches_command_execute':['0x14d4ea1','0x14d4e5d','0x10a0f24','0x10a0f34','0x14ceaca','0x14ceae0'],
      'consumer_destroys_consumed_command':['0x14cb130','0x14cb133','0x14cb138','0x14cb13b'],
      'execute_rechecks_local_and_skips_envoy':['0x4e7c6c','0x4e7c6f','0x4e7c71','0x4e7c86','0x4e7c90','0x4e7ffc','0x4e8054'],
      'conditional_effect_and_native_cost':['0x4ea899','0x4ea8a2','0x4ea8b8','0x4ea8c1','0x4ea8cd','0x4eaad5','0x4eab18'],
    }
    for v in facts.values():assert all(a in anchors for a in v),v
    tables=[]
    for rva,size in [(0x1c814b0,0x90),(0x1d96178,0x90),(0x1d8c8b0,0x28)]:
        b=pe.bytes_at(rva,size);tables.append(dict(rva=hex(rva),bytes=b.hex(),slots={hex(i):hex(struct.unpack_from('<Q',b,i)[0]-pe.base) for i in range(0,size,8)}))
    assert tables[0]['slots']['0x48']=='0x4e7c50' and tables[1]['slots']['0x48']=='0x8b0e0' and tables[2]['slots']['0x10']=='0x14cea10'
    families=[]
    for f,c in zip(spy['families'],callers['families']):
        assert f['name']==c['name'] and c['normal_ai_initialization_static_closed'] is True
        assert all(f['slots'][x]=='0x8f450' for x in ['0xa8','0xd0','0xf8','0x100'])
        families.append({k:f[k] for k in ['name','token','size','vtable_rva','slots','definition_slot','stock_definition_name_candidate','capability_byte_offset']})
    check_memory_budget()
    return dict(schema=1,purpose='v19_static_send_design_only',game_sha256=SHA,
      input_pins=[rec(p) for p in [SPY,CALLERS,PEACE,SUBJECT,TRANSPORT]],families=families,functions=fs,
      data_pins=tables,facts={k:[anchors[a] for a in v] for k,v in facts.items()},
      resource=dict(new_decoded_bytes=new,new_decode_budget=49152,per_function_window=8192,all_exploration_recorded=True,
        no_unrecorded_exploration=True,no_recursive_callee_following=True),
      limitations=['Bounded CFG is not unwind proof or proof of all function paths.',
        'Consumer scheduling, queue timing and execution are not observed.',
        '14ca210 return true and consumed slot are transport acknowledgment only.',
        'Effect virtual48 has country predicates and scripted hooks; it does not establish request causality.',
        'Full preview may allocate or invoke script/TLS; it is not read-only.',
        'No current v18 or v19 actual session has been read or authenticated by this candidate.'],
      runtime_verified=False,execution_verified=False,production_ready=False,process_accessed=False)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    raw=(json.dumps(generate(),sort_keys=True,indent=2)+'\n').encode();out=HERE/'report.json'
    if a.check:assert bounded(out)==raw
    else:
        with out.open('xb') as f:f.write(raw)
    print(json.dumps(dict(passed=True,new_decoded_bytes=2718,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))))
