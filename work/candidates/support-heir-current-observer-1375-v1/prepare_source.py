"""Generate only this unsealed source draft from fixed reviewed source; no imports/tests/process."""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=ROOT/'work/candidates/integration-task-observer-1375-v1'

def source(name,sha):
 b=(OLD/name).read_bytes();assert hashlib.sha256(b).hexdigest()==sha;return b.decode('utf-8')

def replace_block(s,start,end,replacement):
 a=s.index(start);b=s.index(end,a);return s[:a]+replacement+'\n\n'+s[b:]

def save(name,s):
 with (HERE/name).open('x',encoding='utf-8',newline='\n') as f:f.write(s)

s=source('integration_task_observer.py','ec576a21a4018fa1b91d0864990b281a7a075ed3761404d9bdd7559de8b25cb9')
s=s.replace('integration-task','support-heir task').replace('_integration_task_','_support_heir_current_')
s=s.replace("'integration_task_observer.py'","'support_heir_current_observer.py'")
s=s.replace('EU4-INTEGRATION-TASK','EU4-SUPPORT-HEIR').replace('integration_completed','final_heir_result_verified')
s=s.replace("'support_heir_current_observer.py','test_support_heir_current_observer.py','README.md','build_manifest.py','run_offline.py'",
 "'support_heir_current_observer.py','test_support_heir_current_observer.py','README.md','build_manifest.py','run_offline.py','prepare_source.py'")
s=replace_block(s,"R44=","REQUIRED=",'''R48='work/reports/dynastic-support-reader-static-20261015-r48/'
R50='work/reports/dynastic-support-reader-entry-20261015-r50/'
R48_REVIEW='work/reports/dynastic-support-reader-r48-independent-20261015-r1/findings.json'
R50_REVIEW='work/reports/dynastic-support-reader-r50-independent-20261015-r1/findings.json'
CROSSWALK='work/reports/support-heir-handle-crosswalk-20261015-r1/findings.json'
VT=0x1c7c1c8
FIXED={
 DIRECT:'5429932a8f4fb81180c566caa0905008d60880f51f7c5868dd7568b4040fe518',
 DIRECT_MANIFEST:'47cfc947bac30cf47eaf9aa09b46bc423a0cefb49168930b03af4be6a2b47bb8',
 OBSERVER:'9eafecba34e74a6bf1cc3d081b9ce4dee10395cf6bae7da233f915328ec876d1',
 JOB:'5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011',
 'work/candidates/integration-task-observer-1375-v1/integration_task_observer.py':'ec576a21a4018fa1b91d0864990b281a7a075ed3761404d9bdd7559de8b25cb9',
 'work/candidates/integration-task-observer-1375-v1/test_integration_task_observer.py':'1f81280856c9728cfeb0b0c2834516604dc11e881c7a2b7c22d16ca9353a8e96',
 'work/reports/integration-task-observer-source-review-20261015-r1/independent-source-ready.json':'14662f7d78556103252f3f52f30a398d570ce246e56bb17948127249ebc10cc4',
 R48+'manifest.json':'00b98e57bc9ca3c69feae82695717db9851bafb05e7148be5e33426a6fa9ee3b',
 R48+'contract.json':'973a776a00ed95ac61e71b68cf33ac8fad799f18fb2f928de72c1bf07204ef4c',
 R48+'owned-code.json':'d392ac87b59dee56bd77f75f2e41243efbea7def5c1a1819d1df3c1ced42b197',
 R50+'manifest.json':'b09a9795d4f9ca2b9a4f330f39b695720705aad76c4bb5ec452341999260e304',
 R50+'contract.json':'ddc97d4bfd011ade3778ded05c643b9aba7c450eeba50b9162757a25353583f2',
 R50+'owned-code.json':'14cbfd7e2ce8bb4de4992e9f71bef4e5430fb75b11d95424ff5054ddbd4687fd',
 R48_REVIEW:'02df6084e3dac269d4f970c091fe6dee85d9dba9c19b2caec4689b062aa764ed',
 R50_REVIEW:'fe6a9188e2d6be6b55d545505ca19c70c244bcf15ea38e32ce4edc80c0dfc7d9',
 CROSSWALK:'f25d2760d0a2d6afac77d590aff36f165f95b45750542ccb243e25d7ad805abe'}
''')
s=s.replace("'native_predicate_executed','native_ready'","'AI_acceptance_verified','native_predicate_executed','native_ready'")
s=replace_block(s,' for prefix in (R44,R45,R46):',' return dict(manifest=pin(MANIFEST)', ''' for prefix in (R48,R50):
  static=json_file(local_path(prefix+'manifest.json'))
  for n in (prefix+'contract.json',prefix+'owned-code.json'):
   require(static['file_pins'][n]==actual[n],'Static selected output pin linkage')
 if runtime or m['runtime_capture_authorized']:
  require(m['sealed'] is True and m['runtime_capture_authorized'] is True,'Independent source-ready production seal required before process access')
  review=m.get('independent_source_review')
  require(type(review) is dict and set(review)=={'path','bytes','sha256'},'Independent source review pin required')
  check(review['path'],{k:review[k] for k in ('bytes','sha256')})''')
