"""Independent R75 retained-only actual review; no target/engine/program execution."""
import ast
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import struct
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
SUB='work/reports/war-peace-api-20261016-r75-null-successor-fragment/'
UP='work/reports/war-peace-api-20261016-r69-generator-divisor-source/'
OUT=ROOT/'work/reports/war-peace-api-20261016-r75-actual-independent-review-r2'
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
TOP={
 'actual-manifest.json':(16739,'f05a565e8fdb8c2006cd9b2f94e77fef5a86c1c7fbf8d5bcd7e8c91f22c2eab9'),
 'actual-contract.json':(6999,'b841344c4c286f1cd7d5bfe7c5edea930913a9e9191c5731bb03a6f1b62c19ea'),
 'capture.json':(69417,'c0667fdefc13e922d45321b2d63f87e567bb1db3e3d8ab37d447d8f35a3f59b0'),
 'owned-code.json':(584,'150e721451fdf8d071cb038d2530163f7c72be094ebb1598cf2c42249c9e9d3c'),
 'actual-selected-evidence.json':(10173,'5ae4eb40dc81a08ff3c328d8d436bfdee72e26b0211d2cbab0fe7fbf317e9efb'),
 'actual-filecheck.json':(6841,'65aec90be7d9373dc8566d222cd94d4c1366a8bfdd03bb7cb127b2962f53f889'),
 'actual-delivery.json':(3161,'d88cab422b0fe1a50f70107d4fd3e73b54a3ba8b8e46d0bb6596810479270899'),
}
JOURNAL=[]
PEAK=0
MANUAL=1024*1024

def need(ok,message):
    if not ok: raise AssertionError(message)

def pin(raw): return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def pairs(items):
    answer={}
    for k,v in items:
        need(k not in answer,'duplicate JSON key')
        answer[k]=v
    return answer

def parse(raw):
    return json.loads(raw.decode('utf8'),object_pairs_hook=pairs,
      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))

