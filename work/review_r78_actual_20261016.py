"""Independent retained-only R78 6B sample audit; no author program/target access."""
import ast
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
SUB='work/reports/server-expected-owner-sample-data-20261016-r78/'
OUT=ROOT/'work/reports/server-expected-owner-sample-data-actual-independent-review-20261016-r78'
TOP={
 'data-final-manifest.json':(11003,'8724cc5b75048f4915a8badfd9f2e0209fbaa13a856c819e80bc4359d35b236e'),
 'data-contract.json':(3760,'0a3c3febf6c0c0b39c1ea96bd33127f85d01306c864e9d21b6eb1e1ebd6295a1'),
 'data-owned.json':(791,'e18e5597d2f18812a7e8f5856c0d415cda5069afccc81ce4ead5ac2d5cef353a'),
 'capture.json':(45206,'dc61a6b21b0667516115278252804c357584a42c455c66d1f4a59f770fbf4b88'),
 'data-filecheck.json':(7223,'1bf7f0e2c82284b61b675c37306de9d3915dafe7948bacc7c815b22e882c8bad'),
 'data-read-accounting.json':(6530,'5265bdff39866b3a1c14897a12db1c1e6e87e08e22a5ba32ab48f857bc8955b7'),
 'data-delivery.json':(1134,'41bb235a0fb27f05d22a614a1b3a8cccdea5a013f83c03d629b65247a84b62ba'),
 'data-command-receipts.json':(1931,'cbcad512165288e0255ef6f7c6af047ea473bf50ecadf98e17485c9ca1f4d896'),
 'data-publication.json':(1263,'14f0e9fd9572aec96330874171ca65ee8f6907f6a5a59d84b8b4a5f2695a4411'),
}
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
READS=[];PEAK=0;MANUAL=1024*1024;TAIL=2*1024*1024
def need(ok,message):
 if not ok:raise AssertionError(message)
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def parse(raw):
 def pairs(items):
  obj={}
  for k,v in items:need(k not in obj,'duplicatekey');obj[k]=v
  return obj
 def finite(v):
  n=float(v);need(math.isfinite(n),'nonfiniteexponent');return n
 return json.loads(raw.decode('utf8'),object_pairs_hook=pairs,parse_float=finite,
  parse_constant=lambda v:(_ for _ in()).throw(ValueError(v)))
def memory():
 global PEAK
 class P(ctypes.Structure):
  _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t)for n in(
   'peak_working','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
 p=P();p.cb=ctypes.sizeof(p);k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=wintypes.HANDLE
 a=ctypes.WinDLL('psapi',use_last_error=True);a.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(P),wintypes.DWORD]
 need(a.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(p),p.cb),'ownmemory')
 PEAK=max(PEAK,p.private,p.peak_pagefile);need(0<PEAK<=768*1024*1024 and PEAK<1024*1024*1024,'ownsoftwareguard')
 need(sum(x['bytes']for x in READS)+MANUAL+TAIL<=16*1024*1024,'review16MiB cap')
def read(path,want=None,phase='before'):
 need((path.startswith('work/reports/')or path=='work/review_r78_actual_20261016.py')and 'work/deps/'not in path,'admitted flat text')
 need(not path.lower().endswith(('.exe','.dll','.pyd')),'noPEenginebody')
 p=ROOT/path;need(p.stat().st_size<=4*1024*1024,'ordinary4M');raw=p.read_bytes()
 READS.append({'phase':phase,'path':path,'bytes':len(raw)});memory()
 if want is not None:need(pin(raw)==want,'pin '+path)
 return raw
def save(name,obj):
 raw=(json.dumps(obj,indent=2,ensure_ascii=True)+'\n').encode('utf8')
 with (OUT/name).open('xb')as f:f.write(raw)
 return pin(raw)

