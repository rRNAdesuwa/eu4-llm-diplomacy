"""Independent retained-only restart capture replay. Never executes target/author code."""
import ast,collections,copy,ctypes,hashlib,json,re,struct,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
SUB='work/reports/peace-current-pending-observer-live-after-restart-20261016-r2/'
CAND='work/candidates/peace-current-pending-observer-1375-v1/'
OUT=ROOT/'work/reports/peace-current-pending-observer-live-after-restart-independent-review-20261016-r2-review2'
LIMIT=16*1024**2;CAP=4*1024**2;PRIOR_SEARCH=3502427;MANUAL=1024**2;TAIL=1024**2
P={};C={};J=[]
PRIOR_FAILED_REVIEW=3825364;PRIOR_PROOF={}
REUSE_NATIVE={'work/reports/native-owned-peace-1375.json','work/reports/native-pair-replies-1375.json'}
HARD={'capture.json':(71780,'6c25eb2b08b220191b7683d9b26f965b37ab14ea5424aab048d0894be5416250'),'receipt.json':(6232,'2a82a211a1b048a6bbdf41458bccb64aad25aa681f903eeade24b47106559370'),'manifest.json':(4114,'b4456b4d3d269a08647749a91d3bef940ee4bca99d26369cda28f98a9d3eda35'),'capture_once.py':(9639,'27a7696769ac9101c1a15d9f0d33706c27d7e9867e9c10e259d69dc6b9379cc3'),'preparation.json':(1746,'c263a1c5ad333f98ac4e8cfdf3bbe28686d3ce0049282c7e7555bf7a5e061277')}
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
def need(v,m):
 if not v:raise AssertionError(m)
def memory():
 class PMC(ctypes.Structure):
  _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t)for n in('pw','w','pp','p','pn','n','pf','ppf','private')]
 k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi');c=PMC();c.cb=ctypes.sizeof(c)
 need(p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(c),c.cb),'own memory query')
 peak=max(c.private,c.ppf);need(peak<1024**3 and peak<=768*1024**2,'own memory guard');return peak