class PMC(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
      ('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),
      ('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),
      ('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),
      ('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]

def guard():
    global PEAK
    p=PMC();p.cb=ctypes.sizeof(p)
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=wintypes.HANDLE
    a=ctypes.WinDLL('psapi',use_last_error=True)
    a.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
    need(a.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(p),p.cb),'self memory guard')
    PEAK=max(PEAK,p.PeakPagefileUsage)
    need(p.PagefileUsage<=768*1024*1024 and PEAK<=1024*1024*1024,'memory guard limit')
    need(sum(x['bytes'] for x in JOURNAL)+MANUAL+1024*1024<=24*1024*1024,'review stage read limit including prior failure allowance')

def read(path,expected=None,phase='before'):
    need(path.startswith('work/reports/') or path in ('work/review_r75_actual_20261016.py','work/review_r75_actual_20261016_r2.py'),'flat text scope')
    need('work/deps/' not in path and not path.lower().endswith(('.exe','.dll')),'no engine/binary access')
    p=ROOT/path;need(p.stat().st_size<=4*1024*1024,'ordinary file size')
    raw=p.read_bytes();JOURNAL.append({'phase':phase,'path':path,'bytes':len(raw)})
    guard()
    if expected is not None: need(pin(raw)==expected,'source pin: '+path)
    return raw

def write(name,obj):
    raw=(json.dumps(obj,indent=2,ensure_ascii=True)+'\n').encode('utf8')
    with (OUT/name).open('xb') as f:f.write(raw)
    return pin(raw)

def relative(path):
    p=Path(path)
    return p.relative_to(ROOT).as_posix() if p.is_absolute() else p.as_posix()

def audit():
    OUT.mkdir(exist_ok=False)
    expected={SUB+n:{'bytes':v[0],'sha256':v[1]} for n,v in TOP.items()}
    raw={SUB+'actual-manifest.json':read(SUB+'actual-manifest.json',expected[SUB+'actual-manifest.json'])}
    manifest=parse(raw[SUB+'actual-manifest.json'])
    need(manifest['sealed'] is True and manifest['flat_actual_file_count']==len(manifest['source_pins'])==47,'actual manifest47')
    need(len(manifest['decoder_expected_witness_pins'])==38 and manifest['decoder_files_opened_in_retained_stage'] is False,'engine metadata only')
    for path,want in manifest['source_pins'].items():
        if path in expected: need(want==expected[path],'top subject graph')
        raw[path]=read(path,want)
    for path,want in expected.items():
        if path not in raw:raw[path]=read(path,want)
    delivery=parse(raw[SUB+'actual-delivery.json'])
    for stem,key in [('actual-seal','first_retained_seal'),('actual-filecheck','first_filecheck')]:
        group=delivery[key]
        need(group['exit_code']==0,'author retained command collected0')
        for suffix,pinkey in [('.stdout.json','stdout'),('.stderr.txt','stderr')]:
            path=SUB+stem+suffix
            raw[path]=read(path,group[pinkey])
    pins={p:pin(v) for p,v in raw.items()}
    cap=parse(raw[SUB+'capture.json']);owned=parse(raw[SUB+'owned-code.json'])
    contract=parse(raw[SUB+'actual-contract.json']);selected=parse(raw[SUB+'actual-selected-evidence.json'])
    base=parse(raw[SUB+'source-manifest.json']);seed=parse(raw[SUB+'entry-seed.json'])
    auth=parse(raw[SUB+'run-authorization.json']);claim=parse(raw[SUB+'claim.json'])
    acquisition=parse(raw[SUB+'actual-acquisition-receipt.json'])
    accounting=parse(raw[SUB+'actual-retained-read-accounting.json'])
    filecheck=parse(raw[SUB+'actual-filecheck.json'])
    preflight=parse(raw[SUB+'actual-invocation-preflight.json'])
    def subj(name):return pins[SUB+name]
    need(manifest['capture_pin']==subj('capture.json') and manifest['contract_pin']==subj('actual-contract.json')
      and manifest['owned_code_pin']==subj('owned-code.json'),'manifest subjects')
    need(contract['capture_pin']==subj('capture.json') and contract['owned_code_pin']==subj('owned-code.json'),'contract subjects')
    need(selected['source_capture']==subj('capture.json') and selected['source_owned']==subj('owned-code.json'),'selected subjects')
    need(cap['source_manifest']==subj('source-manifest.json') and owned['source_manifest']==subj('source-manifest.json')
      and cap['entry_seed_pin']==subj('entry-seed.json') and cap['owned_code_pin']==subj('owned-code.json'),'capture/owned source identities')
    need(cap['game_sha256']==owned['game_sha256']==contract['game_sha256']==GAME and cap['game_bytes']==38462504,'fixed EXE identity witnesses')
    need(cap['source_pins']==base['source_pins']==claim['source_pins'],'source/claim/capture same expected graph')
    need(cap['decoder_expected_witness_pins']==base['decoder_expected_witness_pins']==manifest['decoder_expected_witness_pins'],'38same metadata entries')
    actual_sources={p:v for p,v in base['source_pins'].items() if not p.startswith('work/deps/')}
    need(len(actual_sources)==21 and len(base['source_pins'])==59,'21text38engine')
    for p,v in actual_sources.items():need(pins[p]==v,'actual source pin current flatsubset')
    need(auth['schema']=='EU4-R75-ROOT-AUTHORIZATION/1' and auth['sealed'] is True and auth['root_explicit_start_received'] is True
      and auth['single_attempt'] is True and auth['sole_executor']=='validation_audit','new exact once authorization')
    need(auth['entry_rva']=='0x993658' and auth['branch_site_rva']=='0x993595' and auth['raw_branch_hex']=='0f84bd000000'
      and auth['pdata_record_index']==19163 and auth['pdata_record_bytes']==12 and auth['pdata_record_rva']=='0x249d244'
      and auth['max_code_bytes']==24,'exact authorization scope')
    for key,name in [('source_manifest','source-manifest.json'),('producer_pin','produce.py'),('entry_seed_pin','entry-seed.json')]:
        need(auth[key]==subj(name),'root authorization subject '+key)
    need(cap['authorization_pin']==claim['authorization_pin']==subj('run-authorization.json'),'authorization captured')
    need(claim['entry_rva']=='0x993658' and claim['pdata_record_index']==19163 and claim['automatic_retry'] is False,'one claim identity')
    review_pins={}
    for label in ('root_raw_entry_review','upstream_actual_review','source_peer_review'):
        group=auth[label]
        need(set(group)=={'findings','manifest'},'three review pair shape')
        for kind,item in group.items():
            path=item['path'];need(pins[path]=={'bytes':item['bytes'],'sha256':item['sha256']},'review direct pin')
            review_pins[str(ROOT/path)]=pins[path]
        findings=parse(raw[group['findings']['path']])
        need(findings['sealed'] is True and findings['passed'] is True and findings['blocking_findings']==[],'review pass')
        if label=='upstream_actual_review':
            need(findings['subject_manifest']==pins[UP+'manifest.json'] and findings['subject_capture']==pins[UP+'capture.json'],'upstream actual subjects')
        else:
            need(findings['subject_source_manifest']==subj('source-manifest.json') and findings['subject_producer']==subj('produce.py')
              and findings['subject_entry_seed']==subj('entry-seed.json'),'r75 raw/source subjects')
    need({relative(p):v for p,v in cap['three_review_pins'].items()}=={relative(p):v for p,v in review_pins.items()}
      =={relative(p):v for p,v in claim['review_pins'].items()},'all review before/after identities')
    root_receipt=parse(raw['work/reports/war-peace-api-20261016-r75-root-authorization/receipt.json'])
    need(root_receipt['passed'] is True and root_receipt['sealed'] is True and root_receipt['before']==root_receipt['after'],'root authorization prepost')
    for path,v in root_receipt['before'].items():need(pins[path]==v,'root prepost flat subject')
    need(root_receipt['authorization']==subj('run-authorization.json'),'root authorization receipt')
    need(acquisition['attempt']==1 and acquisition['exit_code']==0 and acquisition['first_and_only_actual'] is True
      and acquisition['automatic_retry'] is False and acquisition['all_returned_shells_children_collected'] is True
      and acquisition['running_sessions']==[],'single actual receipt0/collected')
    need(acquisition['capture_pin']==subj('capture.json') and acquisition['owned_code_pin']==subj('owned-code.json')
      and acquisition['stdout_pin']==subj('actual-producer.stdout.json') and acquisition['stderr_pin']==subj('actual-producer.stderr.txt'),'actual receipt outputs')
    need(raw[SUB+'actual-producer.stderr.txt']==b'' and acquisition['hard_Job_installed'] is False,'actual empty stderr/no hard Job')
    for entry in preflight['reads']:
        need({'bytes':entry['bytes'],'sha256':entry['sha256']}==subj(entry['name']),'preflight pin')
    preflight_listed=sum(e['bytes'] for e in preflight['reads'])
    need(preflight_listed==62571 and preflight['explicit_bytes']==65560,'preflight listed/conservative billed witnesses')
    preflight_delta=preflight['explicit_bytes']-preflight_listed
    need(selected['analysis']==cap['analysis'] and selected['raw_code']==owned and selected['metadata']==cap['selected'],'selected exact raw/analysis')
    metadata=cap['selected'];record=bytes.fromhex(metadata['raw_hex'])
    need(record.hex()=='583699006836990038dde701' and len(record)==12,'fixed one metadata raw')
    begin,end,unwind=struct.unpack('<III',record)
    need((begin,end,unwind)==(0x993658,0x993668,0x1e7dd38),'metadata little endian DWORDs')
    need(metadata['index']==19163 and metadata['rva']=='0x249d244' and metadata['file_offset']==37139012
      and metadata['begin_rva']==hex(begin) and metadata['end_exclusive']==hex(end)
      and metadata['unwind_rva_unfollowed']==hex(unwind),'metadata fields')
    need(cap['pdata_requests']==[metadata] and cap['metadata_record_attempts']==1
      and cap['pdata_physical_bytes']==cap['pdata_unique_bytes']==12,'unique metadata count')
    upcap=parse(raw[UP+'capture.json'])
    need(cap['previous_retained_only']==upcap['pdata_requests'][14] and cap['next_retained_only']==upcap['pdata_requests'][13],'old neighbors not newly read')
    need(int(cap['previous_retained_only']['end_exclusive'],16)<=begin<end<=int(cap['next_retained_only']['begin_rva'],16)
      and end-begin<=24 and cap['exact_begin_and_retained_neighbor_bounds'] is True,'actual selected disjoint span')
    anchors=parse(raw['work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'])
    def mapping(address,size,name):
        matches=[s for s in anchors['sections'] if int(s['rva'],16)<=address and address+size<=int(s['rva'],16)+s['raw_size']]
        need(len(matches)==1 and matches[0]['name']==name,'unique cached section')
        s=matches[0];answer=s['raw_file_offset']+address-int(s['rva'],16)
        need(0<=answer<=38462504-size,'cached file bounds')
        return answer
    pdata=next(s for s in anchors['sections'] if s['name']=='.pdata')
    need(int(pdata['rva'],16)+19163*12==0x249d244 and mapping(0x249d244,12,'.pdata')==37139012,'fixed metadata mapping')
    need(mapping(begin,end-begin,'.text')==owned['file_offset']==10037848,'code mapping')
    code=bytes.fromhex(owned['raw_hex'])
    need(code.hex()=='498bc64883c430415e415d415c5e5dc3' and len(code)==owned['bytes']==end-begin==16
      and hashlib.sha256(code).hexdigest()==owned['sha256'] and owned['window']==[hex(begin),hex(end)],'owned exact16')
    expected_rows=[('0x993658','498bc6','mov','rax, r14'),('0x99365b','4883c430','add','rsp, 0x30'),
      ('0x99365f','415e','pop','r14'),('0x993661','415d','pop','r13'),('0x993663','415c','pop','r12'),
      ('0x993665','5e','pop','rsi'),('0x993666','5d','pop','rbp'),('0x993667','c3','ret','')]
    analysis=cap['analysis'];rows=analysis['instructions'];need(len(rows)==8,'8retainedrows')
    cursor=begin
    for row,want in zip(rows,expected_rows):
        need(tuple(row[k] for k in ('rva','bytes','mnemonic','operands'))==want,'raw opcode and GP mapping')
        data=bytes.fromhex(row['bytes']);need(int(row['rva'],16)==cursor and code[cursor-begin:cursor-begin+len(data)]==data,'owned contiguous row slice')
        need(row['memory_operands']==[],'no explicit memory operands')
        cursor+=len(data)
    need(cursor==end and analysis['decoded_unique_bytes']==16 and analysis['instruction_count']==8
      and analysis['undecoded_owned_intervals']==[] and analysis['edges']==[]
      and analysis['terminals']==[{'kind':'normal_ret','rva':'0x993667'}]
      and analysis['local_normal_CFG_closed'] is True,'all16B selected local return')
    need(all('rax' not in row['registers_written'] for row in rows[1:]),'RAX not rewritten after currentR14 copy')
    need(rows[1]['registers_written']==['rflags','rsp'],'ADD replaces arithmetic flags')
    look=analysis['lookahead_inputs'];union=set()
    for row,event in zip(rows,look):
        address=int(event['rva'],16);need(event['rva']==row['rva'] and event['bytes']==min(15,end-address),'retained bounded lookahead')
        union.update(range(address,address+event['bytes']))
    need(sum(v['bytes'] for v in look)==analysis['decoder_input_total_bytes']==55 and len(union)==analysis['decoder_input_unique_bytes']==16
      and analysis['decoder_overlap_bytes']==39,'decoder attempt/unique/overlap accounting')
    need(cap['inherited_state']==seed['inherited_state']==contract['inherited_state'],'inherited state no ABI reset')
    upowned=parse(raw[UP+'owned-code.json']);upraw=bytes.fromhex(upowned['raw_hex'])
    uprs=seed['retained_prefix_rows'];need(uprs==upcap['analysis']['instructions'][:15],'prefix exact old15rows')
    for row in uprs:
        address=int(row['rva'],16);data=bytes.fromhex(row['bytes'])
        need(upraw[address-0x993570:address-0x993570+len(data)]==data,'upstream raw prefix')
    branch=bytes.fromhex(seed['source_branch']['bytes']);need(branch.hex()=='0f84bd000000' and 0x993595+6+struct.unpack('<i',branch[2:])[0]==begin,'NULL edge signedrel32')
    need(uprs[-2]['bytes']=='4885c0' and uprs[-3]['bytes']=='4c8be0','TEST64 sourceRAX copied toR12')
    stack=[]
    registers=['R14','R13','R12','RSI','RBP']
    rsp_delta=0x30
    for row,reg in zip(rows[2:7],registers):
        stack.append({'site':row['rva'],'operation':'POP '+reg,'address_from_F':hex(rsp_delta),
                      'address_from_S69':hex(rsp_delta-0x58),'read_bytes':8})
        rsp_delta+=8
    stack.append({'site':rows[-1]['rva'],'operation':'RET','address_from_F':hex(rsp_delta),
                  'address_from_S69':hex(rsp_delta-0x58),'read_bytes':8});rsp_delta+=8
    need(rsp_delta==0x60 and sum(x['read_bytes'] for x in stack)==48,'5POPsRET/frame return arithmetic')
    need(contract['stack_contract']['implicit_stack_reads_bytes']==48 and contract['local_selected_CFG']['closed'] is True
      and contract['local_selected_CFG']['whole_993570_CFG_closed'] is False,'local versus whole function')
    need(contract['raw16_hex']==owned['raw_hex'] and contract['selected_metadata']==metadata
      and selected['return_and_stack_projection']['return']==contract['return_register_contract']
      and selected['return_and_stack_projection']['stack']==contract['stack_contract'],'contract projection binding')
    for a in (contract['authority'],):need(all(value is False for value in a.values()),'all authority false')
    for key in ('native_ready','callable','reader_adoption_allowed','selected_effect_verified','amount_units_verified',
                'recipient_direction_verified','world_lease','atomic_snapshot','authorizes_retry','further_actual_authorized','whole_993570_CFG_closed'):
        need(cap[key] is False,'capture authority false '+key)
    for key in ('game_process_accesses','Frida_operations','native_game_calls','requests','tests','new_header_data_literal_vtable_unwind_callee_bytes'):
        need(cap[key]==0,'capture zero operations '+key)
    need(cap['normal_target_context_exit'] is True and cap['commit_after_target_close_and_final_guards'] is True
      and cap['source_engine_before_after_equal'] is True,'normal close committed capture witness')
    hashes=cap['full_PE_authentication_reads'];need(len(hashes)==2,'two author SHA passes')
    need([v['phase'] for v in hashes]==['before','after'] and all(v['completed'] is True and v['bytes_read']==38462504 and v['sha256']==GAME for v in hashes),'twoSHA exact witness')
    reads=cap['sparse_reads'];need(reads==[
      {'kind':'fixed_pdata_record','rva':'0x249d244','file_offset':37139012,'requested_bytes':12,'bytes':12,'complete':True},
      {'kind':'null_successor_code','rva':'0x993658','file_offset':10037848,'requested_bytes':16,'bytes':16,'complete':True}],'only12+16target reads')
    need(sum(v['bytes_read'] for v in hashes)+sum(v['bytes'] for v in reads)==cap['total_PE_physical_bytes']==76925036,'PE source-auth vs new target accounting')
    source_io=cap['source_file_reads'];need(sum(v['bytes'] for v in source_io)==cap['source_file_read_bytes']==17052059,'source completed journal sum')
    phases={phase:sum(v['bytes'] for v in source_io if v['phase']==phase) for phase in dict.fromkeys(v['phase'] for v in source_io)}
    need(phases=={'authorization_preflight':105008,'source_engine_before':8496380,'source_engine_after':8450671},'completed source phases')
    for path,p in base['source_pins'].items():
        for phase in ('source_engine_before','source_engine_after'):
            events=[v for v in source_io if v['phase']==phase and relative(v['path'])==path]
            need(any(v['bytes']==p['bytes'] for v in events),'before/after completed expected source or decoder witness event')
    for path,p in review_pins.items():
        need(any(relative(v['path'])==relative(path) and v['bytes']==p['bytes'] for v in source_io if v['phase']=='authorization_preflight')
          and any(relative(v['path'])==relative(path) and v['bytes']==p['bytes'] for v in source_io if v['phase']=='source_engine_after'),'review beforeafter journal')
    need(sum(v['bytes'] for v in accounting['completed_read_events'])==accounting['completed_read_bytes']==1214152,'retained completed read sum')
    need(accounting['completed_read_bytes']+accounting['manual_prior_retained_inspection_allowance_bytes']
      +accounting['later_filecheck_delivery_allowance_bytes']==accounting['retained_stage_upper_bytes']==3573448,'retained upper')
    need(accounting['producer_source_engine_bytes']==cap['source_file_read_bytes'] and accounting['combined_source_retained_upper_bytes']==20625507
      ==3573448+17052059,'combined separate stages')
    need(filecheck['sealed'] is True and filecheck['passed'] is True and filecheck['subject_manifest']==subj('actual-manifest.json')
      and filecheck['flat_actual_pin_count']==47 and filecheck['decoder38_metadata_only'] is True,'author retained filecheck witness')
    need(sum(v['bytes'] for v in filecheck['read_events'])==filecheck['explicit_file_read_bytes']==586125,'filecheck explicit returned bytes')
    need(delivery['attempts']==1 and delivery['all_shells_children_collected'] is True and delivery['running_sessions']==[]
      and delivery['no_failures_or_retries'] is True and delivery['retained_stage_upper_bytes']==3573448
      and delivery['combined_source_retained_upper_bytes']==20625507,'delivery collection/resource boundary')
    for key,name in [('actual_manifest','actual-manifest.json'),('capture','capture.json'),('owned','owned-code.json'),('contract','actual-contract.json'),
       ('selected_evidence','actual-selected-evidence.json'),('filecheck','actual-filecheck.json'),('retained_accounting','actual-retained-read-accounting.json'),
       ('acquisition_receipt','actual-acquisition-receipt.json'),('source_manifest','source-manifest.json'),('producer','produce.py'),('entry_seed','entry-seed.json')]:
        need(delivery[key]==subj(name),'delivery exact subject '+key)
    producer=raw[SUB+'produce.py'].decode('utf8');tree=ast.parse(producer)
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    maintext=ast.get_source_segment(producer,main)
    need(maintext.index("save('claim.json'")<maintext.index("with (ROOT.parent/'eu4.exe').open('rb') as target:"),'claim precedesPE source order')
    need(maintext.index('TARGET_CONTEXT_NORMAL_EXIT=True')<maintext.index("PHASE='source_engine_after'")
      <maintext.index("save('capture.json',value)"),'normal context exit before postguards/publication')
    need("_,post=source_guard(base_pin)" in maintext and 'require(post==pins' in maintext and 'all(stream_pin(Path(p))==v for p,v in review_pins.items())' in maintext,'postguard source order')
    save_node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='save')
    need(".open('x'" in ast.get_source_segment(producer,save_node),'exclusive claim/output creates')
    replay={
      'schema':'EU4-R75-ACTUAL-INDEPENDENT-RAW-REPLAY/1','sealed':True,
      'subject_actual_manifest':subj('actual-manifest.json'),'subject_capture_pin':subj('capture.json'),
      'subject_owned_pin':subj('owned-code.json'),'subject_contract_pin':subj('actual-contract.json'),
      'selected_pdata':metadata,'cached_previous':cap['previous_retained_only'],'cached_next':cap['next_retained_only'],
      'raw16_hex':code.hex(),'rows':[{k:row[k] for k in ('rva','bytes','mnemonic','operands')} for row in rows],
      'local_normal_CFG_closed':True,'whole_993570_CFG_closed':False,'explicit_memory_operand_count':0,'explicit_store_count':0,
      'CALL_count':0,'branch_count':0,'RET':'0x993667','implicit_stack_reads':stack,'implicit_stack_read_bytes':48,
      'normal_RAX':'current R14 bits at fragment entry, copied before POP R14; unchanged by the remaining selected rows',
      'normal_RSP':'F+0x60=S69+8 if F=S69-0x58 and saved/control stack remains valid',
      'flags':'ADD RSP,0x30 replaces arithmetic status flags; DF is not modified and remains unknown',
      'decoder_witness':{'input_bytes':55,'unique_bytes':16,'overlap_bytes':39,'new_decoder_calls_by_review':0},
      'preflight_read_precision':{'listed_bytes':preflight_listed,'reported_explicit_bytes':preflight['explicit_bytes'],'unitemized_conservative_delta':preflight_delta},
      'source_completed_phases':phases,'author_PE_bytes':{'full_hash_reads':76925008,'new_metadata':12,'new_code':16,'total':76925036},
      'author_retained_upper':3573448,'author_combined_source_retained_upper':20625507,
      'selected_input_and_return_limitations':['NULL JE-entry RAX=R12=0 is overwritten/restored; not the final RAX/R12 contract.',
        'Only a normal97bd30/R14-preservation premise identifies returned currentR14 with original output pointer.',
        'No selected D/header dereference/store does not prove pointees nonaliased with read stack, nor D0/current header contents.',
        'Exact pdata range and local RET do not prove independent Win64 callable function or whole993570 closure.']}
    replay_pin=write('raw-replay.json',replay)
    for path,p in pins.items():read(path,p,'after')
    guard()
    findings={
      'schema':'EU4-R75-ACTUAL-INDEPENDENT-REVIEW/1','sealed':True,'passed':True,'blocking_findings':[],
      'scope':'full_retained_actual_package_and_selected_null_successor_machine_contract',
      'subject_actual_manifest':subj('actual-manifest.json'),'subject_capture_pin':subj('capture.json'),
      'subject_contract_pin':subj('actual-contract.json'),'subject_owned_pin':subj('owned-code.json'),
      'subject_selected_pin':subj('actual-selected-evidence.json'),'subject_filecheck_pin':subj('actual-filecheck.json'),
      'subject_delivery_pin':subj('actual-delivery.json'),'raw_replay':replay_pin,
      'roles':{'R75_actual_author':'validation_audit (Val)','current_reviewer':'War; independent of R75 actual and retained author',
               'prior_overlap':'War authored R75 raw entry review and original R69 source design, later reviewed Val R69 actual. Those are disclosed upstream witnesses.',
               'source_peer':'D independently reviewed R75 source; source review is retained separately, not claimed new by this review'},
      'checks':{'47_author_flat_pins_before_after':True,'38_decoder_expected_metadata_equal_not_opened':True,
                'three_subject_bound_reviews_and_new_exact_once_root_auth':True,'claim_and_capture_subjects':True,
                'raw12B_metadata_and16B_code':True,'all8_instruction_raw_GP_rows':True,'local_only_CFG_and_stack_projection':True,
                'completed_read_and_resource_bills':True,'normal_context_exit_before_capture_source_order':True},
      'conclusions':[
        'The only new descriptor is19163@0x249d244:583699006836990038dde701, giving[0x993658,0x993668). Its16B are fully retained and match8rows.',
        'MOVRAX,currentR14 precedes fivePOP restores. Normal selected return copies current fragment-entry R14 bits, not JE-entryzero or scalarDWORD[D].',
        'ADD RSP,0x30 then5POP+RET reads6QWORD/48B from the original frame and leavesRSP=S69+8 under valid uncorrupted saved/control-stack assumptions.',
        'No selected CALL, branch or explicit memory operand/store occurs. ADD replaces arithmetic flags; DF remainsunknown.',
        'The selected suffix is locally normalclosed; whole993570, independent function/formals, prior97bd30 behavior and final D/header state remainunknown.',
        'Direct pins, three review subjects, rootgrant06188d1d..., exclusive claim and capture publication order agree; normal file context exit and final guards are retained witness.'
      ],
      'precision_notes':[
        'The preflight receipt lists62571B but reports65560B, a conservative unitemized2989B delta; not an inferred extra read. Covered by prior manual allowance.',
        'The reviewer reads only47author flat sources plus explicit delivery/check extensions; no recursive old closure or enginebody is authenticated anew.',
        'Current source/engine equality in capture and historical twoPE SHA passes are producer witnesses. This review rehashes ordinary flat files only, notPE or engine.',
        'Before/after equality is not external atomicity/ABA exclusion. Earlier completed source/read journals are not full OS/loader IO or failed partial IO proofs.',
        'normal_target_context_exit is Python source/retained evidence, not an independent OS close-return check. owned-code may be emitted before targetclose; committed capture is after close/postguards.',
        'Software self-memory guards and collected direct command exit0 are retained; hard Job and universal process-tree cleanup proof are not claimed.',
        'Local no D/header access does not prove their ranges disjoint from the stack; prior aliases can change D/header/saved words.',
        'No business units, recipient direction, selected effect, current world, native invocation, retry or lease authorization follows.'
      ],
      'author_resource_witness':{'source_completed_bytes':17052059,'retained_upper_bytes':3573448,'combined_upper_bytes':20625507,
        'PE_total_bytes_separate':76925036,'producer_peak_private_bytes':cap['peak_committed_bytes_observed'],
        'producer_invocation_seconds':acquisition['tool_wall_seconds'],'timing_scope':acquisition['timing_scope'],'hard_Job_installed':False},
      'review_resources':{'explicit_file_read_bytes_before_after':sum(v['bytes'] for v in JOURNAL),
        'manual_inspection_allowance_bytes':MANUAL,'prior_failed_review_allowance_bytes':1024*1024,'retained_and_check_allowance_bytes':2*1024*1024,
        'stage_limit_bytes':24*1024*1024,'ordinary_file_limit_bytes':4*1024*1024,
        'software_memory_guard_bytes':768*1024*1024,'self_peak_private_bytes':PEAK,'full_OS_IO_claimed':False},
      'source_pins_before_after_equal':True,'admitted_flat_file_count':len(pins),'recursive_closure_claimed':False,
      'operations':{'PE_stat_open_hash':0,'engine_body':0,'decoder':0,'author_programs':0,'tests':0,'game_process':0,'Frida':0,'native_calls':0,'requests':0},
      'authority':{'native_ready':False,'callable':False,'reader_adoption_allowed':False,'selected_effect_verified':False,
        'amount_units_verified':False,'recipient_direction_verified':False,'world_lease':False,'atomic_snapshot':False,
        'authorizes_retry':False,'further_actual_authorized':False},
      'author_frozen_files_need_change':False,'self_diagnostics':['R1 own audit exact preflight sum assertion stopped on conservative billing mismatch; original source/failure retained. R2 only records listed versus billed delta; no author/actual retry.'],'all_shells_collected':True}
    findings_pin=write('findings.json',findings);journal_pin=write('read-journal.json',JOURNAL)
    all_pins=dict(pins)
    all_pins['work/review_r75_actual_20261016_r2.py']=pin(Path(__file__).read_bytes())
    for path in ('work/review_r75_actual_20261016.py','work/reports/war-peace-api-20261016-r75-actual-independent-review/failure.txt'):
        all_pins[path]=pin(read(path,phase='own_failure_retention'))
    for name,p in [('raw-replay.json',replay_pin),('findings.json',findings_pin),('read-journal.json',journal_pin)]:
        all_pins[(OUT/name).relative_to(ROOT).as_posix()]=p
    manifest_pin=write('manifest.json',{'schema':'EU4-R75-ACTUAL-INDEPENDENT-REVIEW-MANIFEST/1','sealed':True,'passed':True,
      'source_pins':all_pins,'pin_count':len(all_pins),'author_flat_pins':47,'decoder38_metadata_only':True,
      'native_ready':False,'further_actual_authorized':False})
    print(json.dumps({'passed':True,'findings':findings_pin,'manifest':manifest_pin,'raw_replay':replay_pin,
      'read_bytes':sum(v['bytes'] for v in JOURNAL),'flat':len(pins),'peak':PEAK}))

def check():
    path=(OUT/'manifest.json').relative_to(ROOT).as_posix();raw=read(path,phase='review_filecheck');manifest=parse(raw)
    for p,v in manifest['source_pins'].items():read(p,v,'review_filecheck')
    need(manifest['pin_count']==len(manifest['source_pins']),'review pin count')
    result={'schema':'EU4-R75-ACTUAL-REVIEW-VERIFICATION/1','passed':True,'manifest_pin':pin(raw),'pin_count':manifest['pin_count'],
      'file_only':True,'PE_engine_accesses':0,'author_program_tests_game_native':0,'further_actual_authorized':False}
    p=write('verification.json',result);print(json.dumps({'passed':True,'verification':p,'pins':manifest['pin_count']}))

if __name__=='__main__':
    try:
        if sys.argv[1:]==['--check']:check()
        else:need(sys.argv[1:]==[],'noargs or --check only');audit()
    except Exception:
        if OUT.exists():
            with (OUT/'failure.txt').open('x',encoding='utf8') as f:f.write(traceback.format_exc())
        raise
