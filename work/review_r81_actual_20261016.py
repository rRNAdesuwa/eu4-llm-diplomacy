"""Non-author R81 retained-only audit: no PE, decoder, author program or runtime."""
import ast
import collections
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys
import traceback

ROOT=Path(__file__).resolve().parent.parent
SUB='work/reports/war-peace-api-20261016-r81-selector-prefix-tail/'
OLD='work/reports/war-peace-api-20261016-r80-unregistered-call-prefix/'
OUT=ROOT/'work/reports/war-peace-api-20261016-r81-actual-independent-review'
CAP=4*1024**2;LIMIT=24*1024**2;MANUAL=1024**2;TAIL=2*1024**2
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
P={};C={};J=[]
HARD={
 'actual-manifest.json':(16550,'eb8f4a1171c388c1805093a0c41143e1f5f2bc54c08602b235d6ad15850c78c3'),
 'actual-contract.json':(6046,'e2196dd433efbe68d57a1c37ed4b74242a4bfb5f0d00a910e732390ca29fc558'),
 'capture.json':(79710,'9ed8dcd8f053ed9749d9786443ea90b806538f8c062eb5ccdec072671635b5f8'),
 'owned-code.json':(1260,'38a6c1dd3c614d1cddbb9fec77faf0ca7e07e4fa3bfd1e34d110883872119687'),
 'actual-selected-evidence.json':(17878,'480b65763ec022ea2bbde70dcca9435ac713e67e4816852c3fc51be8a134dc3c'),
 'actual-filecheck.json':(6571,'8ad6a6ea746a4c6a0a4bab68cb2d189d6ba601b6024784ffab3660b0c1cbfabd'),
 'actual-delivery.json':(3392,'4989b612f1b49b65da660f5ab2eed6472e3c4c39d5119787784f1917d85f2a28'),
 'actual-publication-accounting.json':(3025,'5e497e7a3dc485cf15c327327a1ffbba77b06a87fce4e6d1bc8009b01e78c79f'),
 'actual-completion.json':(1334,'33e8f7c83bfec8e52dba025845e7b51de8a4f3f74a8feede2e732910d9442594')}
ROWS=[
 (0x97bd6e,'48c1e820','shr','rax, 0x20','RAX=L>>32'),
 (0x97bd72,'98','cwde','','K=sext16_to32(AX), EAX write clears RAX high32'),
 (0x97bd73,'498b4850','mov','rcx, qword ptr [r8 + 0x50]','B=M64[W+0x50]; RCX=B'),
 (0x97bd77,'4963505c','movsxd','rdx, dword ptr [r8 + 0x5c]','N=sext32_to64(M32[W+0x5c])'),
 (0x97bd7b,'48c1e204','shl','rdx, 4','RDX=16*N modulo2^64'),
 (0x97bd7f,'4803d1','add','rdx, rcx','E=B+16*N modulo2^64; RDX=E'),
 (0x97bd82,'483bca','cmp','rcx, rdx','Compare cursor B with E'),
 (0x97bd85,'740d','je','0x97bd94','If equal, zero-return block; otherwise key compare'),
 (0x97bd87,'3901','cmp','dword ptr [rcx], eax','Compare record DWORD key with K; does not store'),
 (0x97bd89,'740c','je','0x97bd97','First equal DWORD takes value-return block'),
 (0x97bd8b,'4883c110','add','rcx, 0x10','Advance cursor16 modulo2^64'),
 (0x97bd8f,'483bca','cmp','rcx, rdx','Compare advanced cursor with E'),
 (0x97bd92,'75f3','jne','0x97bd87','If cursor!=E, local backedge'),
 (0x97bd94,'33c0','xor','eax, eax','RAX=0 through EAX zero-upper32'),
 (0x97bd96,'c3','ret','','Read8B[entryRSP]; RSP+=8'),
 (0x97bd97,'488b4108','mov','rax, qword ptr [rcx + 8]','RAX=M64[first_matching_record+8], possibly0'),
 (0x97bd9b,'c3','ret','','Read8B[entryRSP]; RSP+=8')]


def need(v,m):
    if not v:raise AssertionError(m)


def memory():
    class PMC(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong),('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t),('PrivateUsage',ctypes.c_size_t)]
    p=PMC();p.cb=ctypes.sizeof(p)
    k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=ctypes.c_void_p
    a=ctypes.WinDLL('psapi');a.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
    need(a.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(p),p.cb),'own memory query')
    need(p.PrivateUsage<768*1024**2 and p.PeakPagefileUsage<1024**3,'software768M/1G stop')
    return {'private_bytes':p.PrivateUsage,'peak_pagefile_bytes':p.PeakPagefileUsage}