s=replace_block(s,'def code_buffers():','class Libraries:', '''def code_buffers():
 a=json_file(local_path(R48+'owned-code.json'));b=json_file(local_path(R50+'owned-code.json'))
 raw_a=bytes.fromhex(a['raw_hex']);raw_b=bytes.fromhex(b['raw_hex'])
 require(a['window']==['0x595120','0x5961b4'] and b['window']==['0xa69ab0','0xa69af0']
  and [len(raw_a),len(raw_b)]==[4244,64],'Fixed loaded code spans')
 require(hashlib.sha256(raw_a).hexdigest()==a['sha256'] and hashlib.sha256(raw_b).hexdigest()==b['sha256'],'Owned code digest')
 return [(0x595120,raw_a),(0xa69ab0,raw_b)]''')
s=s.replace('selected exact pinned R44/R45/R46 outputs; static producer dependencies not re-executed',
 'selected exact pinned R48/R50 outputs and independent static reviews; producer dependencies not re-executed')
s=replace_block(s,'def code_guard(', 'def sample_selected(', '''def code_guard(r,base,codes):
 out=[]
 for offset,expected in codes:
  require(type(expected) is bytes,'Code bytes required')
  raw=r.read(base+offset,len(expected));require(raw==expected,'Loaded code mismatch at '+hex(offset))
  out.append(dict(rva=hex(offset),bytes=len(raw),raw_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest()))
 return out


def nullable_index(r,observer,root,other_slot,count):
 """R50 key/value projection plus explicit reader bounds; zero values are legal."""
 require(type(other_slot) is int and 0<other_slot<min(count,32768),'Selected positive slot')
 header=r.read(root+0x140,16);array,capacity,used=struct.unpack('<Qii',header)
 require(0<=used<=256 and used<=capacity<=4096,'Signed index count/capacity bound')
 require((capacity==0 and array==0) or
  (capacity>0 and array%8==0 and 0x10000<=array<array+capacity*16<=2**47),'Index allocation metadata mismatch')
 raw=r.read(observer.ptr(array),used*16) if used else b''
 entries=[]
 for key,value in struct.iter_unpack('<i4xQ',raw):
  require(0<key<min(count,32768),'Index country slot invalid')
  if value:require(observer.ptr(value)%8==0,'Index value pointer alignment')
  entries.append((key,value))
 require(len({k for k,_ in entries})==len(entries),'Duplicate indexed country')
 require(r.read(root+0x140,16)==header,'Index header changed within sample')
 selected=[v for k,v in entries if k==other_slot]
 return dict(count=used,capacity=capacity,array=hex(array),header_raw_hex=header.hex(),
  records_raw_hex=raw.hex(),records_sha256=hashlib.sha256(raw).hexdigest(),
  key_present=bool(selected),selected_pointer=selected[0] if selected else 0,
  lookup_zero_reason=('matched_null_value' if selected and selected[0]==0 else 'missing_key' if not selected else None))''')