def audit():
 OUT.mkdir(exist_ok=False)
 top={SUB+n:{'bytes':v[0],'sha256':v[1]}for n,v in TOP.items()}
 raw={SUB+'data-final-manifest.json':read(SUB+'data-final-manifest.json',top[SUB+'data-final-manifest.json'])}
 final=parse(raw[SUB+'data-final-manifest.json'])
 need(final['sealed']is True and final['flat_file_count']==len(final['source_pins'])==51,'51flat')
 for path,want in final['source_pins'].items():
  if path in top:need(want==top[path],'hard subject graph')
  raw[path]=read(path,want)
 for path,want in top.items():
  if path not in raw:raw[path]=read(path,want)
 pins={p:pin(v)for p,v in raw.items()}
 def p(name):return pins[SUB+name]
 cap=parse(raw[SUB+'capture.json']);owned=parse(raw[SUB+'data-owned.json']);contract=parse(raw[SUB+'data-contract.json'])
 base=parse(raw[SUB+'source-manifest.json']);seed=parse(raw[SUB+'entry-seed.json']);auth=parse(raw[SUB+'run-authorization.json'])
 claim=parse(raw[SUB+'attempt-claim.json']);bill=parse(raw[SUB+'data-read-accounting.json']);check=parse(raw[SUB+'data-filecheck.json'])
 old=parse(raw[SUB+'data-manifest.json']);delivery=parse(raw[SUB+'data-delivery.json']);publication=parse(raw[SUB+'data-publication.json'])
 commands=parse(raw[SUB+'data-command-receipts.json']);actual=parse(raw[SUB+'actual-command.json'])
 need(final['subject_capture']==p('capture.json')and final['subject_contract']==p('data-contract.json')and final['subject_owned']==p('data-owned.json'),'final3subjects')
 need(old['flat_file_count']==len(old['source_pins'])==49 and old['single_actual_invocation']is True,'prior49stage')
 for path,want in old['source_pins'].items():need(final['source_pins'][path]==want==pins[path],'prior49subset')
 need(check['sealed']is True and check['passed']is True and check['subject_manifest']==p('data-manifest.json')and check['flat_pins']==49,'filecheck prior49 notselfref final')
 need(sum(x['bytes']for x in check['read_events'])==check['explicit_filecheck_bytes']==1723216,'firstfilecheckbill')
 need(contract['source_capture']==owned['source_capture']==p('capture.json')and contract['source_owned']==p('data-owned.json'),'contract-owned sourcecaps')
 subjects={'subject_source_manifest':p('source-manifest.json'),'subject_producer':p('produce.py'),'subject_entry_seed':p('entry-seed.json')}
 need(cap['subjects']==claim['subjects']==contract['source_subjects']==subjects,'exact source3subjects')
 need(base['flat_source_count']==len(base['source_pins'])==32 and cap['source_pre']==cap['source_post']==base['source_pins'],'source32prepost')
 for path,want in base['source_pins'].items():need(pins[path]==want,'currentflat source32pin')
 need(cap['source_guard_equal']is True and final['source_pre_post_match']is True,'sourceequalitywitness')
 need(auth['schema']=='EU4-R78-ROOT-AUTHORIZATION/1'and auth['sealed']is True and auth['explicit_start']is True
  and auth['operation']=='one-fixed6B-file-DATA-only'and type(auth['data_rva'])is int and auth['data_rva']==0x1caa8f0
  and type(auth['requested_bytes'])is int and auth['requested_bytes']==6,'root exact span')
 for key,value in subjects.items():need(auth[key]==value,'rootauth source subject')
 need(cap['authorization']['auth_pin']==p('run-authorization.json')and cap['authorization']['reviews']==auth['reviews']
  and claim['authorization']==cap['authorization']and contract['authorization_pin']==p('run-authorization.json'),'authcaptured')
 need(set(auth['reviews'])=={'raw_seed_review','upstream_actual_review','source_peer_review'},'3reviewsgroups')
 for label,group in auth['reviews'].items():
  need(set(group)=={'findings','manifest'},'reviewpairshape')
  for item in group.values():need(pins[item['path']]=={k:item[k]for k in('bytes','sha256')},'reviewrawfilepin')
  finding=parse(raw[group['findings']['path']]);review_manifest=parse(raw[group['manifest']['path']])
  need(finding['sealed']is True and finding['passed']is True and finding['blocking_findings']==[]and review_manifest['sealed']is True,'passedreview')
  if label=='upstream_actual_review':
   for key,want in seed['R76_upstream_subjects_from_real_full_findings'].items():need(finding[key]==want,'realR76subjectfields')
  elif label=='source_peer_review':
   for key,want in subjects.items():need(finding[key]==want,'newsourcepeer3subjects')
  else:
   need(finding['subject_source_manifest']==subjects['subject_source_manifest']and finding['subject_entry_seed']==subjects['subject_entry_seed']
    and type(finding['data_rva'])is int and finding['data_rva']==0x1caa8f0 and type(finding['requested_bytes'])is int and finding['requested_bytes']==6,'rawentryspan')
 need(claim['single_attempt']is True and claim['automatic_retry']is False and claim['plan']==cap['plan'],'singleclaim plan')
 account=cap['accounting'];attempts=account['source_read_attempts']
 # Reconstruct ordered physical-file expectations from fixed graph and exact auth review order.
 review_paths=[item['path']for group in auth['reviews'].values()for item in(group['findings'],group['manifest'])]
 expected_paths=[SUB+'source-manifest.json',SUB+'entry-seed.json',SUB+'produce.py',SUB+'run-authorization.json']+review_paths
 expected_paths+=[SUB+'source-manifest.json',SUB+'source-manifest.json']+list(base['source_pins'])+[SUB+'source-manifest.json',
  'work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json']
 expected_paths+=[SUB+'source-manifest.json']+list(base['source_pins'])+[SUB+'source-manifest.json',SUB+'entry-seed.json',SUB+'produce.py',SUB+'run-authorization.json']+review_paths
 need(len(expected_paths)==len(attempts)==89,'89ordered reads')
 for event,path in zip(attempts,expected_paths):
  want=pins[path]
  need(event['path']==path and event['expected_bytes']==event['returned_bytes']==want['bytes']and event['complete']is True and event['sha256']==want['sha256'],'ordered source pin/review journal')
 need(sum(v['returned_bytes']for v in attempts)==account['source_returned_bytes']==3481090<4194304,'source4M actualbill')
 cache_path='work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json';cache=parse(raw[cache_path])
 sections=cache['sections'];matches=[s for s in sections if int(s['rva'],16)<=0x1caa8f0 and 0x1caa8f6<=int(s['rva'],16)+s['raw_size']]
 need(len(matches)==1 and matches[0]['name']=='.rdata','wholeunique .rdata')
 section=matches[0];start=int(section['rva'],16);size=section['raw_size'];offset=section['raw_file_offset'];virtual=section['virtual_size']
 header=bytes.fromhex(section['section_header_raw_hex'])
 need(len(header)==40 and struct.unpack_from('<IIII',header,8)==(virtual,start,size,offset),'cached rawheaderfields')
 where=offset+0x1caa8f0-start;need(where==30055152 and 0x1caa8f6<=start+virtual and where+6<=38462504,'cached virtual/raw/file spans')
 need(cap['plan']==seed['prepared_cached_mapping_plan']and cap['plan']['rva']==0x1caa8f0 and cap['plan']['end_exclusive']==0x1caa8f6
  and cap['plan']['size']==6 and cap['plan']['file_offset']==where,'fixed plan')
 sample=bytes.fromhex(owned['raw_hex']);need(sample==b'desert'and len(sample)==owned['bytes']==6 and b'\0'not in sample,'ownedexact6noNUL')
 need(hashlib.sha256(sample).hexdigest()==owned['raw_sha256']and owned['ASCII']==owned['UTF8']=='desert'
  and owned['first_NUL_within_owned6']is None and owned['rva_start']=='0x1caa8f0'and owned['end_exclusive']=='0x1caa8f6'
  and owned['file_offset']==where,'samplediagnosticsownedhash')
 need(account['DATA_reads']==[{'rva':0x1caa8f0,'file_offset':where,'section':'.rdata','requested_bytes':6,'returned_bytes':6,'raw_hex':sample.hex(),'complete':True}]
  and account['DATA_returned_bytes']==6,'one6BDATArange')
 interpret=cap['owned_interpretation'];need(interpret['raw_hex']==sample.hex()and interpret['first_NUL_offset']is None
  and interpret['ASCII']==interpret['UTF8']=={'decodable':True,'text':'desert'}and interpret['source_byte7_or_later_read']is False,'interpretationrawbinding')
 need(interpret['consumption_length_verified']is False and interpret['six_is_root_sample_budget_not_proved_length']is True,'no consumerlengthupgrade')
 for key,phase in [('PE_before','before'),('PE_after','after')]:
  event=cap[key];need(event['phase']==phase and event['complete']is True and event['expected_bytes']==event['returned_bytes']==38462504 and event['sha256']==GAME,'fullPE SHA witness')
 need(account['PE_full_SHA_reads']==[cap['PE_before'],cap['PE_after']]and account['PE_full_SHA_returned_bytes']==76925008,'twoSHA ledgers')
 need(account['PE_full_SHA_returned_bytes']+account['DATA_returned_bytes']==76925014,'PEsourcehash separateDATA')
 need(cap['normal_targetfile_close']is True and cap['commit_after_close_and_final_guards']is True,'normalclosecommitwitness')
 producer=raw[SUB+'produce.py'].decode('utf8');functions={n.name:n for n in ast.parse(producer).body if isinstance(n,ast.FunctionDef)}
 run=ast.get_source_segment(producer,functions['run']);publish=ast.get_source_segment(producer,functions['publish'])
 need(run.index("publish(HERE/'attempt-claim.json'")<run.index("with EXE.open('rb')as target:")<run.index('NORMAL_TARGET_EXIT=True')
  <run.index('_,post=source_guard')<run.index('post_auth=authorization')<run.index("publish(HERE/'capture.json',result)"),'source codeclaimclosepostguardpublish order')
 need('path.open("x"'in publish and "'attempt-claim.json','capture.json','failure.json'"in run,'exclusive/noretry source')
 owned_caller=parse(raw[seed['caller_owned_source']['path']]);oldcode=bytes.fromhex(owned_caller['raw_hex']);begin=int(owned_caller['window'][0],16)
 lea=next(x for x in seed['caller_rows']if x['rva']=='0x8035c1');leabytes=bytes.fromhex(lea['bytes'])
 need(oldcode[0x8035c1-begin:0x8035c1-begin+7]==leabytes and leabytes.hex()=='488d1528734a01'
  and 0x8035c1+7+struct.unpack('<i',leabytes[3:])[0]==0x1caa8f0,'retainedRIPmachinecue')
 need(actual['exit_code']==0 and actual['sole_executor']=='diplomacy_static'and actual['producer_invocations']==1
  and actual['direct_child_collected']is True and actual['all_shells_collected']is True,'actualDauthor collected0')
 need(commands['producer_invocations']==1 and commands['automatic_retry']is False and commands['all_shells_collected']is True
  and len(commands['commands'])==3 and all(x['exit_code']==0 for x in commands['commands']),'actualsealcheck first3commands')
 need(raw[SUB+'actual.stderr.txt']==b''and len(raw[SUB+'actual.stdout.txt'])==152,'rawproducer stdoutstderr')
 stdout=parse(raw[SUB+'actual.stdout.txt']);need(stdout['status']=='owned6B_DATA_sample_observed'and stdout['DATA_attempts']==1 and stdout['DATA_returned_bytes']==6,'actual stdout agrees')
 need(sum(x['bytes']for x in bill['read_events'])==bill['seal_completed_read_bytes']==1700801,'sealexplicitreadbill')
 need(bill['seal_completed_read_bytes']+bill['manual_preflight_and_inspection_allowance_bytes']+bill['final_receipts_and_local_read_allowance_bytes']
  +bill['planned_first_filecheck_upper_bytes']==bill['retained_successful_upper_bytes']==3832927,'plannedretainedupper')
 actual_upper=bill['seal_completed_read_bytes']+bill['manual_preflight_and_inspection_allowance_bytes']+bill['final_receipts_and_local_read_allowance_bytes']+check['explicit_filecheck_bytes']
 need(actual_upper==check['retained_successful_upper_bytes']==delivery['retained_successful_upper_bytes']==publication['retained_successful_upper_bytes']==3817233<4194304,'actual firstcheckretainedupper')
 need(actual_upper+3481090==check['combined_source_and_retained_upper_bytes']==publication['combined_successful_upper_bytes']==7298323<8388608,'source+retainedseparate combined')
 need(publication['delivery_local_read_bytes']==14068<=bill['final_receipts_and_local_read_allowance_bytes']and publication['delivery_reads_charged_in_131072_final_allowance']is True,'laterdeliverywithinreserve')
 for path,want in publication['source_pins'].items():need(pins[path]==want,'publication threeflatpins')
 for key,name in [('capture','capture.json'),('contract','data-contract.json'),('owned','data-owned.json'),('final_manifest','data-final-manifest.json'),('filecheck','data-filecheck.json')]:need(delivery[key]==p(name),'delivery subjects')
 for key in('class_or_mode_verified','class_layout_verified','host_guard_change_authorized','vtable_compatibility_verified','native_ready','reader_adoption_allowed',
  'selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry','further_scope_authorized','external_file_ABA_excluded','consumption_length_verified'):
  need(cap[key]is False and contract[key]is False,'allfalse authority '+key)
 for key in('code_header_pdata_unwind_vslot_CHD_callee_bytes','searches','engine_decoder_operations','game_process_accesses','Frida_operations','native_game_calls','requests','tests'):
  need(cap[key]==0,'zero target/runtime operation '+key)
 replay={'schema':'EU4-R78-ACTUAL-INDEPENDENT-REPLAY/1','sealed':True,'subject_data_final_manifest':p('data-final-manifest.json'),
  'source_journal_ordered_events':89,'source_journal_exact_pin_match':True,'source_returned_bytes':3481090,
  'sample':{'rva':'0x1caa8f0','end':'0x1caa8f6','file_offset':where,'raw6_hex':sample.hex(),'ASCII':sample.decode('ascii'),
    'UTF8':sample.decode('utf8'),'NUL_within_owned6':None,'targeted_byte7_read':False,'raw_sha256':hashlib.sha256(sample).hexdigest()},
  'cached_header_raw_hex':header.hex(),'LEA':{'site':'0x8035c1','raw_hex':leabytes.hex(),'target_rva':'0x1caa8f0','dereferences_data':False},
  'single_DATA_attempt':account['DATA_reads'][0],'twoSHA_bytes':76925008,'PE_total_bytes':76925014,
  'retained_planned_upper':3832927,'retained_actual_firstcheck_upper':3817233,'combined_actual_upper':7298323,
  'filecheck_layers':{'first49_manifest':p('data-manifest.json'),'final51_manifest':p('data-final-manifest.json')},
  'normalclose_postsource_auth_guard_commit_source_order':True,'class_mode_length_consumer_effect_verified':False}
 rp=save('raw-replay.json',replay)
 for path,want in pins.items():read(path,want,'after')
 memory()
 findings={'schema':'EU4-R78-ACTUAL-INDEPENDENT-REVIEW/1','sealed':True,'passed':True,'blocking_findings':[],
  'scope':'full_retained_file_sample_provenance_journal_and_bounds_not_runtime',
  'subject_data_final_manifest':p('data-final-manifest.json'),'subject_capture_pin':p('capture.json'),
  'subject_contract_pin':p('data-contract.json'),'subject_owned_pin':p('data-owned.json'),'subject_filecheck_pin':p('data-filecheck.json'),
  'subject_delivery_pin':p('data-delivery.json'),'subject_publication_pin':p('data-publication.json'),'raw_replay':rp,
  'roles':'War is not R78 actual/retained author D. War previously reviewed R78 source and R75 raw/actual, and designed original R69 source before reviewing its actual. Those overlaps are disclosed; no R75/R69/R79 semantics are transferred to this sample.',
  'conclusions':[
   'All51 canonical flat pins plus explicit delivery/commands/publication pins match before/after; no old manifest recursively expanded or enginebody/PE opened.',
   'One6B targeted DATA event returns646573657274 atRVA1caa8f0/file30055152; owned bytes decodeASCII/UTF8 desert and contain noNUL. Byte7 is outside the retained sample.',
   'Cached whole-span .rdata mapping and rawsectionheader agree with fixed plan; retained LEA calculates the sample address without dereferencing data. R8D6 still is not proven consumer length.',
   'All89 source read attempts replay in original order with exact file sizes/SHA/currentpins, including three review groups, two32-source guards and finalbase/auth checks; total3481090B<4MiB.',
   'Rootspan/three subject-boundreviews, exclusiveclaim/no-retry, two fixedPE SHA witnesses, normalcontextclose then finalsource/authguards and committedcapture agree.',
   'First49-manifest filecheck is correctly included by final51-manifest. Plannedretainedupper3832927B and actual firstcheck upper3817233B are distinct; final combined7298323B<8MiB, PE76925014B separate.',
   'No class/mode/layout/hostguard/vtable compatibility, actual95110 length/meaning, world/native effect or lease permission follows; all declared authorities remainfalse.'
  ],
  'precision_notes':[
   'source_byte7_read=false describes targeted/retained DATA sampling. Both whole-PE authentication passes necessarily cover its file location too; no claim of globally zero reads outside6B is made.',
   'ASCII desert with noNUL in6B is an owned-byte diagnostic, not a complete Cstring or resource/type/consumer proof.',
   'Retained successful4MiB accounting is a post-read publication assertion, not a producer failure-path or mutating-source pre-read aggregate bound. Producer explicit source4MiB is separate and pre-read.',
   'Planned firstcheck1738910B was replaced by actual1723216B only in later delivery/filecheck, preserving earlier3832927B conservative witness.',
   'TwoPE SHA/memory/timing and collectedcommand facts are retained author witnesses, not new PE/process observations. Timing0.361163s is the complete producer command, not isolated DATA latency.',
   'Normal Python close/postguard equality is finite source consistency, not independent OS close-return, external ABA exclusion, atomicity or world lifetime.',
   'Accepted upstream R76/R74 source/profile pins remain flat witnesses, not a new full machine-code audit of those bodies or a future execution grant.'
  ],
  'source_pins_before_after_equal':True,'admitted_flat_file_count':len(pins),'author_frozen_files_need_change':False,
  'resource_witness':{'source_bytes':3481090,'PE_SHA_plus_DATA_separate':76925014,'retained_planned_upper':3832927,
   'retained_actual_firstcheck_upper':3817233,'combined_actual_upper':7298323,'producer_own_peak':account['peak_own_private_bytes'],
   'producer_command_seconds':actual['wall_time_seconds'],'hard_Job_installed':False},
  'review_resources':{'explicit_file_read_bytes':sum(x['bytes']for x in READS),'manual_allowance':MANUAL,'own_seal_check_reserve':TAIL,
   'conservative_upper':sum(x['bytes']for x in READS)+MANUAL+TAIL,'limit':16*1024*1024,'ordinary_file_limit':4*1024*1024,
   'own_peak_private':PEAK,'software_guard':768*1024*1024,'full_OS_IO_claimed':False},
  'operations':{'PE_stat_open_hash':0,'engine_body':0,'decoder':0,'author_programs':0,'tests':0,'game':0,'Frida':0,'native_calls':0,'requests':0},
  'authority':{key:False for key in('native_ready','callable','reader_adoption_allowed','host_guard_change_authorized','class_or_mode_verified',
   'consumption_length_verified','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry','further_actual_authorized')},
  'self_diagnostics':[],'all_shells_collected':True}
 fp=save('findings.json',findings);jp=save('read-journal.json',READS)
 mpins=dict(pins);mpins['work/review_r78_actual_20261016.py']=pin(Path(__file__).read_bytes())
 for name,want in [('findings.json',fp),('raw-replay.json',rp),('read-journal.json',jp)]:mpins[(OUT/name).relative_to(ROOT).as_posix()]=want
 mp=save('manifest.json',{'schema':'EU4-R78-ACTUAL-INDEPENDENT-REVIEW-MANIFEST/1','sealed':True,'passed':True,'source_pins':mpins,
  'pin_count':len(mpins),'native_ready':False,'further_actual_authorized':False,'recursive_closure_claimed':False})
 print(json.dumps({'passed':True,'findings':fp,'manifest':mp,'raw_replay':rp,'read_bytes':sum(x['bytes']for x in READS),'peak':PEAK}))
def check():
 path=(OUT/'manifest.json').relative_to(ROOT).as_posix();raw=read(path,phase='own_filecheck');m=parse(raw)
 for p,w in m['source_pins'].items():read(p,w,'own_filecheck')
 need(len(m['source_pins'])==m['pin_count'],'ownmanifestcount')
 vp=save('verification.json',{'schema':'EU4-R78-ACTUAL-INDEPENDENT-VERIFICATION/1','passed':True,'manifest_pin':pin(raw),
  'pin_count':m['pin_count'],'file_only':True,'author_executed':False,'PE_engine_accesses':0,'further_actual_authorized':False})
 print(json.dumps({'passed':True,'verification':vp,'pins':m['pin_count']}))
if __name__=='__main__':
 try:
  if sys.argv[1:]==['--check']:check()
  else:need(sys.argv[1:]==[],'noargs/owncheckonly');audit()
 except BaseException:
  if OUT.exists():
   with (OUT/'failure.txt').open('x',encoding='utf8')as f:f.write(traceback.format_exc())
  raise
