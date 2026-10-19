"""Reproduce exact-build bounded curry-favors evidence. Disk only."""
from __future__ import annotations
import argparse,hashlib,json,struct,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import bounded_cfg
from trace_change_subject_type import rows
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
MAX_FILE=8*1024*1024
IMPORTS={
 'work/reports/native-pair-effects-1375.json':['0x4ea820','0x4e7c50','0x4e7550','0x257a40','0x6ff570'],
 'work/reports/native-pair-cancel-1375.json':['0x4e9d00','0xa5bb00','0x25a3c0','0x25a680','0x8f450'],
 'work/reports/native-coalition-queue-1375.json':['0x129b60'],
}
def raw(path):
 with path.open('rb') as f:data=f.read(MAX_FILE+1)
 if len(data)>MAX_FILE:raise ValueError('input budget')
 return data
def load(path):return json.loads(raw(path))
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def encoded(x):return (json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()
def verify_rows(pe,values):
 for row in values:
  value=bytes.fromhex(row['bytes'])
  if not value or pe.bytes_at(int(row['rva'],16),len(value))!=value:raise ValueError('PE differs '+row['rva'])
def render():
 pins=load(HERE/'input-pins.json')
 for path,digest in pins.items():
  if sha(ROOT/path)!=digest:raise ValueError('input hash '+path)
 pe=PE(ROOT.parent/'eu4.exe')
 if hashlib.sha256(pe.data).hexdigest()!=SHA:raise ValueError('EXE SHA')
 md,cs=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
 functions={};total=0
 for filename in sorted(HERE.glob('decode-*.json')):
  cache=load(filename)
  for entry,old in cache['functions'].items():
   if entry in functions:raise ValueError('duplicate decode')
   ins,edges=bounded_cfg(pe,md,int(entry,16),window=8192,max_instructions=2500)
   rendered=rows(pe,ins)
   if rendered!=old['instructions'] or edges!=old['edges']:raise ValueError('exploration reproduction differs '+entry)
   n=sum(i.size for i in ins);total+=n
   if total>65536:raise ValueError('aggregate decode budget')
   functions[entry]={'instructions':rendered,'edges':edges,'decoded_bytes':n,'exploration_source':filename.name}
 imported={}
 for filename,entries in IMPORTS.items():
  source=load(ROOT/filename)
  for entry in entries:
   values=source['functions'][entry]['instructions'];verify_rows(pe,values)
   imported[entry]={'source':filename,'json_pointer':'/functions/'+entry,'instructions':values}
 factory=[]
 source=load(ROOT/'work/reports/action-factories.json')['functions'][0]['instructions']
 for x in source:
  if any(lo<=int(x['rva'],16)<hi for lo,hi in [(0x35d210,0x35d228),(0x35f559,0x35f56b),(0x35fceb,0x35fd6a),(0x36044d,0x360478)]):
   factory.append({'rva':x['rva'],'bytes':x['bytes'],'instruction':(x['mnemonic']+' '+x['operands']).rstrip()})
 verify_rows(pe,factory)
 inv=load(ROOT/'work/reports/native-diplomacy-1.37.5.json')
 family=next(x for x in inv['native_actions']['actions'] if x['name']=='curry_favors')
 data=[]
 for name,vt,slots in [('action',0x1c7aef8,family['slots']),
    ('relation',0x1c7b178,{'0x0':'0x28b1e0','0x10':'0xa5c020','0x20':'0xa5bdd0','0x48':'0x5ae240','0x50':'0xa63e80','0x58':'0xa63ed0','0x60':'0xa63f30'}),
    ('command',0x1c814b0,{'0x0':'0x4e7470','0x40':'0x4e8630','0x48':'0x4e7c50','0x50':'0x4e8430','0x60':'0x4e8520'}),
    ('mission',0x1c4b2b8,{'0x70':'0x8f440'})]:
  for offset,target in slots.items():
   rva=vt+int(offset,16);value=pe.bytes_at(rva,8)
   if struct.unpack('<Q',value)[0]!=pe.base+int(target,16):raise ValueError('vtable '+name+offset)
   data.append({'kind':name+'_vtable_slot','rva':hex(rva),'bytes':value.hex(),'slot':offset,'target_rva':target})
 # Four-byte setter and two leaf predicates; never treat setter as bool.
 for rva,value in [(0x4e99d0,'885138c3'),(0x5ae240,'b8cc3a0000c3'),(0x8f440,'b001c3'),(0x8f450,'32c0c3')]:
  if pe.bytes_at(rva,len(bytes.fromhex(value))).hex()!=value:raise ValueError('leaf pin')
  data.append({'kind':'leaf','rva':hex(rva),'bytes':value})
 all_rows={r['rva']:r for f in [*functions.values(),*imported.values(),{'instructions':factory}] for r in f['instructions']}
 def fact(name,text,*rvas):return {'id':name,'claim':text,'anchors':[all_rows[hex(v)] for v in rvas]}
 facts=[
  fact('factory','Token3acc branch allocates40; actor/original/target invalid handle2d2d2d, envoy-1; shared tail date sentinel29c77f8 twice,state0,value1,flag39=0,id0.',0x35f559,0x35f565,0x35fceb,0x35fd41,0x35fd45,0x35fd50,0x35fd5b,0x35fd5e,0x360450,0x360453,0x360459,0x36045c,0x360463),
  fact('normal_ai_modes','12b860 proposal+0/+8 are copied to action actor/original and target, game date28/2c, envoy-1,state0,id0. Third argument r8b selects cancellation by replacing value1 with0. Both modes reach129b60; this is an ordinary AI caller, not a newly located human GUI path.',0x12b885,0x12b88f,0x12b896,0x12cc8e,0x12cc94,0x12cd39,0x12cd44,0x12cd48,0x12cd50,0x12cd54,0x12cd57,0x12cd5a,0x12cd63,0x12cd66,0x12cd6c,0x12cd7b,0x12cd80,0x12cdc1),
  fact('ai_preview_wrapper_owning_queue','129b60 calls full88(null,false), then80; virtual40 returns owning command container. Queue a68 takes command pointer, nulls temporary before old-command cleanup. Stack action is not itself queued.',0x129da0,0x129db9,0x12a6e3,0x12a6f2,0x12a6f5,0x12a6fb,0x12a709,0x12a70b),
  fact('clone','40-byte clone copies semantic fields; destination2c is source28, not source2c;39 reset0. No derived owned strings/vectors observed. Independent allocated clone has same vtable.',0x5ae2b9,0x5ae2be,0x5ae2e0,0x5ae2e8,0x5ae2f0,0x5ae2f7,0x5ae2fe,0x5ae305,0x5ae30c,0x5ae314,0x5ae318,0x5ae320,0x5ae32b),
  fact('action_destructor','Deleting destructor129450 rewrites base vt, frees40 only if flags&1; this class has no nested owned member cleanup. ABI returns object pointer; return is not success evidence.',0x129463,0x129468,0x12946d,0x129472),
  fact('wrapper_and_command_destruction','Wrapper clones source, updates cloned2c from currentdate, allocates58 and stores clone50; returns caller slot pointer. Command destructor frees its nonborrowed clone first, thenString32+18 and58; never independently free clone after command dtor.',0x4e9940,0x4e9950,0x4e9957,0x4e995c,0x4e9991,0x4e99ba,0x4e99bd,0x4e7489,0x4e7495,0x4e74b0,0x4e74c0,0x4e74d4),
  fact('full_preview_and_tls','Full88=5ae110 contains same TLS condition as80: if global233ff48==0 OR233fed6!=0, access gs:58 TLS, potentially initialize, requireTLS+10. Then4e9d00; native gate4e8630 separately invokes80. Never replace full88 with gate or call these from RO sampling.',0x5ae12e,0x5ae135,0x5ae137,0x5ae13e,0x5ae140,0x5ae157,0x5ae161,0x5ae178,0x4e8775),
  fact('family_gate','Positive80 rejects matching war indexroot50/count5c and matching curry index158/164, then scripted4ebdb0. Negative80 requires current curry index entry. These checks search slot only and do not verify fullgraph/vtable/mission identities.',0x5adec7,0x5adf05,0x5adf09,0x5adf20,0x5adfae,0x5adfb5,0x5adfc8,0x5ae02f,0x5ae07c,0x5ae083,0x5ae096),
  fact('start_effect','Positive effect4ec160 script hook then allocates40 relation withvt1c7b178, actor10,target18,start20=currentdate; managerregistration and actor outgoing index insertion; failures usea5bb00 andfree40. Notifications/hooks also run, not a pure relation toggle.',0x5ace70,0x5ace7a,0x5ace7f,0x5aceee,0x5acf1b,0x5acf1f,0x5acf23,0x5acf30,0x5acf75,0x5acf7a,0x5acf83,0x5acf90),
  fact('actual_cancel_effect','False5ad74d resolves actor country andtarget slot; a69bf0 gets current outgoing relation. Removes manager/index, setsremoved28=1, runsbase relation dtor andfree40. This effect evidence is independent of localization/value=false naming.',0x5ad754,0x5ad760,0x5ad782,0x5ad786,0x5ad7a4,0x5ad7e4,0x5ad7e9,0x5ad7f0,0x5ad7fd),
  fact('outgoing_index','Actor relation record root0 -> mapbase150, pointer158/capacity160/count164,16B slot32/object64 entries. a69af0 inserts/removes through28d810 and all-relations28ac10. No same-object reciprocal incoming curry index is proved.',0xa69b0f,0xa69b16,0xa69b27,0xa69b50,0xa69b7d,0xa69b9b,0xa69bfc,0xa69c03,0xa69c16,0xa69c26,0x28d82e,0x28d8c2,0x28d91c,0x28d91f,0x28d927),
  fact('mission_creation','Positive virtual100/f8 returns value, d0=false: common command takes free diplomat path, allocatesf8 mission, fullactor80/target88/actiontokena8=3acc, linkedentry48/envoyID50, records actual selectedID back intoaction30. Negative100/f8=false skips newmission.',0x4e7c86,0x4e7c90,0x4e7ddf,0x4e7de2,0x4e7569,0x4e757e,0x4e758a,0x4e7595,0x4e75f0,0x4e77bc,0x4e77c3,0x4e7811),
  fact('relation_mission_binding','Common settlement marks selected actor envoy status2;3acc switch explicitly resolvesa69bf0 and writes relation30=entry10mission. Curry uses direct relation association, not spy mission+a0 nestedtask.',0x4eacd9,0x4eacec,0x4eaee4,0x4eaef3,0x4eaf0e,0x4eaf12),
  fact('cancel_envoy_ownership','Base setter onlyvalue; ordinary cancel initializedenvoy-1. Relation dtor reads30mission and calls25a3c0(mission,-1) only serverexists/servervirtual140false/game7485zero/mission48entry nonnull. Do not callreturn twice; failed world/mission prerequisites can prevent recall.',0x4e99d0,0xa5bb2d,0xa5bb35,0xa5bb3f,0xa5bb47,0xa5bb50,0xa5bb57,0xa5bb5c),
  fact('manager_tombstones','Global game+1bb8 registry actor-slot rows24B hashead0/tail8/count10/iterating14; nodes20B relation0/prev8/next10/marked18. Removal whileiterating marksnode without unlinking; relation freedbycaller, so markednode relation pointer must never be dereferenced.',0x4e13dd,0x4e13f7,0x4e13fe,0x4e1404,0x4e1411,0x4e1660,0x4e16bb,0x4e16c1,0x4e16d1,0x4e1707),
 ]
 return {'schema':1,'purpose':'exact_1375_curry_favors_static_contract','game_sha256':SHA,'input_pins':pins,'family':family['name'],'token':15052,'action_vtable_rva':family['vtable_rva'],'functions':functions,'imported_functions':imported,'factory_slices':factory,'data_pins':data,'facts':facts,'limits':{'new_cfg_count':len(functions),'new_decoded_bytes':total,'all_exploration_included':True,'max_new_decoded_bytes':65536,'window_per_cfg':8192,'max_instructions_per_cfg':2500,'imported_decoded_bytes':sum(len(bytes.fromhex(r['bytes'])) for f in imported.values() for r in f['instructions'])+sum(len(bytes.fromhex(r['bytes'])) for r in factory),'memory_hard_limit':1073741824},'unsupported':['Human GUI-specific sender was not newly located; normal AI path supports the initialization contract.','No executable backend, dynamic entitlement/TLS/authority/world-epoch proof, live lifecycle, dispatch, effect or persistence.','Favors amount gain/rate/decay, complete script sideeffects, no-throw/unwind guarantees and multiplayer behavior remain unproved.','Raw observer and save parser are not implemented here. Minimal graph below is a proposed bounded read contract, not a call authorization.','Ordinary request and mission allocation/dispatch can mutate caches, scripts, notifications, cooldown and world.','Functions5ae950/5af450/4e87b0/4e7450 were exploratory and are not used to assert curry semantics; all bytes remain budgeted.'],'runtime_verified':False,'execution_verified':False,'production_ready':False,'process_accessed':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
 r=render();data=encoded(r);path=HERE/'report.json'
 if a.check:
  if raw(path)!=data:raise ValueError('report differs')
 else:
  with path.open('xb') as f:f.write(data)
 print(json.dumps({'check':a.check,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'limits':r['limits'],'committed_bytes':check_memory_budget()}))
if __name__=='__main__':main()
