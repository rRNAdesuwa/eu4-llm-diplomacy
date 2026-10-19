"""Replay only saved CFG rows and the retained 294-byte finite exploration."""
import argparse,hashlib,json,pathlib,struct
from explore import ROOT,HERE,DiskPE,SHA,check_memory_budget
SOURCES={
 'curry':'work/candidates/curry-favors-contract-1375/report.json',
 'entry':'work/candidates/curry-favors-observer-1375/report.json',
 'cancel':'work/reports/native-pair-cancel-1375.json',
 'profile':'work/candidates/v21-core-pair-nosend-1375/profile-registry.json',
 'engine':'work/native/v17/pair-engine-1375.cpp',
 'agents':'work/AGENTS.md',
 'memory_helper':'work/discover_diplomacy.py',
 'exploration':'work/candidates/core-five-full88-and-spy-entry-1375/exploration-01.json',
}
FAMILIES={
 'vassalaction':dict(token=0x2940,start=0x12bd34,end=0x12bdc7,mode=0x12bd7b,call=0x12bdbc,vtlea=0x12bd6a,stack='rsp+0x30 / rbp-0x81'),
 'royal_marriage':dict(token=0x28df,start=0x12b8cf,end=0x12b9b6,mode=0x12b92c,call=0x12b96c,vtlea=0x12b904,stack='rbp-0x49'),
 'improve_relation':dict(token=0x2ddb,start=0x12c26b,end=0x12c2fe,mode=0x12c2b2,call=0x12c2f3,vtlea=0x12c2a1,stack='rsp+0x30 / rbp-0x81'),
 'guaranteeaction':dict(token=0x2941,start=0x12bca1,end=0x12bd34,mode=0x12bce8,call=0x12bd29,vtlea=0x12bcd7,stack='rsp+0x30 / rbp-0x81'),
 'spy_network':dict(token=0x3378,start=0x12caf9,end=0x12cb94,mode=0x12cb47,call=0x12cb89,vtlea=0x12cb2f,stack='rsp+0x30 / rbp-0x81')}
def read(p):
 with p.open('rb') as f:b=f.read(4*1024*1024+1)
 assert len(b)<=4*1024*1024
 return b
