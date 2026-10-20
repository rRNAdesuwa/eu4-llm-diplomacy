"""Reproduce four normal AI construction branches. Disk-only, no call recursion."""
import argparse,hashlib,json,struct,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import bounded_cfg
from trace_change_subject_type import rows
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
SPY='work/candidates/spy-action-contracts-1375/report.json'
CURRY='work/candidates/curry-favors-contract-1375/report.json'
PROFILES={
 'sabotage_reputation':dict(function='0x13b810',begin=0x13c20a,end=0x13c25e,action_rsp_offset=0x50,queue_call=0x13c27e,score_call=0x13c26e,score_function=0x57ed60,parent_call=None),
 'sow_discontent':dict(function='0x13a1f0',begin=0x13a204,end=0x13a25c,action_rsp_offset=0x20,queue_call=0x13a384,score_call=None,score_function=None,parent_call=0x13c3d4),
 'slander_merchants':dict(function='0x13b810',begin=0x13c2e4,end=0x13c332,action_rsp_offset=0x120,queue_call=0x13c350,score_call=0x13c341,score_function=0x580730,parent_call=None),
 'sabotage_recruitment':dict(function='0x13ade0',begin=0x13adf4,end=0x13ae4c,action_rsp_offset=0x20,queue_call=0x13af84,score_call=None,score_function=None,parent_call=0x13c360),
 'corrupt_officials':dict(function='0x13b810',begin=0x13c365,end=0x13c3b3,action_rsp_offset=0x120,queue_call=0x13c3c4,score_call=None,score_function=None,parent_call=None),
}

def raw(p,limit=8*1024*1024):
 with p.open('rb') as f:b=f.read(limit+1)
 if len(b)>limit:raise ValueError('input bound')
 return b