def pin(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def norm(n):
 p=(ROOT/n).resolve();need(p.is_relative_to(ROOT),'local flat source');r=p.relative_to(ROOT).as_posix()
 need(not r.startswith('work/deps/') and p.name.lower()!='eu4.exe','no PE/native engine body');return r
def read(n,phase,q=None):
 n=norm(n);p=ROOT/n;size=p.stat().st_size
 need(size<=CAP and sum(e['bytes']for e in J)+size+PRIOR_FAILED_REVIEW+PRIOR_SEARCH+MANUAL+TAIL<=LIMIT,'own preread16MiB including prior search')
 memory();b=p.read_bytes();d=pin(b);J.append(dict(path=n,phase=phase,**d));need(len(b)==size,'size stable')
 if q is not None:need(d=={k:q[k]for k in('bytes','sha256')},'exact pin '+n)
 return b
def admit(n,q):
 n=norm(n);q={k:q[k]for k in('bytes','sha256')}
 if n in P:need(P[n]==q,'consistent pin')
 elif n in REUSE_NATIVE:
  need(PRIOR_PROOF.get(n)==q,'Native bulk prior completed before-pin proof');P[n]=q
 else:C[n]=read(n,'before',q);P[n]=q
def strict(b):
 def pairs(xs):
  d={}
  for k,v in xs:need(k not in d,'duplicate JSON key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def obj(n):return strict(C[n])
def triple(n):return dict(path=n,**P[n])
def write(n,x):
 b=(json.dumps(x,sort_keys=True,ensure_ascii=True,indent=2)+'\n').encode()
 with(OUT/n).open('xb')as f:f.write(b)
 return pin(b)
def main():
 global PRIOR_PROOF
 OUT.mkdir(exist_ok=False);self_before=memory()
 previous_failure='work/reports/peace-current-pending-observer-live-after-restart-independent-review-20261016-r2/failure.json'
 previous_raw=read(previous_failure,'prior_failed_review_proof');previous=strict(previous_raw)
 need(previous['completed_bytes']==PRIOR_FAILED_REVIEW and 'captured current32source map' in previous['traceback'],'Exact previous reviewer schema stop')
 PRIOR_PROOF={e['path']:{k:e[k]for k in('bytes','sha256')}for e in previous['reads']if e['phase']=='before'}
 admit(previous_failure,pin(previous_raw))
 previous_source='work/review_peace_pending_restart_r2_20261016.py';previous_source_raw=read(previous_source,'prior_reviewer_source_preserved');admit(previous_source,pin(previous_source_raw))
 for n,(s,h)in HARD.items():admit(SUB+n,dict(bytes=s,sha256=h))
 m=obj(SUB+'manifest.json');c=obj(SUB+'capture.json');receipt=obj(SUB+'receipt.json');prep=obj(SUB+'preparation.json')
 for k in ('local_pins','captured_source_pins'):
  for n,q in m[k].items():admit(n,q)
 sm=obj(CAND+'source-manifest.json');need(len(sm['source_pins'])==32 and sum(q['bytes']for q in sm['source_pins'].values())==PRIOR_SEARCH,'32source search prior exact size')
 for n,q in sm['source_pins'].items():admit(n,q)
 direct=c['source_graph']['reused_direct']['selected_source_pins']
 for n in ['work/candidates/frida-entry-observer-1375-v1/capture_once.py','work/candidates/frida-entry-observer-1375-v1/host-manifest.json','work/capture_direct_truce_flags_20261015.py']:admit(n,direct[n])
 old=prep['original_controller'];admit(old['path'],old)
 own=Path(__file__).relative_to(ROOT).as_posix();b=read(own,'ownsource');P[own]=pin(b);C[own]=b
 runtime_review_pins={sm[k]['path']:{part:sm[k][part]for part in('bytes','sha256')}for k in('independent_source_review','production_review')}
 need(c['source_graph']['candidate']['source_pins']==sm['source_pins']|runtime_review_pins and len(c['source_graph']['candidate']['source_pins'])==34,'captured32owner plus2runtime review actualmap')
 graph=hashlib.sha256(json.dumps(sm['source_pins'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()
 need(graph==sm['source_graph_sha256']==c['source_graph']['candidate']['source_graph_sha256']=='488dbb0d2766e54cdea216c5ffd348c58ef93508d10dffe3e9341261ccec2ece','source graph canonical digest')
 need(sm['sealed']and sm['runtime_capture_authorized']and sm['native_ready']is False and c['source_graph']['candidate']['manifest']==P[CAND+'source-manifest.json'],'production source pin')
 for role in ('independent_source_review','production_review'):
  f=obj(sm[role]['path']);need(f['sealed']and f['passed']and f['blocking_findings']==[] and f['subject_cli_pin']==P[CAND+'peace_current_pending.py']and f['subject_source_graph_sha256']==graph,'production/source exact subject witness')
  if role=='production_review':need(f['approved_for_current_readonly_status'],'current readonly production scope')
 need(obj(SUB+'source-before.json')==obj(SUB+'source-after.json')==m['captured_source_pins']==receipt['source_before']==receipt['source_after'],'controller source prepost exact')
 need(C[SUB+'capture.json']==C[SUB+'stdout.txt'] and not C[SUB+'stderr.txt'],'raw stdout identical/empty stderr')
 need(receipt['capture']==P[SUB+'capture.json']and receipt['control_passed']and receipt['control_failure']is None and receipt['status_attempts']==receipt['maximum_status_attempts']==1,'one cleanly controlled status attempt')
 selection=dict(pid=98548,creation='01dd5d0e670312c4',actor='FRA',target='ENG')
 need(c['selection']==receipt['selection']==prep['selection']==selection,'fixed new process identity and pair')
 need(c['identity']['pid']==98548 and c['identity']['creation']==selection['creation']and re.fullmatch('[0-9a-f]{32}',c['identity']['session']),'identity/nonce shape')
 need(c['identity_purpose']=='Fresh readonly nonce, not installed session or original request','nonce not installed session')
 job=obj(SUB+'job.json');need(job==receipt['job'] and job['exit_code']==2 and job['error']is None and job['job_total_processes']==2 and job['job_active_processes_final']==0 and job['direct_child_collected']and not job['completed_command_descendants_terminated'],'expectedunknown Job exit2/allchildren collected')
 need(job['peak_job_commit']==46116864 and job['memory_limit']==805306368 and job['existing_target_game_assigned_to_job']is False,'Job scope no game ownership')
 need(c['status']=='unknown'and c['samples']==[]and c['selected_queue_presence']is None and c['selected_two_pass_equal']is False and c['commit_after_context_exit']is False,'unknown cannot be absence or committed queue state')
 need(c['errors']==[dict(message='Unsupported current Mod',stage='sample',type='ValueError')],'precise profile refusal')
 need(c['normal_context_exit']and c['held_handle_cleared']and c['close_os_return_checked']is False,'normalcontext/handle None; OSclose return unverified')
 need(c['disk_before']==c['disk_after']and c['disk_before']['bytes']==38462504 and c['disk_before']['sha256']==c['game_sha256']==GAME,'diskSHA onlyauthor witness, no PE read here')
 journal=c['raw_ordered_read_journal'];need(len(journal)==120,'120 ordered reads')
 for i,e in enumerate(journal,1):
  raw=bytes.fromhex(e['raw_hex']);address=int(e['address'],16)
  need(e['ordinal']==i and e['status']=='complete'and len(raw)==e['requested_bytes']==e['returned_bytes'],'complete exact-width read')
  need(0<address<2**47 and address+len(raw)<=2**47,'canonical bounded source address')
  if not e['code_bytes']and len(raw)>=8:need(address%8==0,'aligned data/entry/host reads')
 need(sum(e['requested_bytes']for e in journal)==sum(e['returned_bytes']for e in journal)==10371 and max(e['requested_bytes']for e in journal)==8192,'sharedRPM raw sum')
 need(c['rpm_budget']['calls_attempted']==120 and c['rpm_budget']['bytes_requested']==c['rpm_budget']['bytes_returned']==10371 and c['rpm_budget']['largest']==8192 and c['rpm_budget']['limits']==dict(calls=4096,bytes=524288,single_read=65536),'RPMbudget matches journal')
 base=int(journal[0]['address'],16);need(base==0x7ff635e20000 and journal[0]['stage']=='entry_PE'and journal[0]['requested_bytes']==8192,'single entry8192 header')
 header=bytes.fromhex(journal[0]['raw_hex']);lfanew=struct.unpack_from('<I',header,0x3c)[0]
 need(header[:2]==b'MZ'and lfanew+264<=len(header)and header[lfanew:lfanew+4]==b'PE\0\0'and struct.unpack_from('<H',header,lfanew+4)[0]==0x8664 and struct.unpack_from('<H',header,lfanew+24)[0]==0x20b,'retained PE header AMD64 PE32+ only, no disk PE open')
 at=1
 def take(stage,address,size,code=False):
  nonlocal at
  e=journal[at];at+=1;need((e['stage'],int(e['address'],16),e['requested_bytes'],e['code_bytes'])==(stage,address,size,code),'exact reader sequence '+str(at));return bytes.fromhex(e['raw_hex'])
 def q(stage,a):return struct.unpack('<Q',take(stage,a,8))[0]
 def i(stage,a):return struct.unpack('<i',take(stage,a,4))[0]
 def by(stage,a):return take(stage,a,1)[0]
 def roots(stage):
  game=q(stage,base+0x233fe78);db=q(stage,base+0x233d8d0);need(q(stage,game)==base+0x1cb00c8,'game vtable')
  array=q(stage,db+0x118);cap,count=struct.unpack('<ii',take(stage,db+0x120,8));need(count==cap==1380,'current capacity/count')
  server=q(stage,game+0x1e00);need(q(stage,server)==base+0x1cb8460,'fixed server vtable');pause=q(stage,server+0x418);need(q(stage,pause+0x50)==server,'pause owner')
  d=dict(game=hex(game),database=hex(db),array=hex(array),capacity=cap,count=count,server=hex(server),pause=hex(pause),date=i(stage,game+0x1dd0),manual_pause=by(stage,pause+0x48),reset=by(stage,game+0x7485),load_source=q(stage,game+0x74c8),recalculating=by(stage,game+0x2521),ironman=by(stage,game+0x24d0),current_player=q(stage,game+0x1e60),alternate_player=q(stage,game+0x1e68),selector=by(stage,game+0x1e66))
  h=d['current_player'];hb=h.to_bytes(8,'little');slot=int.from_bytes(hb[4:6],'little',signed=True)
  need(hb[:4]==b'FRA\0'and hb[7]!=0 and hb[6]==0 and 0<=slot<count and d['date']>0 and d['manual_pause']==1 and d['reset']==d['load_source']==d['recalculating']==d['ironman']==d['selector']==0 and d['alternate_player']==0x2d2d2d,'root guards/currentplayer only, not selectedcountry tablebinding')
  return d
 prefix=bytes.fromhex('4c89442418555357488d6c24b04881ec50010000488b159d8f2901488bf9440f')
 hosttext=C['work/candidates/frida-entry-observer-1375-v1/capture_once.py'].decode();need(prefix.hex()in hosttext,'frozen host prefix source')
 def host(stage):
  first=roots(stage);second=roots(stage);need(first==second,'two internal host root samples')
  original=take(stage,base+0x10a6ec0,32);need(original==prefix,'entry prefix original')
  outer=q(stage,base+0x242bf50);need(q(stage,base+0x242bf50)==outer,'outer double pointer')
  h=[take(stage,outer+x,8)for x in(0,0x10)];need([int.from_bytes(x,'little')for x in h]==[base+0x1c48bf8,base+0x1c48c80],'outer typed slots')
  children=[take(stage,outer+x,size)for x,size in((0x40,8),(0x48,1),(0x70,8),(0x78,8),(0x80,1))]
  need(int.from_bytes(children[0],'little')==int(first['server'],16)and children[1]==children[4]==b'\0'and children[2]==children[3]==bytes(8),'outer current/transition/pending/previous guards')
  return dict(roots=first,outer=hex(outer),outer_vtable_hex=[x.hex()for x in h],children_hex=[x.hex()for x in children],prefix_address=hex(base+0x10a6ec0),prefix32_hex=prefix.hex(),process_identity_checked=True,module_set_equal=True,rpm_budget=dict(calls=46,bytes=300,largest=32))
 pre=host('host_before');need(pre==c['precheck'],'raw host_before matches exported view')
 profile=obj('work/reports/peace-current-pending-reader-design-20261016-r1/loaded-code-candidates.json')
 need(profile['bytes_per_pass']==735 and len(profile['ranges'])==4,'four fixed code ranges')
 def code(stage):
  got=[]
  for r in profile['ranges']:
   expected=bytes.fromhex(r['raw_hex']);rva=int(r['start_rva'],16);raw=take(stage,base+rva,len(expected),True)
   need(raw==expected and hashlib.sha256(raw).hexdigest()==r['sha256'],'loaded retained code raw/source profile')
   got.append(dict(bytes=len(raw),raw_hex=raw.hex(),rva=hex(rva),sha256=hashlib.sha256(raw).hexdigest()))
  return got
 codepre=code('code_before');need(codepre==c['code_before'],'code pre735')
 root1=roots('sample_1');need(root1==pre['roots'],'fresh roots equal/paused')
 guardraw=take('sample_1',base+0x233e064,4);value=struct.unpack('<i',guardraw)[0]
 need(at==70 and guardraw.hex()=='01000000'and value==1 and value!=-1,'sample1 ordinal70 signed1 rejects expected-1')
 codepost=code('code_after');post=host('host_after')
 need(codepost==codepre==c['code_after']and post==pre==c['postcheck']and at==120,'after code/host same and every journal row consumed')
 stages={s:dict(calls=sum(e['stage']==s for e in journal),bytes=sum(e['requested_bytes']for e in journal if e['stage']==s))for s in ('entry_PE','host_before','code_before','sample_1','code_after','host_after')}
 need(stages=={'entry_PE':dict(calls=1,bytes=8192),'host_before':dict(calls=46,bytes=300),'code_before':dict(calls=4,bytes=735),'sample_1':dict(calls=19,bytes=109),'code_after':dict(calls=4,bytes=735),'host_after':dict(calls=46,bytes=300)},'exact stage partition')
 need(not any(e['stage']=='sample_2'or int(e['address'],16)==int(root1['array'],16)for e in journal),'no countrytable/second sample')
 cli=C[CAND+'peace_current_pending.py'].decode();lines=cli.splitlines();need("require(r.i(cap.base+0x233e064)==-1,'Unsupported current Mod')"in lines[279] and "table=r.read(int(root['array'],16),1380*8)"in lines[280],'guard dominates countrytable line281')
 need('def i(self,a):return struct.unpack(\'<i\',self.read(a,4))[0]'in cli,'guard is signedDWORD reader')
 # Derivation proof: normalize only declared PID/creation/UTC/schema/restart-disclosure metadata.
 oldtree=ast.parse(C[old['path']].decode());newtree=ast.parse(C[SUB+'capture_once.py'].decode())
 mappings={98548:38076,'98548':'38076','01dd5d0e670312c4':'01dd5cac0b1ad003','2026-10-16T01:50:11.843236Z':'2026-10-15T18:46:04.2554391Z'}
 for k in('CLAIM','CONTROL','DELIVERY'):mappings['EU4-PEACE-CURRENT-PENDING-AFTER-RESTART-LIVE-R2-'+k+'/1']='EU4-PEACE-CURRENT-PENDING-FIRST-LIVE-'+k+'/1'
 removed={'after_user_requested_restart','prior_process_pid','prior_status_frozen_unknown','UI_preparation_separate_from_this_controller','observed_UI_date','observed_UI_paused'}
 class Normalize(ast.NodeTransformer):
  def visit_Constant(self,n):
   if type(n.value)in(int,str)and n.value in mappings:n.value=mappings[n.value]
   return n
  def visit_Call(self,n):
   self.generic_visit(n);n.keywords=[k for k in n.keywords if k.arg not in removed]
   for k in n.keywords:
    if k.arg=='second_status_attempt':k.value=ast.Constant(value=False)
   return n
 need(ast.dump(oldtree,include_attributes=False)==ast.dump(Normalize().visit(newtree),include_attributes=False),'controller AST only declared metadata/restart delta')
 replymanifest=obj('bridge/diplomacy_reply_observer_manifest_1375.json')
 nextnames=['work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/static.json','work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/disassembly.txt','work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/trace.py','work/reports/native-action-fields-1375.json']
 nextscope={n:replymanifest['source_pins'][n]for n in nextnames};need(sum(q['bytes']for q in nextscope.values())==1551988,'finite next source proposal only; not read now')
 for n,q in list(P.items()):C[n]=read(n,'after',q)
 hits=[];patterns=['233e064','14233e064',str(0x233e064),'Unsupported current Mod']
 for n in sm['source_pins']:
  for number,line in enumerate(C[n].decode('utf-8').splitlines(),1):
   if any(p.lower()in line.lower()for p in patterns):hits.append(dict(path=n,line=number,text=line[:500],source_pin=P[n]))
 need(len(hits)==4 and {h['path']for h in hits}=={'bridge/diplomacy_reply_observer.py',CAND+'peace_current_pending.py',CAND+'test_peace_current_pending.py','work/reports/peace-current-pending-reader-design-20261016-r1/retained-layout.json'},'exact selected source search results')
 rawreplay=dict(schema='EU4-PEACE-RESTART-R2-INDEPENDENT-RAW/1',source_capture=triple(SUB+'capture.json'),base=hex(base),entry_header=dict(bytes=8192,e_lfanew=lfanew,AMD64=True,PE32_plus=True,sha256=hashlib.sha256(header).hexdigest(),not_a_new_disk_PE_read=True),stages=stages,RPMcalls=120,RPMbytes=10371,largest=8192,
  host_before_after_equal=True,code_before_after_equal=True,code_bytes_each_pass=735,sample1_fresh_roots_equal=True,
  refusal=dict(ordinal=70,stage='sample_1',address=hex(base+0x233e064),rva='0x233e064',raw_hex=guardraw.hex(),width=4,reader_signed_i32=value,source_required_i32=-1,source_cli_line=280,error='Unsupported current Mod',countrytable_next_line=281),
  no_country_table_or_country_handle_or_queue_reads=True,no_sample2=True,selected_presence=None,commit_after_context_exit=False,field_repeated_postread=False,
  source_field_hits=hits,field_native_semantics_verified=False,finite_next_source_proposal=nextscope,next_source_body_opened=False,
  source_proof_boundary='Only exact lexical spellings/decimal matches in32 fixed sources. Reader labels/copy and synthetic -1 setup are not native writer/consumer/enum/class evidence. No whole repository/binary or indirect-alias absence claim.')
 write('raw-replay.json',rawreplay)

 charged=sum(e['bytes']for e in J);upper=charged+PRIOR_FAILED_REVIEW+PRIOR_SEARCH+MANUAL+TAIL;need(upper<=LIMIT,'full own stage incl prior search16M')
 finding=dict(schema='EU4-PEACE-RESTART-R2-INDEPENDENT-REVIEW/1',sealed=True,passed=True,blocking_findings=[],
  scope='Full non-author retained raw/guard/source diagnostic of one restarted-process current-status refusal; no author execution or new runtime/native/code acquisition',
  subject_capture_pin=triple(SUB+'capture.json'),subject_receipt_pin=triple(SUB+'receipt.json'),subject_manifest=triple(SUB+'manifest.json'),subject_controller=triple(SUB+'capture_once.py'),subject_preparation=triple(SUB+'preparation.json'),
  role_disclosure='war_api independently reviews root-authored restart capture/controller, not its runtime author. Earlier roles include v5/v6 author and R80/R81 reviewers; none grants this reader current runtime or field semantics authority.',
  result='Validated unknown; the signedDWORD profile guard at CLI280 refused raw1 before countrytable/selected handles/queues. No peace presence/absence or effect is established.',
  raw_checks=['All120 entries/10371B replayed in order with exact addresses and lengths, including entry8192, host300+300, code735+735, roots105 plus guard4.','Both host samples reproduce the exported typed/root/currentapp guard views; four code ranges match fixed retained source bytes before-after.','First sample reaches scalar field only after paused fresh root equality. It fails signed1!=-1, before line281 countrytable read; sample2 is never reached, samples remains empty.','Normal context exit/held None and postsource/code/host guards are consistent; OS CloseHandle return remains explicitly unchecked.'],
  field_diagnosis=dict(rva='0x233e064',value=1,raw_hex='01000000',required_by_source=-1,source_label='Unsupported current Mod',label_is_not_native_semantic_proof=True,native_writer_consumer_meaning='unknown in this selected source scope',
   must_not_infer=['installed Mod or Chinese localization Mod','multiplayer or modified game mode','a game defect or action rejection','current queue absent','why this field must be -1','field value stable after refusal']),
  provenance=dict(source32_pin_count=32,runtime_review_actual_pin_count=34,source32_bytes=3502427,graph_sha256=graph,controller_AST_only_declared_metadata_delta=True,source_prepost_equal=True,
   frozen_host215_local_11_external='Existing captured verification witness only; not recursively rehashed/replayed here.',process_identity_path_modules_rights_diskSHA='Source/receipt metadata witnesses; captured RPM alone cannot independently authenticate these OS facts.',UI_date_pause='Root preparation witness plus paused root scalar/date; no independent UI access by reviewer.',nonce='Fresh read-only correlation nonce, not installed session or original API request.'),
  precise_limits=['Own first reviewer stopped after3825364B on an incorrect32-only actualmap equality. Runtime verify_sources adds exact source/production findings, so captured actual34=owner32+2; original reviewer/failure/read journal are preserved. R2 uses the two native bulk files original completed BEFORE pins and current AFTER hashes to avoid duplicating their before reads within16MiB. No author/game operation was rerun.',
       'Typeguard pass means the frozen observer accepted the sampled vtable/root pattern; it does not establish meaning of separate global233e064.','Current-player FRA handle bytes were read in roots; selected FRA/ENG country objects, full table mapping and queue nodes were not read.','The RPM scope string describes maximum profile coverage; actual journal does not contain both tables/queues.','Pre/post equality can miss ABA/transient changes and is no world lease/atomic snapshot. The guard field itself was read only once.','Unknown is not native rejection/peace completion/absent queue or original request attribution.','Two disk SHA passes are author witnesses outside the RPM10371B bill; the reviewer did not open the PE.','8835.005ms capture duration includes source/disk/host guards; Job14.547s and controller14.664602s are separate scopes, not HTTP RTT.'],
  next_source_scope_proposal=dict(fixed_sources=nextscope,total_source_bytes=1551988,maximum_files=4,ordinary_cap=4194304,task='Only search fixed cached files for this exact global consumer/writer/initialization evidence; preserve actual raw rows/pins and unknowns. No body is read now and no new PE/global-xref scope is authorized.'),
  author_resources=dict(RPMcalls=120,RPMbytes=10371,largest_read=8192,source_graph32_bytes=3502427,Job_total=2,Job_active_final=0,child_exit=2,controller_control_passed=True,Job_peak_commit=46116864,Job_target_game_owned=False,CloseHandle_return_checked=False,all_author_shells_collected_witness=True),
  review_resources=dict(flat_input_files=len(P)-1,source_pins_before_after_equal=True,completed_current_read_events=len(J),completed_current_read_bytes=charged,prior_failed_reviewer_bytes=PRIOR_FAILED_REVIEW,native_bulk_beforepins_reused_from_preserved_failure=True,prior_exact32source_search_bytes=PRIOR_SEARCH,manual_other_inspection_allowance=MANUAL,own_report_local_seal_check_reserve=TAIL,successful_upper_bytes=upper,limit_bytes=LIMIT,ordinary_file_cap=CAP,self_peak_before=self_before,self_peak_after=memory(),software_guard=768*1024**2,one_GiB_stop=True),
  operations=dict(new_gamequeries=0,PE_open_or_stat=0,native_decoder_or_engine_body=0,author_program_or_tests=0,Frida=0,nativecalls=0,source_mutations=0,all_review_shells_collected=True),authority=dict(receipt['authority']))
 need(all(v is False for v in finding['authority'].values()),'allauthorityfalse')
 write('findings.json',finding);write('read-accounting.json',dict(schema='EU4-PEACE-RESTART-R2-INDEPENDENT-READS/1',events=J,prior_failed_reviewer_bytes=PRIOR_FAILED_REVIEW,prior_exact_source_search_bytes=PRIOR_SEARCH,measured_current_bytes=charged,manual_allowance=MANUAL,reserved_local_seal_check=TAIL,successful_upper_bytes=upper,limit=LIMIT,full_OS_IO_claim=False))
 with(OUT/'report.md').open('x',encoding='utf-8')as f:f.write('Independent restart-capture review: validated unknown, no blocking mismatch.\n\n120 ordered RPM reads/10371B replay. Entry8192+host600+code1470+sample109. First sample read global233e064 as signed1 and failed source guard expecting-1 before countrytable/handles/queues. No second sample or state commit. The Mod error is a source label, not native evidence of installed mods, localization or multiplayer. Four fixed source hits only reproduce guard/copy/synthetic setup; native meaning remains unknown.\n\nSource32 and finite host/controller text pins are stable. Normal context exit and held None are retained, OS close return unchecked. No game/PE/decoder/author execution was performed. All effect/native/lease/atomic/retry authority remains false.\n')
 manifestpins=dict(P)
 for n in('raw-replay.json','findings.json','read-accounting.json','report.md'):
  r=(OUT/n).relative_to(ROOT).as_posix();manifestpins[r]=pin(read(r,'own_seal'))
 mp=write('manifest.json',dict(schema='EU4-PEACE-RESTART-R2-INDEPENDENT-MANIFEST/1',sealed=True,passed=True,files=manifestpins,file_count=len(manifestpins),subject_capture=triple(SUB+'capture.json'),native_ready=False,world_lease=False,atomic_snapshot=False))
 print(json.dumps(dict(status='sealed_independent_validated_unknown',findings=pin((OUT/'findings.json').read_bytes()),manifest=mp,own_upper_bytes=upper,flat_sources=len(P)-1,all_shells_collected=True)))
def check():
 raw=read((OUT/'manifest.json').relative_to(ROOT).as_posix(),'own_local_seal_manifest');m=strict(raw)
 count=0
 for n,q in m['files'].items():
  if n.startswith(OUT.relative_to(ROOT).as_posix()+'/'):
   read(n,'own_local_report_pin_check',q);count+=1
 result=dict(schema='EU4-PEACE-RESTART-R2-LOCAL-SEAL-CHECK/1',passed=True,subject_manifest=pin(raw),local_report_pins_checked=count,subject_source_third_pass_executed=False,subject_sources_already_verified_before_after=True,read_bytes=sum(e['bytes']for e in J),scope='Own local sealing only, within1MiB reserve; no third historical/source closure pass',author_PE_game_decoder_tests=0,all_shells_collected=True)
 write('verification.json',result);print(json.dumps(result))
if __name__=='__main__':
 try:
  if sys.argv[1:]==['--check']:check()
  else:need(sys.argv[1:]==[],'only own retained review or localsealcheck');main()
 except BaseException:
  if OUT.exists():
   with(OUT/'failure.json').open('x',encoding='utf-8')as f:json.dump(dict(traceback=traceback.format_exc(),reads=J,completed_bytes=sum(e['bytes']for e in J),prior_search_bytes=PRIOR_SEARCH,no_author_or_game_rerun=True),f,indent=2)
  raise
