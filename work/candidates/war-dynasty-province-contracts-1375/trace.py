"""Finite, disk-only replay. No process reader, game call, or recursive decode."""
import argparse, hashlib, json, struct, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,check_memory_budget
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
INV='work/reports/native-diplomacy-1.37.5.json'
FIELDS='work/reports/native-action-fields-1375.json'
SPY='work/candidates/spy-action-contracts-1375/report.json'
FAVOR='work/candidates/favor-exchanges-contract-1375/report.json'
V11='work/reports/native-pair-extension-v11-1375.json'
CURRY='work/candidates/curry-favors-contract-1375/report.json'
NAMES=('claimaction','sellprov','enforce_peace','threaten_war')
PUBLIC=('claim_throne','sell_province','enforce_peace','threaten_war')
BRANCHES=(0x35d94b,0x35dbed,0x35e365,0x35ed67)
CALLERS=(0x136ea0,0x138090,0x13b810,0x13d4c0)

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
    funcs={};ledger=[];failed=[];new=0;peaks=[]
    for n in range(1,6):
        path=HERE/f'exploration-{n:02}.json';d=load(path)
        assert d['game_sha256']==SHA and d['window']<=8192
        count=sum(f['decoded_bytes'] for f in d['functions'].values())+d.get('extra_failed_attempt_bytes',0)
        assert count==d['new_this_file'];new+=count;peaks.append(d['committed_bytes'])
        failed.extend(d.get('failed_and_repeated_exploration',[]))
        for k,f in d['functions'].items():
            assert k not in funcs and f['decoded_bytes']<=8192
            funcs[k]={**f,'source':str(path.relative_to(ROOT)).replace('\\','/'),'source_pointer':'/functions/'+k}
            ledger.append({'source':path.name,'entry':k,'decoded_bytes':f['decoded_bytes'],
                           'mode':f.get('decode_mode','bounded CFG, no call recursion')})
    assert new==46674 and new<=49152 and max(peaks)<1024**3
    sources={p:load(ROOT/p) for p in (INV,FIELDS,SPY,FAVOR,V11,CURRY)}
    imports=[(FIELDS,'functions',['0x4e87b0','0x4e8b40','0x552ab0','0x552b80','0x572eb0','0x572f80','0x54c9f0','0x54cb20']),
      (SPY,'functions',['0x13b810','0x4e9930','0x4e8630','0x4e7c50','0x4ea820','0x4e99d0','0x4ebdb0','0x4ec160','0x8f440','0x8f450']),
      (SPY,'imported_functions',['0x4e9d00','0x129b60']),
      (V11,'functions',['0x129450','0x129500','0x338540','0x3387f0']),
      (CURRY,'functions',['0x4e7470']),
      (FAVOR,'functions',['0x35d210','0x35db1a','0x36044d'])]
    imported={}
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
    def pin(rva,width,meaning):
        b=pe.bytes_at(rva,width);data.append({'rva':hex(rva),'bytes':b.hex(),'meaning':meaning});return b
    for token,indexbase,base,jumpbase,branch in [(0x2949,0x3604c0,0x28df,0x360480,0x35d94b),(0x2dda,0x360564,0x2d48,0x360530,0x35e365)]:
        ix=pin(indexbase+token-base,1,'selected factory dispatch index')[0]
        assert struct.unpack('<I',pin(jumpbase+ix*4,4,'selected factory branch RVA'))[0]==branch
    families=[]
    for name,public,branch,caller in zip(NAMES,PUBLIC,BRANCHES,CALLERS):
        a=next(x for x in sources[INV]['native_actions']['actions'] if x['name']==name)
        vt=int(a['vtable_rva'],16)
        for slot,target in a['slots'].items():
            assert struct.unpack('<Q',pin(vt+int(slot,16),8,name+' virtual slot '+slot))[0]==pe.base+int(target,16)
        b=bytes.fromhex(a['accessor_bytes']);assert pin(int(a['accessor_rva'],16),len(b),name+' token getter')==b
        families.append({'native_name':name,'public_id':public,'token':hex(a['token_id']),'vtable':a['vtable_rva'],
          'size':a['clone']['allocation']['size_bytes'],'factory_branch':hex(branch),'slots':a['slots'],
          'normal_caller':hex(caller),'normal_send_boundary':'AI owning queue 129b60' if name!='threaten_war' else 'direct wrapper 4e9930 then world sender bfe50',
          'normal_full88_call_closed':name!='threaten_war','parameter_live_resolution_implemented':False,'execution_verified':False})
    for address,target,label in [(0x1c814b0,0x4e7470,'command destructor'),(0x1c814f0,0x4e8630,'command gate'),(0x1c814f8,0x4e7c50,'command execute')]:
        assert struct.unpack('<Q',pin(address,8,label))[0]==pe.base+target
    stock='work/runtime/unpacked-1.37.5/base/common/diplomatic_actions/00_diplomatic_actions.txt'
    lines=(ROOT/stock).read_text(encoding='utf-8-sig').splitlines()
    selected=[{'line':i+1,'text':s} for i,s in enumerate(lines) if any(x in s for x in PUBLIC)]
    return {'schema':1,'purpose':'war_dynasty_province_static_contract','game_sha256':SHA,'inputs':pins,
      'families':families,'functions':funcs,'imported_functions':imported,'facts':facts,'data_pins':data,'string_pins':strings,
      'stock_action_identifiers':{'source':stock,'selected_lines':selected},
      'limits':{'new_decode_budget':49152,'max_function_or_slice':8192,'new_decoded_bytes_including_failed_upper_bound_and_repeats':new,
        'failed_upper_bound_is_conservative':True,'ledger':ledger,'discarded_exploration':failed,'peak_committed_bytes':max(peaks),
        'verified_unique_instruction_anchors':len(known),'verified_bytes_including_reused_overlaps':verified_bytes},
      'unsupported':['Human GUI construction and parameter selection','threaten_war normal sender full+88 invocation (normal AI observed local+80 only)',
        'Live country/province/war resolution, exact array bounds and event correlation','All transitive lazy government/TLS/script/CB side effects',
        'Engine-thread/lifetime/SP provenance and live native invocation','Any cancel/false public mode or arbitrary state2/force-accept input',
        'Observed effects, persistence and production API execution'],
      'raw_observer_implemented':False,'native_adapter_implemented':False,'runtime_verified':False,'execution_verified':False,
      'effect_verified':False,'production_ready':False,'process_accessed':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    b=(json.dumps(render(),ensure_ascii=False,indent=2)+'\n').encode();out=HERE/'report.json'
    if a.check:assert out.read_bytes()==b
    else:
        with out.open('xb') as f:f.write(b)
    print(json.dumps({'check':a.check,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'committed_bytes':check_memory_budget(),'process_accessed':False}))
if __name__=='__main__':main()