def digest(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def normalize(n):
    p=(ROOT/n).resolve();need(p.is_relative_to(ROOT),'flat project-local source')
    rel=p.relative_to(ROOT).as_posix()
    need(not rel.startswith('work/deps/') and p.name.lower()!='eu4.exe','no native engine or PE open')
    return rel


def read(n,phase,expected=None):
    n=normalize(n);p=ROOT/n;size=p.stat().st_size
    need(size<=CAP and sum(e['bytes'] for e in J)+size+MANUAL+TAIL<=LIMIT,'preread source4M/stage24M')
    memory();b=p.read_bytes();d=digest(b);J.append({'path':n,'phase':phase,**d})
    need(len(b)==size,'size stable')
    if expected is not None:need(d=={k:expected[k] for k in ('bytes','sha256')},'exact pin '+n)
    return b


def admit(n,p):
    n=normalize(n);p={k:p[k] for k in ('bytes','sha256')}
    if n in P:need(P[n]==p,'flat pin agreement')
    else:C[n]=read(n,'before',p);P[n]=p


def strict(b):
    def pairs(xs):
        d={}
        for k,v in xs:need(k not in d,'no duplicate JSON keys');d[k]=v
        return d
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))


def obj(n):return strict(C[normalize(n)])
def triple(n):return {'path':normalize(n),**P[normalize(n)]}


def save(n,x):
    b=(json.dumps(x,ensure_ascii=True,indent=2)+'\n').encode()
    with (OUT/n).open('xb') as f:f.write(b)
    return digest(b)


def body(text,name):
    a=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    return '\n'.join(text.splitlines()[a.lineno-1:a.end_lineno])