def desc(p):
 b=read(p);return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def build():
 loaded={k:json.loads(read(ROOT/p)) for k,p in SOURCES.items() if k not in ('engine','agents','memory_helper')}
 pins={p:desc(ROOT/p) for p in SOURCES.values()}
 pe=DiskPE();slices={};data=[]
 try:
  def take(label,key,parts,lo=0,hi=0xffffffff):
   obj=loaded[key]
   for part in parts:obj=obj[part]
   rows=[]
   for i,r in enumerate(obj):
    address=int(r['rva'],16)
    if lo<=address<hi:
     expected=bytes.fromhex(r['bytes']);assert pe.read(address,len(expected))==expected
     rows.append(dict(r,source=SOURCES[key],json_pointer='/'+('/'.join(parts))+f'/{i}'))
   assert rows,label;slices[label]=rows;return rows
  take('dispatcher_header','curry',['functions','0x12b860','instructions'],0x12b860,0x12b8cf)
  take('dispatcher_small_jump_table','curry',['functions','0x12b860','instructions'],0x12bb4e,0x12bb85)
  take('dispatcher_spy','curry',['functions','0x12b860','instructions'],0x12ca33,0x12ca66)
  take('normal_stack_epilogue','curry',['functions','0x12b860','instructions'],0x12cdc7,0x12cde8)
  table=loaded['exploration']['table'];assert pe.read(int(table['rva'],16),28).hex()==table['bytes'];data.append(dict(table,kind='RVA_jump_table'))
  profiles={p['family']:p for p in loaded['profile']['families']}
  result={}
  for family,cfg in FAMILIES.items():
   p=profiles[family]
   if family in ('vassalaction','guaranteeaction'):
    rows=take(family,'exploration',['explorations',hex(cfg['token']),'instructions'])
    target=int(table['targets'][cfg['token']-0x293e],16);assert target==cfg['start']
   else:rows=take(family,'curry',['functions','0x12b860','instructions'],cfg['start'],cfg['end'])
   by={int(r['rva'],16):r for r in rows};assert by[cfg['call']]['instruction']=='call 0x129b60'
   vtr=by[cfg['vtlea']];raw=bytes.fromhex(vtr['bytes']);assert raw[:3]==bytes.fromhex('488d05')
   vt=cfg['vtlea']+7+struct.unpack('<i',raw[3:])[0];assert vt==int(p['vtable_rva'],16)
   slot_values={0:int(p['destructor_rva'],16),0x40:0x4e9930,0x80:int(p['local80_rva'],16),0x88:int(p['full88_rva'],16),0xa8:0x8f450,0xb0:int(p['clone_rva'],16),0xe0:int(p['setter_rva'],16)}
   for off,target in slot_values.items():
    b=pe.read(vt+off,8);assert struct.unpack('<Q',b)[0]-pe.base==target
    data.append({'kind':'vtable_slot','family':family,'rva':hex(vt+off),'bytes':b.hex(),'slot':hex(off),'target_rva':hex(target)})
   result[family]={
    'token':cfg['token'],'size':p['size_bytes'],'vtable_rva':hex(vt),'normal_caller':'0x12b860','original_storage':'stack_local',
    'original_stack_base':cfg['stack'],'branch_entry':hex(cfg['start']),'normal_queue_call':hex(cfg['call']),
    'full88':{'rva':p['full88_rva'],'slot':'0x88','sink':'NULL','mode':False,'common_call_site':'0x129da0','distinct_from_local80':True,'distinct_from_generic_4e9d00':True},
    'initial_fields':{'marker8':0x165,'actor10':'proposal+0 full_handle','original18':'same as actor','target20':'proposal+8 full_handle','primary28':'current game+1dd0','secondary2c':'same current game+1dd0','envoy30':-1,'state34':0,'value38':True,'flag39':0,'id3c':0},
    'positive':{'caller_cancel_arg':False,'value':True,'envoy_after_construction':-1,'reaches_common_evaluator':True},
    'cancel':{'caller_cancel_arg':True,'value':False,'mode_write_or_setter_site':hex(cfg['mode']),'envoy_rule':'native void586330 scans diplomat graph; may retain -1 if no match' if family=='spy_network' else 'remains -1','reaches_common_evaluator':True},
    'extra_fields':{'String32_at40':'empty SSO length0 capacity15 first0','force60':False} if family=='royal_marriage' else {},
    'original_cleanup':{'kind':'stack String32 cleanup after evaluator; free only owned heap buffer when capacity>=16','sites':['0x12b972','0x12b976','0x12b983','0x12b9ac'],'does_not_delete_stack_object':True} if family=='royal_marriage' else {'kind':'trivial stack storage release at shared epilogue','site':'0x12cdc7','does_not_delete_stack_object':True},
    'owned_heap_original_cleanup_normal_caller_proved':False,'normal_AI_structural_call_chain_proved':True,'human_GUI_call_chain_proved':False,
    'runtime_verified':False,'native_ready':False,'production_ready':False}
  take('ordinary_AI_evaluator','curry',['imported_functions','0x129b60','instructions'])
  for function in ('0x4e9930','0x4e7470'):
   take(function,'curry',['functions',function,'instructions'])
  take('known_not_borrowed_getter','curry',['imported_functions','0x8f450','instructions'])
  for function in ('0x6fec50','0x6fec80','0x6ff4e0','0x6ff570','country_manager_vector_slice','0xc9f10'):
   take(function,'entry',['functions',function,'instructions'])
  take('spy_cancel_setter','cancel',['functions','0x586330','instructions'])
  take('mission_entry_link','entry',['functions','0x4e7550','instructions'],0x4e771a,0x4e77c7)
  entry_contract={
   'manager':{'vtable_rva':'0x1cac380','marker8':0x165,'token10':0x2746,'kind14':3,'owner16':'unaligned full_handle','begin20':'pointer','end28':'pointer','capacity30':'pointer','size':0x38},
   'country_holder':{'begin1480':'pointer vector','end1488':'pointer','capacity1490':'pointer','selected_pointer_offset':0x18,'selected_ordinal':3,'exact_proof':'2cb753/757/75d construct token2746 kind3 with country+20 owner;2cb80d..818 append as fourth entry;586384/395 select this same fourth manager'},
   'entry':{'vtable_rva':'0x1cac2f0','marker8':0x165,'mission10':'pointer','status18':'BYTE','kind40':3,'id44':'signed DWORD; nonnegative selected ID','size':0x48},
   'ctor_chain':'6fec80 allocates48, passes manager.kind14 to R8B and vector ordinal toR9D;6ff4e0 sets exact vtable,marker,kind and ID;stored back in this manager vector.',
   'spy_selection':'586330 selects entries from actor fourth manager, status2; mission+70 returns1, task+70 returns3378; chosen entry+44 copied action+30. Existing safe reader replaces native getters with separate pinned concrete mission/task layouts.',
   'safe_read_order':['country holder bounds and full actor identity','manager vtable before derived fields; marker/token/kind/owner','manager vector bounds and selected entry pointer','entry vtable before derived fields; marker/kind','status BYTE and ID signed DWORD','known mission/task type then full pair/backrefs/token','repeat complete graph and roots'],
   'unknown_entry_vtable':'return unsupported before entry+10/+18/+40/+44 derived reads; do not borrow mission vtable as entry identity',
   'implemented_sampler':False,'live_type_checked':False,'two_pass_is_lifetime_lock':False}
  n=sum(len(bytes.fromhex(r['bytes'])) for group in slices.values() for r in group)
  return {'schema':1,'purpose':'five_core_normal_AI_full88_and_diplomat_entry_type_static_supplement','game_sha256':SHA,'source_pins':pins,
   'profiles':result,'entry_contract':entry_contract,'instruction_slices':slices,'data_pins':data,
   'shared_ownership':{'full88_null_false':['0x129d95','0x129d98','0x129d9b','0x129da0'],'full_false_reject_site':'0x129da8','additional_local80_call':'0x129db9',
     'wrapper_call':'0x12a6e3','wrapper':'4e9930 calls action+b0, updates clone+2c to game+1dd0, allocates command58, stores clone at+50',
     'owning_queue':'12a6f2 reads returned container command;12a6f5 clears temporary;12a6fb assigns owner+a68;12a709 destroys prior command;12a71d destroys any residual temporary',
     'queued_original':'never stack original; independent clone owned by command','normal_command_cleanup':'4e7470 reads clone+50, calls clone virtual+a8; each of these five slots resolves8f450 returningfalse, then calls clone virtual+0(flags1), destroys command String32+18, conditionally deletes command58 when flags&1',
     'final_transport_or_effect_proved':False},
   'limitations':['A normal conditional AI route is proved, not unconditional acceptance, human GUI visibility or permission.129b60 includes score/world and other virtual checks and writes AI scheduling metadata.',
     'Plain originals are stack locals, not owned heap originals. Marriage destroys only its temporary String32 storage. This caller cannot authorize deleting a heap original or repairing an invalid object.',
     'Spy false mode resolves an envoy via native setter; lookup failure can retain -1. Exact live entry type/full generation/unique reciprocal binding still must be read and checked; type profile does not prove current object lifetime.',
     'Only structural known entry constructor/selected manager chain is proved. Unknown subclasses, reconstructed save objects, concurrent replacement, TLS/entitlement, epoch and strict SP remain unsupported.',
     'No sampler, adapter, DLL, native call, sender or actual validation is implemented. No frozen source changed.'],
   'limits':{'new_decode_bytes':loaded['exploration']['all_exploration_decoded_bytes'],'all_exploration_retained':True,'new_decode_total_limit':32768,'max_new_function_window':8192,'replayed_instruction_bytes_including_reuse':n,'instruction_count':sum(map(len,slices.values())),'memory_limit_bytes':768*1024*1024,'peak_commit':check_memory_budget(),'process_accessed':False,'all_shells_collected':True},
   'runtime_verified':False,'native_ready':False,'production_ready':False}
 finally:pe.close()
def canonical(data):return (json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode()
def main():
 a=argparse.ArgumentParser();a.add_argument('--check',action='store_true');args=a.parse_args();report=build();report['limits'].pop('peak_commit',None);raw=canonical(report);path=HERE/'report.json'
 if args.check:assert read(path)==raw
 else:
  with path.open('xb') as f:f.write(raw)
 print(json.dumps({'check':args.check,'report_sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'instructions':report['limits']['instruction_count'],'new_decode_bytes':report['limits']['new_decode_bytes'],'peak_commit':check_memory_budget()}))
if __name__=='__main__':main()