def load(p):return json.loads(raw(p))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def encode(x):return (json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()
def verify(pe,values):
 for row in values:
  b=bytes.fromhex(row['bytes'])
  assert pe.bytes_at(int(row['rva'],16),len(b))==b,row['rva']
def target(row):
 b=bytes.fromhex(row['bytes']);assert len(b)==5 and b[0]==0xe8
 return int(row['rva'],16)+5+struct.unpack('<i',b[1:])[0]

def render():
 pins=load(HERE/'input-pins.json')
 for p,h in pins.items():assert sha(ROOT/p)==h,p
 pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
 md,_=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
 new={};total=0
 for file in sorted(HERE.glob('exploration-*.json')):
  cache=load(file)
  for entry,old in cache['functions'].items():
   assert entry not in new
   ins,edges=bounded_cfg(pe,md,int(entry,16),window=8192,max_instructions=2500)
   projected=rows(pe,ins);n=sum(i.size for i in ins);total+=n
   assert total<=65536 and projected==old['instructions'] and edges==old['edges']
   new[entry]={'source':file.name,'instructions':projected,'edges':edges,'decoded_bytes':n}
 old=load(ROOT/SPY);curry=load(ROOT/CURRY)
 imports={}
 def take(label,source,pointer,fn,ranges=None):
  ins=fn['instructions']
  if ranges:ins=[r for r in ins if any(lo<=int(r['rva'],16)<hi for lo,hi in ranges)]
  verify(pe,ins);imports[label]={'source':source,'json_pointer':pointer,'ranges':ranges,'instructions':ins}
 # Reuse only bounded saved slices of the large dispatcher; don't redisassemble it.
 take('0x13b810',SPY,'/functions/0x13b810',old['functions']['0x13b810'],
      [(0x13b810,0x13b86f),(0x13be10,0x13be46),(0x13c0fd,0x13c455)])
 take('0x129b60',SPY,'/imported_functions/0x129b60',old['imported_functions']['0x129b60'])
 for entry in ['0x4e9930','0x129450']:
  take(entry,SPY,'/functions/'+entry,old['functions'][entry])
 take('0x4e7470',CURRY,'/functions/0x4e7470',curry['functions']['0x4e7470'])
 take('0x8f450',CURRY,'/imported_functions/0x8f450',curry['imported_functions']['0x8f450'])
 families=[];data=[]
 for family in old['families']:
  name=family['name'];cfg=PROFILES[name]
  source=(imports if cfg['function']=='0x13b810' else new)[cfg['function']]['instructions']
  initialization=[x for x in source if cfg['begin']<=int(x['rva'],16)<cfg['end']]
  assert initialization
  code=next(x for x in initialization if x['instruction'].startswith('lea rax, [rip'))
  b=bytes.fromhex(code['bytes']);vt=int(code['rva'],16)+len(b)+struct.unpack('<i',b[-4:])[0]
  assert vt==int(family['vtable_rva'],16)
  lookup={x['rva']:x for x in source}
  assert target(lookup[hex(cfg['queue_call'])])==0x129b60
  if cfg['score_call']:assert target(lookup[hex(cfg['score_call'])])==cfg['score_function']
  if cfg['parent_call']:
   parent=next(x for x in imports['0x13b810']['instructions'] if x['rva']==hex(cfg['parent_call']))
   assert target(parent)==int(cfg['function'],16)
  getter=int(family['slots']['0x98'],16);value=b'\xb8'+struct.pack('<I',family['token'])+b'\xc3'
  assert pe.bytes_at(getter,6)==value
  data.append({'kind':'token_getter_mov_eax_imm32_ret','family':name,'rva':hex(getter),'bytes':value.hex(),'token':family['token']})
  for slot in ['0x0','0x40','0x80','0x88','0x98','0xa8','0xb0']:
   rva=vt+int(slot,16);v=pe.bytes_at(rva,8)
   assert struct.unpack('<Q',v)[0]==pe.base+int(family['slots'][slot],16)
   data.append({'kind':'vtable','family':name,'slot':slot,'rva':hex(rva),'bytes':v.hex(),'target_rva':family['slots'][slot]})
  clone=family['slots']['0xb0'];take(clone,SPY,'/functions/'+clone,old['functions'][clone])
  families.append({'name':name,'token':family['token'],'size':64,'vtable_rva':hex(vt),
     'factory_reference':family['factory_reference'],'token_getter':hex(getter),
     'normal_caller':cfg,'initialization_instructions':initialization,
     'slots':{s:family['slots'][s] for s in ['0x0','0x40','0x80','0x88','0x98','0xa8','0xb0']},
     'normal_ai_initialization_static_closed':True,'runtime_verified':False,'production_ready':False})
 factory=old['factory_slices'];verify(pe,factory)
 for pin in curry['data_pins']:
  if pin['kind']=='command_vtable_slot':
   value=bytes.fromhex(pin['bytes']);assert pe.bytes_at(int(pin['rva'],16),len(value))==value
   data.append(dict(pin,source=CURRY))
 combined={r['rva']:r for f in [*imports.values(),*new.values()] for r in f['instructions']}
 def fact(key,claim,*sites):return {'id':key,'claim':claim,'anchors':[combined[hex(x)] for x in sites]}
 facts=[
  fact('actor_target_origin','13b810 keeps AI in RSI, selected target country in R14; actor loaded from AI+28. Reputation reloads actor into RDI; other blocks load directly. No bare TAG parameters.',0x13b84e,0x13b851,0x13be22,0x13c0fd,0x13c20a,0x13c2e4,0x13c2e8),
  fact('reputation_fields','Stack action rsp50: marker357,actor/original fullRDI,targetR14+20,currentGAMEdate twice,envoy-1,state0,value1/flag0,id0,exactfamilyvt.',0x13c21b,0x13c223,0x13c228,0x13c22d,0x13c232,0x13c236,0x13c23a,0x13c241,0x13c244,0x13c248,0x13c24e,0x13c252,0x13c259),
  fact('merchant_fields','Stack action rbp20: all semantic fields explicitly initialized. R13 zero was set at13c241 and is nonvolatile across intervening normal ABI calls.',0x13c2e4,0x13c2e8,0x13c2ec,0x13c300,0x13c304,0x13c308,0x13c30c,0x13c30f,0x13c312,0x13c319,0x13c31d,0x13c323,0x13c327,0x13c32e),
  fact('recruitment_fields','Helper13ade0 called from13b810 uses AI RCX/targetcountry RDX; entryR11=currentRSP+68,actionRSP+20. Fullhandles/currentdate/state0/envoy-1/value1/flag0/id0 explicitly stored.',0x13c360,0x13adf4,0x13adf7,0x13adfb,0x13ae14,0x13ae18,0x13ae1c,0x13ae20,0x13ae24,0x13ae28,0x13ae30,0x13ae32,0x13ae36,0x13ae3d,0x13ae41,0x13ae48,0x13af84),
  fact('discontent_fields','Helper13a1f0 has separate explicit normal constructor. Its r8b changes score branch, never action value; value remains1.',0x13c3d4,0x13a204,0x13a207,0x13a20b,0x13a224,0x13a228,0x13a22c,0x13a230,0x13a234,0x13a238,0x13a240,0x13a242,0x13a246,0x13a24d,0x13a251,0x13a258,0x13a25c,0x13a384),
  fact('score_not_mode','Reputation/merchant score helpers write caller-owned DWORD result and return its pointer; shown helper bodies do not write action fields or pass action pointer to their downstream calls. This does not prove downstream world-read purity.',0x13c26e,0x13c273,0x13c27e,0x57ed6f,0x57ed72,0x57ed7f,0x57eedc,0x13c341,0x13c346,0x13c350,0x58073f,0x580742,0x58074f,0x5807da),
  fact('preview_abi','Common129b60 first performs other score/cost gates; on advancing path full+88 receives RCXaction,RDXnull,R8false; false branches away. Local+80 follows separately with same null/false. Neither is command gate.',0x129b8d,0x129b90,0x129d95,0x129d98,0x129d9b,0x129d9d,0x129da0,0x129da6,0x129da8,0x129dae,0x129db1,0x129db4,0x129db6,0x129db9),
  fact('owned_queue','On eligible normal path virtual+40 wrapper returns command slot address. AI+a68 receives command; temporary is cleared before previous command destruction. The borrowed stack action is not stored into AI queue.',0x129b93,0x12a6d6,0x12a6d9,0x12a6e0,0x12a6e3,0x12a6e6,0x12a6f2,0x12a6f5,0x12a6f8,0x12a6fb,0x12a703,0x12a709,0x12a70b),
  fact('clone_wrapper_lifetime','Wrapper clones via+b0, stamps clone2c currentdate, allocates58 ownedcommand storingclone50. Command checks clone+a8(false for allfive) then deletingdtor. Never separately delete ownedclone after command destruction.',0x4e9940,0x4e9950,0x4e9957,0x4e995c,0x4e9991,0x4e99ba,0x4e99bd,0x4e7489,0x4e7495,0x4e74ab,0x4e74b0,0x4e74c0,0x4e74d4),
 ]
 imported_bytes=sum(len(bytes.fromhex(r['bytes'])) for f in imports.values() for r in f['instructions'])+sum(len(bytes.fromhex(r['bytes'])) for r in factory)
 return {'schema':1,'purpose':'four_spy_normal_AI_callers_static_closure','game_sha256':SHA,'input_pins':pins,
   'families':families,'functions':new,'imported_functions':imports,'factory_slices':factory,'data_pins':data,'facts':facts,
   'limits':{'new_cfg_count':len(new),'new_cfg_decoded_bytes':total,'new_token_leaf_bytes':30,'total_new_code_bytes':total+30,'max_new_code_bytes':65536,'window_per_cfg':8192,'max_instructions_per_cfg':2500,'saved_imported_bytes':imported_bytes,'all_exploration_included':True},
   'unsupported':['No human GUI callback newly closed; normal AI eligibility/scoring is not an external sending permission.',
    'Normal AI constructs stack actions directly. Factory token is bound through its pinned matching vtable/token getter, not claimed to be an AI factory call.',
    'Known normal x64 nonvolatile preservation is required between initialization and queue; exception unwind/no-throw/thread safety and full transitive script/cache effects are not proved.',
    'Only positive value1 normal branches are closed. Third helper bool is score control, not cancellation.',
    'Current player FRA/ENG binding, strict SP/origin/epoch, runtime lifecycle/dispatch/application remain external unproved requirements.',
    'New static evidence does not modify frozen no-send core/model or authorize native calls.'],
   'runtime_verified':False,'execution_verified':False,'effect_verified':False,'production_ready':False,'process_accessed':False}

def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
 result=render();b=encode(result);path=HERE/'report.json'
 if a.check:assert raw(path)==b
 else:
  with path.open('xb') as f:f.write(b)
 print(json.dumps({'check':a.check,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'limits':result['limits'],'committed_bytes':check_memory_budget()}))
if __name__=='__main__':main()