def review():
    OUT.mkdir(exist_ok=False);before=memory()
    for n,(size,sha) in HARD.items():admit(SUB+n,{'bytes':size,'sha256':sha})
    m=obj(SUB+'actual-manifest.json');need(m['sealed'] and m['file_count']==len(m['files'])==47,'47 explicit flat files')
    for n,p in m['files'].items():admit(n,p)
    delivery=obj(SUB+'actual-delivery.json');completion=obj(SUB+'actual-completion.json')
    for n,p in delivery['pins'].items():admit(SUB+n,p)
    for key,n in [('command_receipts','actual-command-receipts.json'),('publication_accounting','actual-publication-accounting.json')]:admit(SUB+n,delivery[key])
    for n,p in completion['pins'].items():admit(SUB+n,p)
    own=Path(__file__).relative_to(ROOT).as_posix();b=read(own,'own_source_before');P[own]=digest(b);C[own]=b
    c=obj(SUB+'capture.json');o=obj(SUB+'owned-code.json');s=obj(SUB+'actual-selected-evidence.json');con=obj(SUB+'actual-contract.json')
    src=obj(SUB+'source-manifest.json');auth=obj(SUB+'run-authorization.json');seed=obj(SUB+'entry-seed.json');claim=obj(SUB+'claim.json')
    need(c['owned_code_pin']==s['owned_pin']==P[SUB+'owned-code.json'] and s['capture_pin']==P[SUB+'capture.json'],'owned/capture binding')
    for field,n in [('capture_pin','capture.json'),('owned_pin','owned-code.json'),('selected_pin','actual-selected-evidence.json')]:need(con[field]==P[SUB+n],'contract component pin')
    need(c['source_manifest']==o['source_manifest']==claim['source_manifest']==auth['source_manifest']==P[SUB+'source-manifest.json'],'source manifest exact')
    need(c['entry_seed_pin']==auth['entry_seed_pin']==P[SUB+'entry-seed.json'] and auth['producer_pin']==P[SUB+'produce.py'],'entry/producer exact')
    need(c['authorization_pin']==claim['authorization_pin']==P[SUB+'run-authorization.json'],'authorization exact')
    need(auth['root_explicit_start_received'] and auth['sealed'] and auth['single_attempt'] and auth['sole_executor']=='diplomacy_static' and auth['operation']=='one-fixed-cached2-plus-new48B-continuation','once root grant')
    need((auth['requested_bytes'],auth['cached_bytes'],auth['combined_bytes'])==(48,2,50),'authorized byte split')
    reviewpins={}
    for role in ('root_raw_entry_review','upstream_actual_review','source_peer_review'):
        group=auth[role]
        for p in group.values():
            need(P[normalize(p['path'])]=={k:p[k] for k in ('bytes','sha256')},'review exact subject file')
            reviewpins[str((ROOT/p['path']).resolve())]={k:p[k] for k in ('bytes','sha256')}
        f=obj(group['findings']['path']);need(f['sealed'] and f['passed'] and f['blocking_findings']==[],'passed gate')
        if role=='upstream_actual_review':
            for key,n in [('subject_actual_manifest','actual-manifest.json'),('subject_capture_pin','capture.json'),('subject_contract_pin','actual-contract.json'),('subject_owned_pin','owned-code.json'),('subject_selected_pin','actual-selected-evidence.json')]:need(f[key]==triple(OLD+n),'R80 five exact full subject witness')
        else:
            need(f['subject_source_manifest']==P[SUB+'source-manifest.json'] and f['subject_producer']==P[SUB+'produce.py'] and f['subject_entry_seed']==P[SUB+'entry-seed.json'],'newR81 gate subject triples')
            if role=='root_raw_entry_review':need(f['scope']=='cached_partial_continuation_seed_only','entry raw gate scope')
    need(c['three_review_pins']==claim['three_review_pins']==reviewpins,'three exact review map')
    need(c['source_pins']==claim['source_pins']==src['source_pins'],'source map equality')
    engines=src['decoder_expected_witness_pins']
    need(len(engines)==38 and engines==m['decoder_expected_witness_pins']==c['decoder_expected_witness_pins'],'38 engine metadata only')
    need(src['actual_source_pin_count']==len(src['actual_source_pins'])==25 and len(src['source_pins'])==63 and src['source_pins']==src['actual_source_pins']|engines,'25 source+38 engines')
    for n,p in src['actual_source_pins'].items():need(P[normalize(n)]==p,'flat source actual pin read')

    oldo=obj(OLD+'owned-code.json');oldc=obj(OLD+'capture.json');oldcon=obj(OLD+'actual-contract.json')
    oldraw=bytes.fromhex(oldo['raw_hex']);raw=bytes.fromhex(o['raw_hex']);fresh=bytes.fromhex(o['new_raw_hex'])
    need(len(raw)==50 and len(fresh)==48 and raw==bytes.fromhex(o['cached_raw_hex'])+fresh and raw[:2]==oldraw[62:64]==bytes.fromhex('48c1'),'exact cached2+new48')
    need(hashlib.sha256(raw).hexdigest()==o['sha256'] and hashlib.sha256(fresh).hexdigest()==o['new_raw_sha256'],'combined/new raw hash')
    need(o['cache_source_owned_pin']==s['cache_source_owned_pin']==c['cache_source_owned_pin']==P[OLD+'owned-code.json'],'carry source exact')
    need(seed['continuation_state']==oldcon['conditional_projection'],'inherit current state, no fresh ABI reset')
    need(seed['partial_terminal']==oldc['analysis']['terminals'] and seed['cached_raw_offset_in_old64']==o['cache_source_raw_offset']==62,'old partial remains prior boundary')
    need(o['physical_window']==c['physical_window']==['0x97bd70','0x97bda0'] and o['window']==c['window']==['0x97bd6e','0x97bda0'],'fixed continuation windows')
    need((o['physical_file_offset'],o['combined_mapping_file_offset'])==(9941360,9941358),'cached mapping offsets')
    need(o['new_physical_bytes']==c['new_physical_code_bytes']==48 and o['combined_bytes']==c['combined_analysis_bytes']==50 and o['cached_bytes']==c['cached_reused_bytes']==2,'physical vs analysis byte split')
    need(c['new_pdata_requests']==[] and c['new_pdata_physical_bytes']==0 and c['prior64B_targeted_reread_bytes']==o['prior64B_targeted_reread_bytes']==0,'zero newmetadata/old targeted reread')
    need(c['cached_previous']==seed['cache_previous']==oldc['cached_previous'] and c['cached_next']==seed['cache_next']==oldc['cached_next'],'cached descriptors only')
    need(c['cached_gap_valid'] and c['cached_carry_valid'] and c['mapping_valid'] and claim['cached_gap_valid'] and claim['cached_carry_valid'] and claim['mapping_valid'],'plan guards valid')
    anchors=obj('work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json')
    maps=[q for q in anchors['sections'] if int(q['rva'],16)<=0x97bd6e and 0x97bda0<=int(q['rva'],16)+q['raw_size']]
    need(len(maps)==1 and maps[0]['name']=='.text' and maps[0]['raw_file_offset']+0x97bd6e-int(maps[0]['rva'],16)==9941358,'unique cached text mapping')
    rows=c['analysis']['instructions'];need(len(rows)==17 and rows==s['retained_decoder_rows'] and len(s['all17_raw_reviewed_rows'])==17,'17 exact retained rows')
    cursor=0;replayed=[];reads=[]
    for actual,selected,(rva,code,mnemonic,operands,meaning) in zip(rows,s['all17_raw_reviewed_rows'],ROWS):
        b=bytes.fromhex(code)
        need(rva==0x97bd6e+cursor and raw[cursor:cursor+len(b)]==b,'owned contiguous bytes')
        need((actual['rva'],actual['bytes'],actual['mnemonic'],actual['operands'])==(hex(rva),code,mnemonic,operands),'raw opcode manual/retained agreement')
        need(selected['rva']==hex(rva) and selected['raw_hex']==code,'manual selected exact row')
        for mem in actual['memory_operands']:
            need(mem['read'] and not mem['write'],'all explicit memory operands source only')
            reads.append({'rva':hex(rva),'width':mem['width_bytes'],'base':mem['base'],'offset':mem['displacement']})
        replayed.append({'rva':hex(rva),'raw_hex':code,'operation':meaning,'explicit_or_implicit_memory_store':False,'implicit_stack_read':8 if mnemonic=='ret' else 0})
        cursor+=len(b)
    need(cursor==c['analysis']['decoded_unique_bytes']==46 and raw[46:]==bytes.fromhex('cccccccc'),'46 decoded plus4 owned CC not decoded')
    need(reads==[{'rva':'0x97bd73','width':8,'base':'r8','offset':80},{'rva':'0x97bd77','width':4,'base':'r8','offset':92},{'rva':'0x97bd87','width':4,'base':'rcx','offset':0},{'rva':'0x97bd97','width':8,'base':'rcx','offset':8}],'four data load/compare sites and widths')
    targets=[]
    for site,code,target,fall in [(0x97bd85,'740d',0x97bd94,0x97bd87),(0x97bd89,'740c',0x97bd97,0x97bd8b),(0x97bd92,'75f3',0x97bd87,0x97bd94)]:
        disp=struct.unpack('<b',bytes.fromhex(code)[1:])[0];need(site+2+disp==target,'signed rel8 target')
        targets.append({'site':hex(site),'raw':code,'signed_rel8':disp,'target':hex(target),'fallthrough':hex(fall)})
    edges=c['analysis']['edges'];need(len(edges)==3 and [(e['site'],e['target_rva'],e['fallthrough']) for e in edges]==[(e['site'],e['target'],e['fallthrough']) for e in targets],'all3 CFGedges')
    need(all(e['inside_owned_window'] and e['local_branch_target_enqueued'] for e in edges),'local CFG targets only')
    need(c['analysis']['terminals']==[{'kind':'normal_ret','rva':'0x97bd96'},{'kind':'normal_ret','rva':'0x97bd9b'}] and c['analysis']['local_normal_CFG_closed'] and c['analysis']['undecoded_owned_intervals']==[['0x97bd9c','0x97bda0']],'twoRET local model closed, CC outside execution')
    need(not c['analysis']['dynamic_reachability_verified'] and not c['known_function_extent'] and not c['whole_function_owned'],'local normalmodel not function identity')
    looks=c['analysis']['lookahead_inputs'];union=set()
    for e in looks:
        start=int(e['rva'],16);need(0x97bd6e<=start<0x97bda0 and start+e['bytes']<=0x97bda0,'owned lookahead')
        union.update(range(start,start+e['bytes']))
    need(len(looks)==17 and sum(e['bytes'] for e in looks)==230 and len(union)==50 and c['analysis']['decoder_overlap_bytes']==180,'230 cumulative/50 unique/180 repeated')
    need(c['sparse_reads']==[{'kind':'continuation_new_suffix','rva':'0x97bd70','end_exclusive':'0x97bda0','file_offset':9941360,'requested_bytes':48,'bytes':48,'complete':True}],'single physical48 targeted request')
    need(c['full_PE_authentication_reads']==[{'phase':phase,'bytes_read':38462504,'completed':True,'sha256':GAME} for phase in ('before','after')] and c['total_PE_physical_bytes']==76925008+48==76925056,'twoSHA separate bill')
    events=c['source_file_reads'];need(len(events)==158 and sum(e['bytes'] for e in events)==c['source_file_read_bytes']==17331379,'source completed event bill')
    known={str((ROOT/n).resolve()):p for n,p in src['source_pins'].items()};known.update({str((ROOT/n).resolve()):p for n,p in P.items()})
    for e in events:need(e['path'] in known and e['bytes']==known[e['path']]['bytes'],'completed source event names/byte widths')
    phases=collections.Counter((e['phase'],e['operation']) for e in events)
    for phase in ('source_engine_before','source_engine_after'):
        seen={e['path']:e['bytes'] for e in events if e['phase']==phase and e['operation']=='streaming_engine_pin'}
        need(seen=={str((ROOT/n).resolve()):p['bytes'] for n,p in engines.items()} and len(seen)==38,'38before/38after engine metadata witness')

    text=C[SUB+'produce.py'].decode();guard=body(text,'source_guard');main=body(text,'main')
    need(guard.index('raw_manifest=read_source')<guard.index('==expected_manifest_pin')<guard.index('json.loads(raw_manifest)')<guard.index('for name,expected in pins.items()'),'rawbuffer authorized before parse/engine')
    need(main.count('source_guard(base_pin)')==2,'both guards same authorized base')
    need(main.index("for label in ('root_raw_entry_review'")<main.index('base,pins=source_guard(base_pin)')<main.index("with (ROOT.parent/'eu4.exe').open"),'allreview gates before engine andPE')
    need(main.index("'Manifest changed before authorized raw-buffer guard'")<main.index('base,pins=source_guard(base_pin)')<main.index("'Manifest changed after authorized raw-buffer guard'"),'first external exactbase guards')
    need(main.index("save('claim.json'")<main.index("with (ROOT.parent/'eu4.exe').open") and claim['automatic_retry'] is False,'claim-before-target/no retry')
    need(main.index('TARGET_CONTEXT_NORMAL_EXIT=True')<main.index('_,post=source_guard(base_pin)')<main.index("save('capture.json',value)"),'normal close before postguards/capture')
    saveast=ast.parse(body(text,'save'));need(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='open' and n.args and isinstance(n.args[0],ast.Constant) and n.args[0].value in ('x','xb') for n in ast.walk(saveast)),'exclusive output write mode')
    need(c['normal_target_context_exit'] and c['commit_after_target_close_and_final_guards'] and c['source_engine_before_after_equal'],'retained postguard/close flags')
    need(c['R80_partial_history_unchanged'] and c['continuation_not_new_Win64_entry'],'scope preserves prefix history')
    need(all(v is False for v in con['authority'].values()) and all(v is False for v in m['authority'].values()),'author authority remains false')
    for k in ('game_process_accesses','Frida_operations','native_game_calls','requests','tests','new_header_data_literal_vtable_unwind_callee_bytes'):need(c[k]==0,'no runtime/data followup')
    command=obj(SUB+'actual-command.json');cmds=obj(SUB+'actual-command-receipts.json')
    need(command['before']==command['after'] and command['exit_code']==0 and command['direct_child_collected'] and command['retry'] is False and len(command['argv'])==3 and command['argv'][-1]==SUB+'produce.py','noarg single actual/collected')
    for n,p in command['before'].items():need(P[SUB+n]==p,'command exactsource')
    need(cmds['all_shells_collected'] and cmds['actual_attempts']==1 and cmds['retries']==0 and [e['exit_code'] for e in cmds['commands']]==[0,0,0],'actual/seal/check collected receipts')
    need(completion['all_shells_collected'] and completion['commands_all_exit_zero'] and completion['actual_attempts']==1 and completion['actual_retries']==0 and completion['publication_tool_receipt']['exit_code']==0,'actual publication collected')
    for n in ('actual.stderr.txt','actual-seal.stderr.txt','actual-check.stderr.txt','actual-publication.stderr.txt'):need(C[SUB+n]==b'','stderr preserved empty')
    stdout=strict(C[SUB+'actual.stdout.txt']);need((stdout['rows'],stdout['new_code_bytes'],stdout['cached_bytes'],stdout['combined_bytes'],stdout['source_journal_bytes'])==(17,48,2,50,17331379),'actual stdout samecapture')
    account=obj(SUB+'actual-read-accounting.json');fc=obj(SUB+'actual-filecheck.json');pub=obj(SUB+'actual-publication-accounting.json')
    need(sum(e['bytes'] for e in account['read_events'])==account['measured_read_bytes']==1213660,'retained seal bill')
    need(fc['passed'] and fc['files']==47 and fc['subject_manifest']==P[SUB+'actual-manifest.json'] and sum(e['bytes'] for e in fc['read_events'])==fc['read_bytes']==662298,'first retainedcheck bill')
    need(sum(e['bytes'] for e in pub['publication_read_events'])==pub['publication_measured_bytes']==150382,'publication bill')
    upper=1213660+662298+150382+1048576+111762
    need(upper==pub['successful_upper_with_remaining_publication_allowance_bytes']==3186678 and pub['frozen_seal_conservative_upper_bytes']==6718684 and upper<16*1024**2,'retained successful upper separated')
    need(completion['completion_measured_read_bytes']==11227 and completion['within_final_publication_reserve'],'completion withinpublication allowance')
    need(pub['producer_source_bytes_separate']==17331379 and pub['PE_SHA_plus_targeted_bytes_separate']==76925056 and pub['full_OS_IO_claim'] is False,'separate resource layers')
    need(c['peak_committed_bytes_observed']==con['resources']['producer_peak_committed_witness']==24145920 and c['hard_Job_installed'] is False,'peak onlyproducerwitness nohardJob')

    projection={'premises':['Inherited R80 current GP/state, normal valid control transfer and memory; not fresh function formals.','For finite N-record interpretation: stable valid range, nonnegative N and no invalid address wrap. Native does not check these.'],
     'key':'K = zext32_to64(sext16_to32((entry_current_RAX >>32)&0xffff)); comparison is low32 DWORD only',
     'list':'W=entry_current_R8; B=M64[W+0x50]; N=sext32(M32[W+0x5c]); E=B+16*N modulo2^64',
     'zero_exit':{'rva':'0x97bd96','RAX':0,'RCX':'E','RDX':'E','R8':'W unchanged','R9':'inherited R80 R9 unchanged by suffix','RSP':'entryQ+8=S69-0x58','flags':'XOR EAX,EAX: ZF1/SF0/CF0/OF0/PF1; AF undefined; DF inherited unknown'},
     'match_exit':{'rva':'0x97bd9b','RAX':'M64[first DWORD-matching record+8], may be0','RCX':'matching record address','RDX':'E','R8':'W unchanged','R9':'inherited R80 R9 unchanged by suffix','RSP':'entryQ+8=S69-0x58','flags':'Equality CMP DWORD[RCX],EAX sets ZF1/SF0/CF0/OF0/PF1/AF0; following JE/MOV/RET do not alter them; DF inherited unknown'},
     'normal_return_target':'Read8B[entryQ=S69-0x60]; expected prior CALL address modulebase+99358f only if valid unchanged control stack.',
     'memory_stores':0,'stack_reads':'Exactly one RET8B per terminating path; two RET sites are alternatives, not16B per execution.',
     'negative_count':'Signed32 N is not rejected; bounds/capacity/valid access and useful termination remain unknown.',
     'zero_ambiguity':['N=0/end reached returns0','no matching DWORD returns0','first matching record can contain QWORDvalue0'],
     'not_proved':['originalD/header identity or unchanged content across caller CALL-stack aliases','fullhandle/generation/type/lifecycle','unique key/match or returned pointer ownership','complete function extent/leaf identity','runtime execution/effect/units/recipient/lifetime']}
    rawreplay={'schema':'EU4-R81-INDEPENDENT-RAW-REPLAY/1','source_owned_pin':triple(SUB+'owned-code.json'),'raw_combined_bytes':50,'physical_new_bytes':48,'cached_bytes':2,'all17_rows':replayed,'decoded_combined_bytes':46,'decoded_new_positions':44,'undecoded_owned_CC':{'range':['0x97bd9c','0x97bda0'],'raw':'cccccccc','instruction_effect_not_decoded':True},'branch_rel8':targets,'data_memory_operand_sites':reads,'conditional_projection':projection,'new_decoder_operations':0,'runtime_accesses':0}
    save('raw-replay.json',rawreplay)
    for n,p in list(P.items()):read(n,'after',p)
    after=memory();charged=sum(e['bytes'] for e in J);need(charged+MANUAL+TAIL<=LIMIT,'review upper24M')
    findings={'schema':'EU4-R81-ACTUAL-INDEPENDENT-REVIEW/1','sealed':True,'passed':True,'blocking_findings':[],
      'scope':'Full non-author retained-file/raw review of fixed cached2B+new48B continuation only, not independent API/wholefunction/runtime permission',
      'subject_actual_manifest':triple(SUB+'actual-manifest.json'),'subject_capture_pin':triple(SUB+'capture.json'),'subject_contract_pin':triple(SUB+'actual-contract.json'),'subject_owned_pin':triple(SUB+'owned-code.json'),'subject_selected_pin':triple(SUB+'actual-selected-evidence.json'),
      'subject_source_manifest':triple(SUB+'source-manifest.json'),'subject_producer':triple(SUB+'produce.py'),'subject_authorization':triple(SUB+'run-authorization.json'),
      'role_disclosure':{'R81_actual_author':'diplomacy_static; not this reviewer','reviewer':'war_api','prior_roles':['R80 full reviewer (upstream accepted witness produced by this reviewer)','R79 source/actual author','R78 full reviewer','lookupv5 author and v6 planning author'],
        'R80_prior_review_scope':'Only five exact accepted subject pins and cache-carry fields are bound; no recursive re-review of the old74-pin review graph. R81 actual author is independent of this reviewer.','not_claimed':'Independent origin of every upstream historical source or v6 non-author acceptance.'},
      'result':{'new_physical_bytes':48,'cached_bytes':2,'combined_bytes':50,'complete_rows':17,'decoded_combined_bytes':46,'decoded_new_positions':44,'unreached_owned_bytes':4,'local_branches':3,'RET_sites':['0x97bd96','0x97bd9b'],'CALLs':0,'memory_stores':0,'wholefunction_extent_known':False},
      'checks':['All17 raw rows reproduce consecutive46B from cached2+new48; two RETs terminate paths and four following CC bytes remain owned but not decoded.','Raw SHR64/CWDE32 produce zero-upper32 K; MOVSXD consumes signedDWORD count; SHL4/ADD64 form modular end.','Three signedrel8 branches resolve exactly, including backedge; compares use DWORD key only. First matching record+8 value can be0, so return0 is ambiguous.','The suffix writes no memory and has no CALL. Each normalRET reads8B controlstack and incrementsRSP8; no capacity/nonnegative/type/fullhandle/lifecycle check is filled in.','Three subject-bound review gates and rootonce authorization precede sourceengine/PE access; rawmanifest bytes/SHA precede parsing and engine loop; close precedes postguards and capture publish.','47 manifest files plus explicit delivery/completion pins are flat before/after verified;38 engine pins remain metadata only; all158 completed source events match known names and sizes.'],
      'machine_projection':projection,
      'resources_author_witness':{'producer_source_events':158,'producer_source_bytes':17331379,'two_SHA_bytes':76925008,'new_code_physical_bytes':48,'total_PE_bytes':76925056,'new_metadata_bytes':0,'decoder_cumulative_input_bytes':230,'decoder_unique_owned_bytes':50,'decoder_overlap_bytes':180,
        'seal_completed_read_bytes':1213660,'first_filecheck_read_bytes':662298,'publication_completed_read_bytes':150382,'retained_successful_upper_bytes':3186678,'retained_prior_frozen_upper_bytes':6718684,'completion_reads_within_remaining_publication_allowance':11227,'producer_peak_committed_bytes_not_independent':24145920,'hard_Job_installed':False,'actual_attempts':1,'retries':0,'all_actual_shells_collected_witness':True,'whole_OS_IO_or_failure_path_universal_cap_claimed':False},
      'review_resources':{'flat_subject_files':len(P)-1,'completed_read_events':len(J),'completed_read_bytes':charged,'manual_schema_source_inspection_allowance_bytes':MANUAL,'sealing_report_first_check_reserve_bytes':TAIL,'successful_upper_bytes':charged+MANUAL+TAIL,'limit_bytes':LIMIT,'ordinary_file_limit_bytes':CAP,'source_pin_before_after_equal':True,'self_memory_before':before,'self_memory_after':after,'engine_metadata_only_pins':38,'engine_bodies_stat_or_opened':0,'software_guard_bytes':768*1024**2,'one_GiB_stop':True},
      'precision_notes':['Targeted new48B and cached2B are separate; two full SHA passes still read the entire PE. No statement that the prior64B never occurred in those hash reads.','The230 decoder input bytes are overlapping owned views, not new target reads.','Normal local CFG closure includes a backedge and is conditional, not unconditional valid traversal/termination or proof of wholefunction identity.','Before/after source/engine equality is historical witness, not atomic input authentication or ABA exclusion.','Collected shell/peak/duration evidence comes from authored receipts, not independent observation of past processes.','R80 historical partial/noRET and R79 bounded unknown remain frozen; later continuation adds conditional context.'],
      'limits':con['unknowns']+['No v6 candidate build/query/publication or R82/native scope is authorized. v6 R2 remains a proposal until root separately grants its build and non-author review follows.'],
      'operations':{'author_programs_or_tests_executed':0,'PE_stat_open_read':0,'engine_body_stat_open':0,'Capstone_import_decode':0,'game_process':0,'Frida':0,'native_calls':0,'requests':0,'all_review_shells_collected':True},'authority':dict(con['authority'])}
    save('findings.json',findings)
    save('read-accounting.json',{'schema':'EU4-R81-INDEPENDENT-READ-BILL/1','events':J,'measured_completed_bytes':charged,'manual_allowance':MANUAL,'seal_first_check_reserve':TAIL,'successful_upper_bytes':charged+MANUAL+TAIL,'limit':LIMIT,'full_OS_IO_claim':False})
    report='R81 retained-only full independent review: PASSED, no blocking differences.\n\nThe separately acquired48B plus exact cached2B give17 instructions/46 decoded bytes, with4 following owned CC not decoded. Three local branches and two RETs support a conditional16B-record first-DWORD-match search; its returned QWORD+8 can be0, just like the empty/no-match path. Signed count, valid range, termination, capacity/fullhandle/type and ownership/lifetime are unproved. RET reads8B stack per terminating path.\n\nExact review/auth/source/cache and normalclose/postguard publish evidence match;38 engine pins remain metadata witnesses. The reviewer produced the accepted R80 full review and authored R79; R81 actual author is diplomacy_static. No recursive historical graph, author program, PE, decoder, test or runtime was executed. No v6 build or new scope is authorized.\n'
    with (OUT/'report.md').open('x',encoding='utf-8',newline='\n') as f:f.write(report)
    pins=dict(P)
    for n in ('raw-replay.json','findings.json','read-accounting.json','report.md'):
        rel=(OUT/n).relative_to(ROOT).as_posix();pins[rel]=digest(read(rel,'own_output_seal'))
    save('manifest.json',{'schema':'EU4-R81-INDEPENDENT-FULL-MANIFEST/1','sealed':True,'passed':True,'files':pins,'file_count':len(pins),'subject_actual_manifest':triple(SUB+'actual-manifest.json'),'engine_metadata_only':True,'authority':dict(con['authority'])})
    roles={'author_actual_manifest':triple(SUB+'actual-manifest.json'),'author_contract':triple(SUB+'actual-contract.json'),'author_selected_evidence':triple(SUB+'actual-selected-evidence.json')}
    for key,n in [('independent_full_findings','findings.json'),('independent_full_manifest','manifest.json')]:roles[key]={'path':(OUT/n).relative_to(ROOT).as_posix(),**digest(read((OUT/n).relative_to(ROOT).as_posix(),'own_delivery_pin'))}
    save('lookup-source-roles.json',{'schema':'EU4-R81-FIVE-LOOKUP-SOURCE-ROLES/1','sealed':True,'roles':roles,'source_count':5,'v6_build_authorized':False,'native_ready':False,'notes':'Exactly five fixed JSON roles for future v6 direct sources; not the full transitive historical graph or build permission.'})
    print(json.dumps({'status':'sealed_independent_full_passed','findings':roles['independent_full_findings'],'manifest':roles['independent_full_manifest'],'first_check_required':True,'own_upper_bytes':charged+MANUAL+TAIL,'all_shells_collected':True}))


