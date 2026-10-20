"""Reproduce disk evidence from bounded saved CFGs; never call or open EU4."""
import argparse, hashlib, json, struct, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,check_memory_budget
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
SPY='work/candidates/spy-action-contracts-1375/report.json'
FIELDS='work/reports/native-action-fields-1375.json'
V10='work/reports/native-pair-extension-v10-1375.json'
CURRY='work/candidates/curry-favors-contract-1375/report.json'
INVENTORY='work/reports/native-diplomacy-1.37.5.json'
STOCK='work/runtime/unpacked-1.37.5/base/common/new_diplomatic_actions/00_diplomatic_actions.txt'

def load(p):
    with p.open('rb') as f:b=f.read(8*1024*1024+1)
    if len(b)>8*1024*1024:raise ValueError('bounded JSON exceeded')
    return json.loads(b)

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def render():
    inputs=load(HERE/'input-pins.json')
    for name,sha in inputs.items():assert digest(ROOT/name)==sha,name
    pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
    functions={};new=0;explorations=[]
    for n in ('01','02','03'):
        name='exploration-'+n+'.json';d=load(HERE/name)
        assert d['game_sha256']==SHA and d['window']==8192
        for key,f in d['functions'].items():
            assert key not in functions and f['decoded_bytes']<=8192
            functions[key]={**f,'source':str((HERE/name).relative_to(ROOT)).replace('\\','/'),'source_pointer':'/functions/'+key,'evidence_kind':'new_bounded_saved_CFG'}
            new+=f['decoded_bytes']
        explorations.append({'file':name,'decoded_bytes':d['new_this_file'],'observed_committed_bytes':d['committed_bytes']})
    assert new==26985 and new<=49152
    sources={p:load(ROOT/p) for p in (SPY,FIELDS,V10,CURRY,INVENTORY)}
    imports=[(FIELDS,'functions',['0x54ee00','0x54ee40','0x5843e0','0x584420','0xac6540','0xac65a0']),
      (SPY,'functions',['0x4e9930','0x4e7c50','0x4e8630','0x4e99d0','0x4ea820','0x4ea610','0x4ebdb0','0x4ec160','0x576840','0x8f440','0x8f450']),
      (SPY,'imported_functions',['0x4e9d00','0x129b60']),
      (V10,'functions',['0x129500']), (CURRY,'functions',['0x4e7470'])]
    imported={}
    for source,section,keys in imports:
        for key in keys:
            f=sources[source][section][key]
            imported[key]={**f,'source':source,'source_pointer':'/'+section+'/'+key,'evidence_kind':'reused_saved_CFG_no_new_decode'}
    spy=sources[SPY]
    slices={'factory_prologue_and_tail':{'source':SPY,'source_pointer':'/factory_slices','instructions':[r for r in spy['factory_slices'] if int(r['rva'],16)<0x35d250 or int(r['rva'],16)>=0x36044d]},
      'scripted_AI_selected_blocks':{'source':SPY,'source_pointer':'/functions/0x13b810/instructions','instructions':[r for r in spy['functions']['0x13b810']['instructions'] if any(a<=int(r['rva'],16)<=b for a,b in ((0x13b840,0x13b870),(0x13be10,0x13be30),(0x13c230,0x13c24c),(0x13d264,0x13d3ad)))]}}
    anchors=0;verified_bytes=0
    for f in [*functions.values(),*imported.values(),*slices.values()]:
        for r in f['instructions']:
            raw=bytes.fromhex(r['bytes']);assert pe.bytes_at(int(r['rva'],16),len(raw))==raw,r
            anchors+=1;verified_bytes+=len(raw)
    families=[];data=[]
    for name in ('stealmap','support_rebels','scriptable_diplomatic_action'):
        a=next(a for a in sources[INVENTORY]['native_actions']['actions'] if a['name']==name)
        vt=int(a['vtable_rva'],16)
        for slot,target in a['slots'].items():
            addr=vt+int(slot,16);raw=pe.bytes_at(addr,8)
            assert struct.unpack('<Q',raw)[0]==0x140000000+int(target,16)
            data.append({'family':name,'slot':slot,'rva':hex(addr),'bytes':raw.hex(),'target':target})
        families.append({k:a[k] for k in ('name','token_id','vtable_rva','accessor_rva','slots','factory_branch')})
    with (ROOT/STOCK).open('rb') as f:stock_bytes=f.read(1024*1024+1)
    assert len(stock_bytes)<=1024*1024
    stock=stock_bytes.decode('utf-8-sig')
    start=stock.index('steal_modern_ideas = {');end=stock.index('\n}',start)+2
    block=stock[start:end];assert 'add_government_power' in block and 'russian_modernization_mechanic' in block
    facts=load(HERE/'facts.json')
    known={r['rva'] for f in [*functions.values(),*imported.values(),*slices.values()] for r in f['instructions']}
    for fact in facts.values():
        for anchor in fact.get('anchors',[]):assert anchor in known,(anchor,fact)
    return {'schema':1,'purpose':'spy_extra_parameters_static_contract','game_sha256':SHA,'input_pins':inputs,
      'families':families,'functions':functions,'imported_functions':imported,'slices':slices,'data_pins':data,'facts':facts,
      'stock_script':{'source':STOCK,'first_line':stock[:start].count('\n')+1,'text':block,'sha256':hashlib.sha256(block.encode()).hexdigest()},
      'limits':{'max_new_decode':49152,'per_CFG_window':8192,'new_decoded_bytes':new,'explorations':explorations,'all_exploration_retained':True,'unadopted_transitive_functions':['0xa2adf0','0xa2ac30','0xaa75c0','0xa0a1d0'],'unadopted_means_not_a_complete_effect_or_permission_contract':True,'verified_anchor_count':anchors,'verified_anchor_bytes_including_imports':verified_bytes,'vtable_slots':len(data)},
      'raw_sampler_implemented':False,'native_adapter_implemented':False,'runtime_verified':False,'execution_verified':False,'effect_verified':False,'production_ready':False,'process_accessed':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    data=(json.dumps(render(),ensure_ascii=False,indent=2)+'\n').encode();path=HERE/'report.json'
    if a.check:assert path.read_bytes()==data
    else:
        with path.open('xb') as f:f.write(data)
    print(json.dumps({'check':a.check,'report_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'committed_bytes':check_memory_budget(),'process_accessed':False}))
if __name__=='__main__':main()
