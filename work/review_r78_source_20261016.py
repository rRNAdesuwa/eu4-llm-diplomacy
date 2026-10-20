"""R78 non-author file/AST review; never imports or executes author source."""
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
OUT=ROOT/'work/reports/server-expected-owner-sample-data-source-independent-review-20261016-r78'
EXPECTED={
 'source-manifest.json':(7700,'d1bce281e91ebca3ff60ce5a5b25acb1dfd91a4178e34acd5a66e1b9d4c10b33'),
 'produce.py':(18803,'eca07fe527f95f7db33094ff78f315571ca75bb238a7ebb4676e67e3d5aca2b3'),
 'entry-seed.json':(6277,'028f47b32044c1ca47f28c885379a9a69108fd4474157b3cfc7626c11b8ad0fc'),
 'budget.json':(1030,'5b4957d92b869e402725398478e8a8e4e9a8a98c6274b61f0c73802085f81672'),
 'final-manifest.json':(9322,'2d60fe0d62cd2acc9781b2a4e7c14519ad3e25c6a1bd1ecfa20c386a53d28518'),
 'prepared-delivery.json':(2361,'2ed9291b2c2a1758203e546c8ee8793623e50407ce046d4d445c4c727a261cf5'),
 'PROTOCOL.md':(3809,'243513c5405987cba9970a6cd0498924151b7b410b5d8c4c24ac01649ab57ef7'),
 'source-changes.json':(4174,'a6bcd66d66eca41fbc1e1a00c1d1b09aba06f52b8c9fc55b53f386ecb6457283'),
 'preparation.json':(10948,'4b30b87f71f8ba971349ac85ca1e329bde8f0febcdce2c622fab97fe5dacf4ec'),
}
JOURNAL=[];PEAK=0;MANUAL=1024*1024;TAIL=2*1024*1024