s=replace_block(s,'def sample_selected(', 'def base_result(', '''def sample_selected(r,observer,r24,base,root,table,handles,actor,target):
 require(root['count']==1380 and type(table) is bytes and len(table)==1380*8,'Full1380 table required')
 forward=r24.pair_sample(r,observer,base,root,handles,actor,target)
 reverse=r24.pair_sample(r,observer,base,root,handles,target,actor)
 pairs=[forward,reverse];r24.check_country_table_binding([dict(directional_pairs=pairs)],table)
 require(forward['actor']['address']!=forward['target']['address'],'Country pointer alias')
 left=nullable_index(r,observer,int(forward['relation_root'],16),forward['target']['slot'],1380)
 right=nullable_index(r,observer,int(reverse['relation_root'],16),reverse['target']['slot'],1380)
 require(left['selected_pointer']==right['selected_pointer'],'One-sided or mismatched selected task pointer')
 address=left['selected_pointer'];task=None
 if address:
  body=r.read(observer.ptr(address),0x40)
  first,second=struct.unpack_from('<QQ',body,0x10)
  require(struct.unpack_from('<Q',body)[0]==base+VT and struct.unpack_from('<I',body,8)[0]==357,
   'Other task vtable/marker; unknown, not absence')
  require(body[0x28]==0,'Nonzero raw byte at P+28; unknown, not absence')
  require({first,second}=={handles[actor],handles[target]},'Task full endpoint set differs')
  task=dict(address=hex(address),body_raw_hex=body.hex(),vtable_rva=hex(VT),
   endpoint1_at_10=hex(first),endpoint2_at_18=hex(second),
   raw_u32_at_08=struct.unpack_from('<I',body,8)[0],
   raw_u32_at_20=struct.unpack_from('<I',body,0x20)[0],raw_u32_at_24=struct.unpack_from('<I',body,0x24)[0],
   raw_byte_at_28=body[0x28],raw_u64_at_30=hex(struct.unpack_from('<Q',body,0x30)[0]),
   raw_u32_at_38=struct.unpack_from('<I',body,0x38)[0],raw_u32_at_3c=struct.unpack_from('<I',body,0x3c)[0],
   endpoint_business_roles_verified=False,complete_cpp_class_verified=False)
  state='selected_task_present'
 else:state='selected_task_absent'
 for item in (forward['actor'],forward['target']):
  fresh=r24.owned_country(r,observer,base,root,int(item['handle'],16),item['tag'])
  require(fresh==item and struct.unpack_from('<Q',table,item['slot']*8)[0]==int(item['address'],16),'Country/table changed within pass')
 require(observer.roots(r,base)==root,'Roots changed within pass')
 return dict(state=state,selected_task_present=bool(address),directional_pairs=pairs,
  forward_index=left,reverse_index=right,task=task,
  absence_scope='Both selected native-lookup values are zero; missing keys and matched NULL values remain separate facts.',
  extra_reader_guards_not_native_getter_checks=['Qii capacity at root+148','positive bounded unique keys',
   'canonical aligned nonzero pointers','both directions same selected value','typed vtable and raw357',
   'complete endpoint set','P+28 byte zero'],
  native_getter_does_not_check=['vtable','raw357','endpoints','P+28','capacity','uniqueness','full_handle'])''')
s=s.replace('loaded code/slot before/after','loaded code before/after')
s=s.replace("'selected_index_absent'","'selected_task_absent'")
s=s.replace("id='current_bilateral_integration_task'","id='current_bilateral_support_heir_task'")
s=s.replace("actions_for_reference=['integrate_union','cancel_integration']","actions_for_reference=['support_heir','stop_supporting_heir']")
s=s.replace("raw_field_20_semantics='unknown; not a date or progress'","raw_fields_semantics='20/24/30/38/3c unknown; no date or progress; endpoints are unlabeled raw handles'")
s=s.replace("'integration completion'","'final heir result'")
save('support_heir_current_observer.py',s)

r=(OLD/'run_offline.py').read_text(encoding='utf-8')
r=r.replace('integration_task_observer','support_heir_current_observer').replace('_integration_candidate_offline_job','_support_heir_offline_job')
r=r.replace("'run_offline.py','source-manifest.json'","'run_offline.py','prepare_source.py','source-manifest.json'")
r=r.replace("peak=r['job'].get('peak_job_memory')","peak=r['job'].get('peak_job_commit')")
save('run_offline.py',r)
print('source-only draft written; no manifest/test/CLI/process execution')
