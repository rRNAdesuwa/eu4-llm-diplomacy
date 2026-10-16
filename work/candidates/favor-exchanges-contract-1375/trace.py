"""Replay finite saved instruction/data evidence against the exact disk PE only."""
import argparse, hashlib, json, struct, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,check_memory_budget
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
INV='work/reports/native-diplomacy-1.37.5.json'
FIELDS='work/reports/native-action-fields-1375.json'
SPY='work/candidates/spy-action-contracts-1375/report.json'
V11='work/reports/native-pair-extension-v11-1375.json'
BREAK='work/candidates/favor-break-alliance-contract-1375/report.json'
CURRY='work/candidates/curry-favors-contract-1375/report.json'
NAMES=('reduce_relations_favor','trade_favors_for_gold','trade_favors_for_men',
       'trade_favors_for_sailors','trade_favors_for_trust','trade_favors_for_war_prep')
BRANCHES=(0x3601f3,0x35fe28,0x35fea7,0x35ff26,0x360024,0x3600df)
def load(p):
    with p.open('rb') as f:b=f.read(8*1024*1024+1)
    if len(b)>8*1024*1024:raise ValueError('bounded JSON')
    return json.loads(b)
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def render():
    pins=load(HERE/'input-pins.json')
    for p,s in pins.items():assert digest(ROOT/p)==s,p
    pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
    funcs={};ledger=[];new=0;peaks=[];failed=[]
    for n in range(1,13):
        path=HERE/f'exploration-{n:02}.json';d=load(path)
        assert d['game_sha256']==SHA and d['window']<=8192
        count=sum(f['decoded_bytes'] for f in d['functions'].values())+d.get('extra_failed_attempt_bytes',0)
        assert count==d['new_this_file'];new+=count;peaks.append(d['committed_bytes'])
        for k,f in d['functions'].items():
            assert f['decoded_bytes']<=8192 and k not in funcs
            adopted=k not in ('0x35ffa5','0x557c80','0x557580','0x4fd1f0','0x4feac0','0x4fea50','0x557380','0x500410')
            reason=None if adopted else ('Unselected adjacent heir factory branch' if k=='0x35ffa5' else 'Exploratory neighboring destructor/text helper, not needed for the six ABI claims')
            ledger.append({'source':path.name,'entry':k,'decoded_bytes':f['decoded_bytes'],'adopted':adopted,'not_adopted_reason':reason,'mode':f.get('decode_mode','bounded CFG, no call recursion')})
            funcs[k]={**f,'source':str(path.relative_to(ROOT)).replace('\\','/'),'source_pointer':'/functions/'+k}
        if d.get('failed_attempt'):failed.append(d['failed_attempt'])
    assert new==40585 and new<=49152 and max(peaks)<1024**3
    sources={p:load(ROOT/p) for p in (INV,FIELDS,SPY,V11,BREAK,CURRY)}
    imported={}
    imports=[(FIELDS,'functions',['0x7c6790','0x7c67d0','0x4fe7e0','0x4fe890']),
      (SPY,'functions',['0x4e9930','0x4e8630','0x4e7c50','0x4ea820','0x4e99d0','0x4ebdb0','0x8f440','0x8f450','0x4f3b00','0x4f3b10','0x4ec160']),
      (SPY,'imported_functions',['0x4e9d00','0x129b60']),
      (V11,'functions',['0x129450','0x129500','0x4f40a0','0x4f4ee0','0x4f5bd0','0x35fe28','0x4f3fe0','0xa658d0','0x3387f0','0x338540']),
      (CURRY,'functions',['0x4e7470']), (BREAK,'functions',['0x4f5940'])]
    for src,section,keys in imports:
        for k in keys:imported[k]={**sources[src][section][k],'source':src,'source_pointer':'/'+section+'/'+k}
    known={};strings={};verified_bytes=0
    for f in [*funcs.values(),*imported.values()]:
        for r in f['instructions']:
            b=bytes.fromhex(r['bytes']);assert pe.bytes_at(int(r['rva'],16),len(b))==b,r['rva']
            assert r['rva'] not in known or known[r['rva']]['bytes']==r['bytes']
            known[r['rva']]=r;verified_bytes+=len(b)
            if 'ascii' in r:
                b=r['ascii'].encode('ascii')+b'\0';assert pe.bytes_at(int(r['rip_target'],16),len(b))==b
                strings[r['rip_target']]={'bytes':b.hex(),'text':r['ascii']}
    facts=load(HERE/'facts.json')
    for f in facts.values():
        for a in f.get('anchors',[]):assert a in known,a
    data=[]
    def pin(address,width,meaning):
        b=pe.bytes_at(address,width);data.append({'rva':hex(address),'bytes':b.hex(),'meaning':meaning});return b
    normal_tokens=list(struct.unpack('<4I',pin(0x1dc23c0,16,'AI loop first four tokens')))+list(struct.unpack('<4I',pin(0x1dc23b0,16,'AI loop second four tokens')))+[0x3bcb]
    assert normal_tokens==[0x3bce,0x3bcf,0x3bd0,0x3bd2,0x3bd3,0x3bd4,0x3bcc,0x3bcd,0x3bcb]
    families=[]
    for name,branch in zip(NAMES,BRANCHES):
        a=next(x for x in sources[INV]['native_actions']['actions'] if x['name']==name)
        token=a['token_id'];vt=int(a['vtable_rva'],16)
        assert token in normal_tokens
        ix=pin(0x360768+(token-0x3b85),1,'selected factory byte dispatch '+name)[0]
        found=struct.unpack('<I',pin(0x36073c+ix*4,4,'selected factory relative branch '+name))[0]
        assert found==branch
        for slot,target in a['slots'].items():
            assert struct.unpack('<Q',pin(vt+int(slot,16),8,name+' virtual slot '+slot))[0]==pe.base+int(target,16)
        assert pe.bytes_at(int(a['accessor_rva'],16),6)==bytes.fromhex(a['accessor_bytes'])
        pin(int(a['accessor_rva'],16),6,name+' exact token getter')
        families.append({'name':name,'token':hex(token),'vtable':a['vtable_rva'],'size':a['clone']['allocation']['size_bytes'],'factory_branch':hex(branch),'slots':a['slots'],
          'normal_caller':'0x133ea0','normal_parameterized_caller_closed':name!='reduce_relations_favor',
          'third_party_selection_closed':False if name=='reduce_relations_favor' else None,
          'execution_verified':False,'raw_observer_implemented':False})
    for address,target,label in [(0x1c814b0,0x4e7470,'command destructor'),(0x1c814f0,0x4e8630,'command gate'),(0x1c814f8,0x4e7c50,'command execute')]:
        assert struct.unpack('<Q',pin(address,8,label))[0]==pe.base+target
    stock='work/runtime/unpacked-1.37.5/base/common/defines.lua'
    keywords=('TRADE_FAVORS_','INCREASE_TRUST_','PREPARE_FOR_WAR_','REDUCE_OPINION_')
    selected=[{'line':i+1,'text':s} for i,s in enumerate((ROOT/stock).read_text(encoding='utf-8-sig').splitlines()) if any(k in s for k in keywords)]
    return {'schema':1,'purpose':'favor_exchanges_static_contract','game_sha256':SHA,'inputs':pins,'families':families,
       'functions':funcs,'imported_functions':imported,'facts':facts,'data_pins':data,'string_pins':strings,
       'stock_defines':{'source':stock,'selected_lines':selected,'global_define_registration_not_traced':True},
       'limits':{'per_CFG_max':8192,'new_decode_budget':49152,'new_decoded_bytes_including_failures_and_repeated_prefixes':new,'ledger':ledger,'failed_attempts':failed,'historical_counter_correction':'exploration-12 cumulative omitted the earlier111-byte failed interpreter attempt; this recomputed sum of all new_this_file fields is authoritative','peak_committed_bytes':max(peaks),'verified_unique_instruction_anchors':len(known),'verified_bytes_including_reused_and_overlapping_rows':verified_bytes},
       'bounded_search':{'kind':'relative E8 candidate bytes only, not instruction proof','range':['0x120000','0x140000'],'target':'0x35d210','hits':['0x133fa3'],'selected_function':'0x133ea0','fragment_first_examined':'0x133eff','whole_program_search':False},
       'unsupported':['Human GUI parameter controls and visibility','reduce_relations_favor real third-country selection caller','Live full-generation/world/pause/engine-thread lifetime binding','Transitive script/TLS/lazy-cache side effects and common AI scoring internals','Normal native invocation, effect observation, save/reload','Any false/cancel API or raw pointer/parameter ABI exposed externally'],
       'native_adapter_implemented':False,'runtime_verified':False,'execution_verified':False,'effect_verified':False,'production_ready':False,'process_accessed':False}
def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    b=(json.dumps(render(),ensure_ascii=False,indent=2)+'\n').encode();out=HERE/'report.json'
    if a.check:assert out.read_bytes()==b
    else:
        with out.open('xb') as f:f.write(b)
    print(json.dumps({'check':a.check,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'committed_bytes':check_memory_budget(),'process_accessed':False}))
if __name__=='__main__':main()