def check():
    raw=read((OUT/'manifest.json').relative_to(ROOT).as_posix(),'own_first_check_manifest');m=strict(raw)
    need(m['sealed'] and m['passed'] and m['file_count']==len(m['files']),'own manifest')
    for n,p in m['files'].items():read(n,'own_first_filecheck',p)
    rolesraw=read((OUT/'lookup-source-roles.json').relative_to(ROOT).as_posix(),'own_first_check_roles');roles=strict(rolesraw)
    need(roles['source_count']==5 and len(roles['roles'])==5,'five futurelookup roles')
    for p in roles['roles'].values():read(p['path'],'own_first_check_role_pin',p)
    v={'schema':'EU4-R81-INDEPENDENT-FIRST-FILECHECK/1','passed':True,'subject_manifest':digest(raw),'lookup_roles_pin':digest(rolesraw),'file_count':len(m['files']),'read_events':len(J),'read_bytes':sum(e['bytes'] for e in J),'author_program_PE_engine_decoder_tests_game_native':0,'all_shells_collected':True}
    save('verification.json',v);print(json.dumps(v))


if __name__=='__main__':
    try:
        if sys.argv[1:]==['--check']:check()
        else:need(sys.argv[1:]==[],'review or own first check only');review()
    except BaseException:
        if OUT.exists():
            with (OUT/'failure.json').open('x',encoding='utf-8') as f:json.dump({'traceback':traceback.format_exc(),'read_events':J,'read_bytes':sum(e['bytes'] for e in J),'author_program_actual_not_repeated':True},f,indent=2)
        raise