def need(ok,msg):
    if not ok:raise AssertionError(msg)
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def parse(raw):
    def pairs(items):
        result={}
        for k,v in items:need(k not in result,'duplicate key');result[k]=v
        return result
    def finite(value):
        n=float(value);need(math.isfinite(n),'nonfinite exponent');return n
    return json.loads(raw.decode('utf8'),object_pairs_hook=pairs,parse_float=finite,
      parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def guard():
    global PEAK
    class PMC(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in (
          'peak_working','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
    p=PMC();p.cb=ctypes.sizeof(p)
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=wintypes.HANDLE
    a=ctypes.WinDLL('psapi',use_last_error=True);a.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
    need(a.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(p),p.cb),'own memory available')
    PEAK=max(PEAK,p.private,p.peak_pagefile);need(0<PEAK<=768*1024*1024 and PEAK<1024*1024*1024,'software own memory guard')
    need(sum(x['bytes'] for x in JOURNAL)+MANUAL+TAIL<=16*1024*1024,'review16MiB source+manual+seal cap')
def read(path,want=None,phase='before'):
    need((path.startswith('work/reports/') or path=='work/review_r78_source_20261016.py') and 'work/deps/' not in path,'admitted ordinary text only')
    need(not path.lower().endswith(('.exe','.dll','.pyd')),'no binary/engine body')
    p=ROOT/path;need(p.stat().st_size<=4*1024*1024,'ordinary4MiB');raw=p.read_bytes()
    JOURNAL.append({'phase':phase,'path':path,'bytes':len(raw)});guard()
    if want is not None:need(pin(raw)==want,'pin differs: '+path)
    return raw
def save(name,obj):
    raw=(json.dumps(obj,indent=2,ensure_ascii=True)+'\n').encode('utf8')
    with (OUT/name).open('xb') as f:f.write(raw)
    return pin(raw)
def functions(text):return {n.name:n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
def dump(n):return ast.dump(n,include_attributes=False)
def constant(n):
    try:return ast.literal_eval(n)
    except (ValueError,TypeError):
        need(isinstance(n,ast.BinOp) and isinstance(n.op,ast.Mult),'only static integer multiplication allowed')
        left=constant(n.left);right=constant(n.right)
        need(type(left) is int and type(right) is int,'static integer operands only')
        return left*right

def audit():
    OUT.mkdir(exist_ok=False)
    top={SUB+n:{'bytes':v[0],'sha256':v[1]} for n,v in EXPECTED.items()}
    raw={SUB+'final-manifest.json':read(SUB+'final-manifest.json',top[SUB+'final-manifest.json'])}
    final=parse(raw[SUB+'final-manifest.json'])
    need(final['sealed'] is True and final['pin_count']==len(final['pins'])==44,'44flat final pins')
    for path,want in final['pins'].items():
        if path in top:need(want==top[path],'hard subject versus final graph')
        raw[path]=read(path,want)
    for path,want in top.items():
        if path not in raw:raw[path]=read(path,want)
    delivery=parse(raw[SUB+'prepared-delivery.json'])
    for name in ('seal.stdout.json','seal.stderr.txt','seal-run.json'):
        raw[SUB+name]=read(SUB+name)
    pins={p:pin(v) for p,v in raw.items()}
    base=parse(raw[SUB+'source-manifest.json']);seed=parse(raw[SUB+'entry-seed.json']);budget=parse(raw[SUB+'budget.json'])
    delta=parse(raw[SUB+'source-changes.json']);prep=parse(raw[SUB+'preparation.json'])
    accounting=parse(raw[SUB+'prepared-read-accounting.json']);check=parse(raw[SUB+'prepared-filecheck.json'])
    need(base['sealed'] is True and base['actual_authorized'] is False and base['flat_source_count']==len(base['source_pins'])==32,'32source graph prepared notactual')
    need(sum(v['bytes'] for v in base['source_pins'].values())==base['flat_source_bytes']==1601982,'runtime flat bytes')
    for path,v in base['source_pins'].items():need(pins[path]==v,'base32 subset')
    text=raw[SUB+'produce.py'].decode('utf8');tree=ast.parse(text);fs=functions(text)
    donor_path=delta['donor']['path'];donor=raw[donor_path].decode('utf8')
    need(pins[donor_path]=={k:delta['donor'][k] for k in ('bytes','sha256')},'R74 donor pin')
    candidate=donor
    for replacement in delta['replacements']:
        need(candidate.count(replacement['before'])==replacement['occurrences'],'exact replacement occurrence')
        candidate=candidate.replace(replacement['before'],replacement['after'])
    need(candidate==text,'whole producer exact stated R74 delta')
    donor_fs=functions(donor)
    helper_names=['require','digest','exact_pin','project_path','strict_json','rel','pair','review_pin','full_sha','publish']
    need(delta['ten_pureDATA_helpers_AST_equal']==helper_names,'ten helper metadata')
    unchanged={name:dump(fs[name])==dump(donor_fs[name]) for name in delta['all_unchanged_function_ASTs']}
    need(all(unchanged.values()) and set(unchanged)==set(helper_names+['memory_guard','source_bytes','fixed_plan']),'13unchanged function ASTs')
    need({name for name in fs if dump(fs[name])!=dump(donor_fs[name])}==set(delta['changed_functions'])
      =={'source_guard','interpret_owned','authorization','data_read','run'},'only5declared changed functions')
    constants={}
    for n in tree.body:
        if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name):
            try:constants[n.targets[0].id]=constant(n.value)
            except (ValueError,TypeError,AssertionError):pass
    need(constants['DATA_RVA']==0x1caa8f0 and constants['DATA_SIZE']==6 and constants['LIMIT_SOURCE']==constants['LIMIT_FILE']==4*1024*1024,'fixed6B and4M bounds')
    need(constants['SOFT_MEMORY']==768*1024*1024 and constants['HARD_MEMORY']==1024*1024*1024,'memory constants')
    guardtext=ast.get_source_segment(text,fs['source_guard']);runtext=ast.get_source_segment(text,fs['run'])
    need(guardtext.index('require(pair(raw)==expected_manifest_pin')<guardtext.index('manifest=strict_json(raw)')
      <guardtext.index('pins=manifest.get')<guardtext.index('source_bytes(path,expected)'),'single raw buffer pin dominates parse/source selection')
    guards=[n for n in ast.walk(fs['run']) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='source_guard']
    need(len(guards)==2 and all(len(n.args)==1 and dump(n.args[0])==dump(ast.parse("subjects['subject_source_manifest']",mode='eval').body) for n in guards),'both same authorizedbasepin')
    need(runtext.index("'Current manifest differs before guard'")<runtext.index("base,pre=source_guard")
      <runtext.index("'Current manifest differs after guard'"),'first surrounding exactbase checks')
    need(runtext.index('pre_auth=authorization')<runtext.index('base,pre=source_guard')<runtext.index("publish(HERE/'attempt-claim.json'")
      <runtext.index("with EXE.open('rb')as target:"),'review/root auth beforegraph andclaim beforePE')
    need(runtext.index('NORMAL_TARGET_EXIT=True')<runtext.index('_,post=source_guard')<runtext.index('post_auth=authorization')
      <runtext.index("publish(HERE/'capture.json',result)"),'normalclose postguard/authbeforecapture')
    need("require(pre==post and pre_auth==post_auth" in runtext and "'Current manifest differs at final guard'" in runtext,'closed graph/authbase comparisons')
    authtext=ast.get_source_segment(text,fs['authorization'])
    need("'subject_final_manifest':UPSTREAM_MANIFEST" in authtext and "'subject_capture_pin':UPSTREAM_CAPTURE" in authtext
      and "'subject_contract_pin':UPSTREAM_CONTRACT" in authtext and 'subject_actual_manifest' not in authtext,'real R76 upstream gate names')
    need("'source_peer_review':subjects" in authtext and "'raw_seed_review':{'subject_source_manifest'" in authtext
      and "type(findings.get('data_rva'))is int" in authtext and "type(findings.get('requested_bytes'))is int" in authtext,'exact three review subjects/spans')
    reviewpath=seed['R76_full_review']['path'];upreview=parse(raw[reviewpath])
    need(upreview['sealed'] is True and upreview['passed'] is True and upreview['blocking_findings']==[],'accepted R76 review')
    for key,value in seed['R76_upstream_subjects_from_real_full_findings'].items():
        need(upreview[key]==value,'R76 seed true subject field')
    need(constants['UPSTREAM_MANIFEST']==upreview['subject_final_manifest'] and constants['UPSTREAM_CAPTURE']==upreview['subject_capture_pin']
      and constants['UPSTREAM_CONTRACT']==upreview['subject_contract_pin'],'producer exact upstream3pins')
    def match_record(record):need(pins[record['path']]=={k:record[k] for k in ('bytes','sha256')},'seed flat source pin')
    for record in (seed['R76_full_review'],seed['caller_owned_source'],seed['caller_selected_source']):match_record(record)
    owned=parse(raw[seed['caller_owned_source']['path']]);code=bytes.fromhex(owned['raw_hex']);begin=int(owned['window'][0],16)
    for row in seed['caller_rows']:
        at=int(row['rva'],16);b=bytes.fromhex(row['bytes'])
        need(code[at-begin:at-begin+len(b)]==b,'seed row belongs to retainedR76 ownedbytes')
    lea=next(r for r in seed['caller_rows'] if r['rva']=='0x8035c1');lea_raw=bytes.fromhex(lea['bytes'])
    need(lea_raw.hex()=='488d1528734a01' and 0x8035c1+7+struct.unpack('<i',lea_raw[3:])[0]==0x1caa8f0,'LEA RIP arithmetic notdereference')
    need(seed['R8D6_is_not_proved_length'] is True and seed['requested_bytes']==6 and seed['root_selected_sample_budget']==6,'sample notconsumptionlength')
    cache=parse(raw[constants['CACHE']]);need(pins[constants['CACHE']]==constants['CACHE_PIN'],'cache hardpin')
    matches=[s for s in cache['sections'] if int(s['rva'],16)<=0x1caa8f0 and 0x1caa8f6<=int(s['rva'],16)+s['raw_size']]
    need(len(matches)==1 and matches[0]['name']=='.rdata','cached whole6B unique nontext')
    section=matches[0];start=int(section['rva'],16);size=section['raw_size'];offset=section['raw_file_offset'];virtual=section['virtual_size']
    header=bytes.fromhex(section['section_header_raw_hex'])
    need(struct.unpack_from('<IIII',header,8)==(virtual,start,size,offset) and len(header)==40,'cached rawheader fields')
    where=offset+0x1caa8f0-start
    need(where==30055152 and 0x1caa8f6<=start+virtual and 0<=where<=38462504-6,'cached virtual/raw/file bounds')
    plan=seed['prepared_cached_mapping_plan'];need(plan['rva']==0x1caa8f0 and plan['end_exclusive']==0x1caa8f6
      and plan['size']==6 and plan['file_offset']==where and plan['section']=='.rdata','fixed prepared plan')
    need(prep['planned_mapping']==delivery['mapping']==plan,'prepared plan three outputs')
    mappingtext=ast.get_source_segment(text,fs['fixed_plan']);datatext=ast.get_source_segment(text,fs['data_read'])
    need("'DATA_reads_allowed':0" in mappingtext and "if len(matches)!=1:return unknown" in mappingtext
      and "item.get('name')=='.text'" in mappingtext,'invalid map unknown0DATA nofallback')
    need("require(not LEDGER['DATA_reads']and LEDGER['DATA_returned_bytes']==0" in datatext
      and 'raw=target.read(DATA_SIZE)' in datatext and "require(len(raw)==DATA_SIZE,'Short DATA read, no retry')" in datatext,'one fixed6B read/shortreadrefuse')
    interprettext=ast.get_source_segment(text,fs['interpret_owned'])
    need("len(raw)==DATA_SIZE" in interprettext and "source_byte7_or_later_read':False" in interprettext
      and "consumption_length_verified':False" in interprettext,'ownedonlydiagnostics')
    sourcetext=ast.get_source_segment(text,fs['source_bytes']);shatext=ast.get_source_segment(text,fs['full_sha'])
    need("LEDGER['source_returned_bytes']+n<=LIMIT_SOURCE" in sourcetext and sourcetext.index('<=LIMIT_SOURCE')<sourcetext.index("with p.open('rb')"),'4M sourcehardguard beforebodyread')
    need("event['returned_bytes']+=len(raw)" in sourcetext and "LEDGER['source_returned_bytes']+=len(raw)" in sourcetext,'source partialreturnedledger')
    need('remaining = EXPECTED_BYTES' in shatext and 'min(1024 * 1024, remaining)' in shatext
      and 'os.fstat(f.fileno()).st_size == EXPECTED_BYTES' in shatext,'fixed fullSHA bounds')
    need("before=full_sha(target,'before')" in runtext and "after=full_sha(target,'after')" in runtext,'twoSHApasses')
    need('path.open("x"' in ast.get_source_segment(text,fs['publish']) and "'attempt-claim.json','capture.json','failure.json'" in runtext,'exclusiveclaim+noretry')
    imports=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
    need(not any('capstone' in ast.unparse(n).lower() or 'frida' in ast.unparse(n).lower() for n in imports),'stdlib noengineimports')
    need(budget['producer_explicit_source_IO']==budget['retained_IO']==4*1024*1024 and budget['source_plus_retained']==8*1024*1024
      and budget['new_DATA_bytes']==6 and budget['two_full_PE_SHA_separate']==76925008 and budget['full_success_PE_total']==76925014,'4M+4M andPE separate')
    need(base['future_conditional_source_estimate']==3872274<4*1024*1024 and base['estimate_is_not_all_OS_IO'] is True,'estimate isconditional nothardbound')
    need(sum(v['bytes'] for v in prep['events'])==prep['instrumented_source_bytes']==3164804
      and prep['instrumented_source_bytes']+prep['manual_preinspection_allowance']==prep['preparation_upper']==3426948,'preparation accounting')
    need(accounting['first_filecheck_bytes']+accounting['seal_file_bytes']==accounting['retained_total_instrumented']==3249469
      and accounting['retained_total_instrumented']+accounting['final_log_delivery_and_inspection_allowance']==accounting['retained_upper']==3773757<4*1024*1024,'retained accounting')
    for phase in ('prepare','check','seal'):
        result=parse(raw[SUB+phase+'-run.json'])
        need(result.get('exit_code')==0,'firstauthor command collected0')
        need(raw[SUB+phase+'.stderr.txt']==b'','empty authorstderr')
    need(delivery['all_prior_shells_collected'] is True and delivery['source_mutation_after_first_check'] is False
      and delivery['producer_executed'] is False and delivery['auth_claim_capture_created'] is False,'source-only collectedfirstwitness')
    need(all(v is False for v in seed['authority'].values()),'seed allauthorityfalse')
    producer_false_keys=['native_ready','reader_adoption_allowed','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry',
      'host_guard_change_authorized','class_or_mode_verified','consumption_length_verified','external_file_ABA_excluded']
    for key in producer_false_keys:need("'"+key+"':False" in runtext,'producer falseclaim '+key)
    replay={
      'schema':'EU4-R78-INDEPENDENT-SOURCE-REPLAY/1','sealed':True,'R74_whole_text_replacements_exact':True,
      'ten_helper_AST_equal':{n:unchanged[n] for n in helper_names},'all13unchanged_function_AST':unchanged,
      'five_changed_functions':sorted(delta['changed_functions']),'source_guard_rawbuffer_pin_precedes_parse':True,
      'source_guard_calls_same_authorizedpin':2,'initial_outer_basechecks':True,'source_graph_limit':32,
      'exact_R76_gate_subjects':seed['R76_upstream_subjects_from_real_full_findings'],'future_sample':{'rva':'0x1caa8f0','end':'0x1caa8f6','bytes':6,
        'file_offset':where,'section':'.rdata','cached_header':header.hex(),'newDATA_by_review':0},
      'LEA':{'site':'0x8035c1','raw_hex':lea_raw.hex(),'target_rva':'0x1caa8f0','memory_data_read_by_LEA':False},
      'one_read_and_zero_on_invalid_mapping_source_checked':True,'normalclose_before_postguards_capture':True,
      'future_actual_source_cap':4194304,'retained_cap_separate':4194304,'conditional_future_estimate':3872274,
      'twoSHA_bytes_separate':76925008,'fixedsample_bytes':6,'fullsuccess_PE_bytes':76925014,
      'source_preparation_upper':3426948,'author_retained_upper':3773757,
      'helper_or_author_program_executions_by_review':0,'runtime_type_or_consumption_length_verified':False}
    replay_pin=save('source-replay.json',replay)
    for path,want in pins.items():read(path,want,'after')
    guard()
    findings={
      'schema':'EU4-R78-SOURCE-INDEPENDENT-REVIEW/1','sealed':True,'passed':True,'blocking_findings':[],
      'scope':'full_bounded_flat_source_budget_protocol_AST_review_not_actual',
      'subject_source_manifest':pins[SUB+'source-manifest.json'],'subject_producer':pins[SUB+'produce.py'],
      'subject_entry_seed':pins[SUB+'entry-seed.json'],'subject_budget':pins[SUB+'budget.json'],
      'subject_final_manifest':pins[SUB+'final-manifest.json'],'subject_prepared_delivery':pins[SUB+'prepared-delivery.json'],
      'data_rva':0x1caa8f0,'requested_bytes':6,'source_replay':replay_pin,
      'reviewer_roles':'Non-author of R78. War previously authored R75 raw-entry review, independently reviewed Val R75 actual, and designed original R69 source before later reviewing its actual. Those roles confer no R78 actual authority. R77 composition was assigned to D; it is not imported or claimed reviewed here.',
      'conclusions':[
        'All44 final flat pins and explicit seal/delivery extensions match before/after.32 runtime source pins total1601982B. No enginebody or recursive history graph is read.',
        'R78 producer is exactly the declared R74 string delta. First10 helpers and13 unchanged function ASTs match; only the5declared identity/subject/diagnostic functions differ.',
        'Authorized raw manifest length/SHA is verified before JSON parse/path selection. Both guards use one authorizedbasepin, with first outerchecks and final base/source/auth/review equality.',
        'R76 upstream review uses actual subject_final_manifest/capture/contract fields with exact pins. New raw/sourcepeer and rootoncegrant remain required beforePE access.',
        'Only one6B DATA read from cached unique whole non.text raw/virtual/file mapping is allowed; malformed mapping recordsunknown0DATA and has no alternate target. LEA is address computation, R8D6 is not proved consumption length.',
        'Single exclusive attempt claim precedes targetopen; two fixed38462504B SHA passes surround the optional6B read. Normalcontext exit precedes final source/auth/review guards and committedcapture.',
        'Producer explicitsource4MiB is checked before eachread. The completed retainedstage post-bill upper is3773757B<4MiB; its sealer aggregate check occurs after reading.3872274B future estimate is conditional.',
        'All class/mode/hostguard/reader/effect/native/lease/atomic/retry permissions remainfalse; samplediagnostics examine onlyowned6B.'
      ],
      'precision_notes':[
        'No originalR76 fullraw audit is rerun. Selected raw rows/map and acceptedsubject fields are sufficient for this newsource audit, not an independent revalidation of every older semantic claim.',
        'Normal Python context exit is source evidence, not an independent OS CloseHandle-return proof. Pre/post file equality does not exclude external ABA or establish atomicity.',
        'The preparation and retained bills are author witnesses replayed from retained events; they are not full OS/loader IO or universal failed-I/O/tree cleanup proofs.',
        'Retained4MiB sealer aggregate is a post-read publication assertion, not a pre-read cumulative stop for failed/file-changing paths; read() only checks perfile4MiB before reading. The successful bill remains below4MiB. No universal output/loader/allocation bound follows.',
        'Conditional estimate assumptions about future authorization/review sizes may fail. Source reader then refuses at4MiB; the audit does not raise that limit or permit retry.',
        'No R74 label is transferred to this address. Encoding/NUL diagnostics, if future granted, cannot prove actual95110 consumption, object identity, GUI resource or hostguard compatibility.'
      ],
      'source_pins_before_after_equal':True,'admitted_flat_files':len(pins),'author_frozen_files_need_change':False,
      'resources':{'explicit_text_read_bytes':sum(x['bytes'] for x in JOURNAL),'manual_inspection_allowance':MANUAL,'seal_and_filecheck_reserve':TAIL,
        'conservative_review_upper':sum(x['bytes'] for x in JOURNAL)+MANUAL+TAIL,'limit':16*1024*1024,
        'ordinary_file_limit':4*1024*1024,'own_peak_private_bytes':PEAK,'software_guard':768*1024*1024,'full_OS_IO_claimed':False},
      'operations':{'PE_stat_open_hash':0,'engine_body':0,'decoder':0,'author_prepare_check_producer':0,'tests':0,'game':0,'Frida':0,'native':0,'requests':0,'actual_auth':0},
      'authority':{'actual_authorized':False,'native_ready':False,'callable':False,'reader_adoption_allowed':False,'class_or_mode_verified':False,
        'host_guard_change_authorized':False,'consumption_length_verified':False,'selected_effect_verified':False,'world_lease':False,'atomic_snapshot':False,'authorizes_retry':False},
      'self_diagnostics':[],'all_shells_collected':True,'further_scope_auto_authorized':False}
    fp=save('findings.json',findings);jp=save('read-journal.json',JOURNAL)
    mpins=dict(pins);mpins['work/review_r78_source_20261016.py']=pin(Path(__file__).read_bytes())
    for name,want in [('findings.json',fp),('source-replay.json',replay_pin),('read-journal.json',jp)]:mpins[(OUT/name).relative_to(ROOT).as_posix()]=want
    mp=save('manifest.json',{'schema':'EU4-R78-SOURCE-INDEPENDENT-REVIEW-MANIFEST/1','sealed':True,'passed':True,'source_pins':mpins,
      'pin_count':len(mpins),'no_recursive_closure':True,'PE_engine_decoder_author_execution':False,'actual_authorized':False,'native_ready':False})
    print(json.dumps({'passed':True,'findings':fp,'manifest':mp,'source_replay':replay_pin,'read_bytes':sum(x['bytes'] for x in JOURNAL),'peak':PEAK}))

def check():
    path=(OUT/'manifest.json').relative_to(ROOT).as_posix();raw=read(path,phase='independent_filecheck');m=parse(raw)
    for p,w in m['source_pins'].items():read(p,w,'independent_filecheck')
    need(len(m['source_pins'])==m['pin_count'],'own review pin count')
    vp=save('verification.json',{'schema':'EU4-R78-INDEPENDENT-VERIFICATION/1','passed':True,'manifest_pin':pin(raw),
      'pin_count':m['pin_count'],'file_only':True,'author_executed':False,'actual_authorized':False})
    print(json.dumps({'passed':True,'verification':vp,'pins':m['pin_count']}))

if __name__=='__main__':
    try:
        if sys.argv[1:]==['--check']:check()
        else:need(sys.argv[1:]==[],'noargs or own--check');audit()
    except BaseException:
        if OUT.exists():
            with (OUT/'failure.txt').open('x',encoding='utf8') as f:f.write(traceback.format_exc())
        raise
