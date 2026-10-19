"""Disk-only dense spy-cost aggregate evidence. No process access or engine call."""
import argparse,hashlib,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import SHA,bounded_cfg
SOURCES=['work/candidates/spy-modifier-observer-1375/report.json','work/candidates/spy-action-contracts-1375/report.json',
 'work/candidates/spy-modifier-observer-1375/observer.py','work/candidates/spy-modifier-observer-1375/review.json',
 'work/discover_diplomacy.py','work/map_diplomacy_fields.py','work/AGENTS.md']
NEW=[0x939ef0,0x93ae10,0x93d130,0x8e6120,0x8e6190,0x1b2370]
def bounded(p,limit=8*1024*1024):
    with p.open('rb') as f:raw=f.read(limit+1)
    if len(raw)>limit:raise ValueError('input budget')
    return raw
def rec(n):
    raw=bounded(ROOT/n);return {'path':n,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def generate():
    pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
    md,cs=make_disassembler(Path(os.environ.get('TEMP',''))/'eu4-native-analysis-deps');assert md
    fs={};n=0
    for a in NEW:
        rows,edges=bounded_cfg(pe,md,a,window=8192,max_instructions=2500);size=sum(i.size for i in rows);assert size<=8192
        fs[hex(a)]={'kind':'new_bounded_cfg','decoded_bytes':size,'edges':edges,'instructions':[]};n+=size;assert n<=16384
        for i in rows:
            r={'rva':hex(i.address),'bytes':i.bytes.hex(),'instruction':(i.mnemonic+' '+i.op_str).strip()}
            for o in i.operands:
                if o.type==cs.CS_OP_MEM and o.mem.base==cs.x86_const.X86_REG_RIP:r['rip_target_rva']=hex(i.address+i.size+o.mem.disp)
            fs[hex(a)]['instructions'].append(r)
        check_memory_budget()
    for source,entry,key in [(SOURCES[0],'0x93d750','exe_sha256'),(SOURCES[1],'0x4ea610','game_sha256')]:
        j=json.loads(bounded(ROOT/source));assert j[key]==SHA
        fs[entry]={**j['functions'][entry],'kind':'reused_cfg','source':source,'json_pointer':'/functions/'+entry}
    for f in fs.values():
        for i in f['instructions']:
            b=bytes.fromhex(i['bytes']);assert pe.bytes_at(int(i['rva'],16),len(b))==b
    facts={
      'aggregate_layout':{'value':{'country_cache_state':0x28c8,'country_aggregate':0x28d0,'vtable':0x1c42770,'type_offset':8,'type_value':0x165,'dense_offset':0x10,'vector_vtable_offset':0x50,'vector_vtable':0x1c37fa0,'data_offset':0x58,'capacity_offset':0x60,'count_offset':0x64,'record_stride':8},'anchors':['0x8e6122','0x8e6129','0x8e612f','0x8e6139','0x8e6160','0x8e6164','0x8e6168','0x8e616f','0x1b2385','0x1b23c8','0x1b23e4','0x1b2401']},
      'dense_initialization':{'value':{'initial_count':0x287,'empty_id':0x286,'empty_value':0,'empty_id_is_not_index':True,'initial_count_is_not_a_live_fixed_count':True},'anchors':['0x93ad00','0x93ad04','0x93ad08','0x93ad1c','0x8e619b','0x8e619e','0x8e61a7','0x8e61b5','0x8e61ba','0x1b23e8','0x1b23ee','0x1b23f0','0x1b23f4','0x1b2401']},
      'capacity_growth':{'value':'requested count greater than capacity allocates max(2*capacity,requested)*8, then updates vector storage via 94030; count becomes requested; allocation helper is not invoked by this candidate','anchors':['0x1b2385','0x1b2391','0x1b2395','0x1b239e','0x1b23a5','0x1b23ab','0x1b23b5','0x1b23c3','0x1b2401']},
      'dense_nonzero_writer':{'value':{'example_id':0xd5,'example_value':1000,'id_address_delta':0x6a8,'value_address_delta':0x6ac,'only_example_not_exhaustive_writer_inventory':True},'anchors':['0x93d6be','0x93d6c4','0x93d6c8','0x93d6d2']},
      'selected_cost':{'value':{'selected_index':0x261,'value_offset':0x130c,'native_ignores_record_id_in_dense_branch':True,'transform_global_rva':0x2358080,'transform_offset':0xe4a0,'projection':'base_milli*(1000+modifier_milli)/1000; narrow candidate admits only nonnegative product, so // equals native truncation toward zero'},'anchors':['0x4ea65c','0x4ea661','0x4ea665','0x4ea66c','0x4ea670','0x4ea6a4','0x4ea6ab','0x4ea6b5','0x4ea6ca','0x4ea6e2','0x4ea7d8','0x4ea7db','0x4ea7e3','0x4ea7e7','0x4ea7f1','0x4ea7f4','0x4ea7fb','0x4ea7ff','0x4ea802']},
      'cache_recompute_boundaries':{'value':'93d130 destroys/rebuilds wrapper, sets state1 and thread owner, invokes an indirect callback table, then writes state2 and clears owner. State2 is a narrow observed state, not proof of freshness, synchronization, or lifetime. Getter93d750 and recompute are never called.','anchors':['0x93d150','0x93d15b','0x93d51f','0x93d540','0x93d548','0x93d579','0x93d5f9','0x93d600']}}
    allrows={i['rva']:i for f in fs.values() for i in f['instructions']}
    for fact in facts.values():
        fact['evidence']=[allrows[a] for a in fact.pop('anchors')]
    observer=json.loads(bounded(ROOT/SOURCES[0]));data_pins=[]
    for rva,size in [(0x1c42770+0x48,8)]:
        raw=pe.bytes_at(rva,size);assert int.from_bytes(raw,'little')==0x140000000+0x8e6190
        data_pins.append({'rva':hex(rva),'bytes':raw.hex(),'value':'aggregate virtual+48 = 8e6190'})
    return {'schema_version':1,'exe_sha256':SHA,'inputs':[rec(n) for n in SOURCES],'functions':fs,
      'facts':facts,'data_pins':data_pins,'families':{k:{'base_cost_rva':v['base_cost_rva']} for k,v in observer['families'].items()},
      'limits':{'new_decoded_bytes':n,'total_new_limit':16384,'per_cfg_window':8192,'memory_guard':805306368},
      'runtime_verified':False,'native_call_authorized':False,'production_ready':False}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();j=generate()
    raw=(json.dumps(j,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode();p=HERE/'report.json'
    if a.check:assert bounded(p)==raw
    else:p.write_bytes(raw)
    print(json.dumps({'pass':True,'check':a.check,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'new_decoded_bytes':j['limits']['new_decoded_bytes'],'peak_committed':check_memory_budget()}))
