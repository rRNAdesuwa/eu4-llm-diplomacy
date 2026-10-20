"""R64 non-author retained raw/CFG/integer/alias review. No original execution."""
from pathlib import Path
import ast
import ctypes
from ctypes import wintypes
import hashlib
import json
import struct

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/war-peace-api-20261016-r64-independent-review'
SUBJECT='work/reports/war-peace-api-20261016-r64-gold-element-selection/'
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
M_PIN=dict(bytes=14450,sha256='ac219aa1b6adc947acf64d61dcd56126b370860b02ab7dcff22a1a8000d1fc81')
LIMIT=24*1024*1024;MEMORY=768*1024*1024
reads=[];peak=0
class PMC(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[
        (x,ctypes.c_size_t) for x in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
        'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage',
        'PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE
p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]

def guard():
    global peak
    x=PMC();x.cb=ctypes.sizeof(x)
    assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
    peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage)
    assert peak<=MEMORY

def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def read(path,expected=None):
    assert not path.startswith('work/deps/') and 'eu4.exe' not in path.lower()
    guard();f=ROOT/path;a=f.stat();assert a.st_size<=4*1024*1024
    raw=f.read_bytes();b=f.stat()
    assert len(raw)==a.st_size and(a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)
    if expected is not None:assert pin(raw)==expected,(path,pin(raw),expected)
    reads.append(dict(path=path,**pin(raw)));guard();return raw

def write(name,obj):
    raw=(json.dumps(obj,ensure_ascii=True,indent=2)+'\n').encode()
    assert len(raw)<=4*1024*1024
    with (OUT/name).open('xb') as f:f.write(raw)
    guard();return pin(raw)

def direct_target(row):
    raw=bytes.fromhex(row['bytes']);at=int(row['rva'],16)
    if raw[0] in (0xe8,0xe9):assert len(raw)==5;disp=struct.unpack('<i',raw[1:])[0]
    elif raw[0]==0xeb or 0x70<=raw[0]<=0x7f:assert len(raw)==2;disp=struct.unpack('<b',raw[1:])[0]
    else:assert raw[0]==0x0f and 0x80<=raw[1]<=0x8f and len(raw)==6;disp=struct.unpack('<i',raw[2:])[0]
    return at+len(raw)+disp

def is_store(row):
    raw=bytes.fromhex(row['bytes']);i=0
    while raw[i] in (0x66,0xf2,0xf3) or 0x40<=raw[i]<=0x4f:i+=1
    op=raw[i]
    if op==0x0f:
        second=raw[i+1]
        if second==0x29:return raw[i+2]>>6!=3
        assert second in (0x10,0x1f,0x40,0x4f,0xaf) or 0x80<=second<=0x8f,row
        return False
    if op in (0x89,0xc7,0x01):return raw[i+1]>>6!=3
    if op==0x83:
        modrm=raw[i+1];group=(modrm>>3)&7
        assert group in (0,5,7),row
        return modrm>>6!=3 and group!=7
    if op==0xff:
        group=(raw[i+1]>>3)&7
        assert group in (0,2),row
        return raw[i+1]>>6!=3 and group==0
    assert op in (0x03,0x2b,0x33,0x39,0x3b,0x63,0x84,0x85,0x8b,0x8d,0xb8,0xb9,0xc1,0xc3,0xe8,0xe9,0xeb,0xf7) or 0x50<=op<=0x5f or 0x70<=op<=0x7f,row
    return False

def main():
    sp=str((OUT/'retained-source.json').relative_to(ROOT)).replace('\\','/')
    sr=read(sp);snapshot=json.loads(sr)
    suppraw=read(str((OUT/'supplement-retained.json').relative_to(ROOT)).replace('\\','/'));supp=json.loads(suppraw)
    files={**snapshot['files'],**supp['files']}
    def raw(name):return bytes.fromhex(files[SUBJECT+name]['raw_hex'])
    def obj(name):return json.loads(raw(name))
    for path,item in files.items():assert pin(bytes.fromhex(item['raw_hex']))=={x:item[x] for x in ('bytes','sha256')}
    m=obj('manifest.json');c=obj('capture.json');s=obj('selected-native.json');o=obj('owned-code.json');contract=obj('contract.json')
    assert pin(raw('manifest.json'))==M_PIN and len(m['source_pins'])==38 and len(m['decoder_expected_witness_pins'])==38
    code=bytes.fromhex(o['raw_hex']);assert len(code)==1003 and hashlib.sha256(code).hexdigest()==o['sha256']==s['owned_code_sha256']
    assert o['window']==s['window']==['0x97b8a0','0x97bc8b'] and o['full_extent_owned'] is True
    assert c['game_sha256']==o['game_sha256']==GAME
    rows=s['instructions'];assert len(rows)==266
    cursor=0x97b8a0;rm={};joined=bytearray()
    for row in rows:
        at=int(row['rva'],16);rb=bytes.fromhex(row['bytes'])
        assert at==cursor and 1<=len(rb)<=15
        assert rb==code[at-0x97b8a0:at-0x97b8a0+len(rb)]
        rm[at]=row;joined.extend(rb);cursor+=len(rb)
    assert cursor==0x97bc8b and bytes(joined)==code
    cm={int(x['rva'],16):x for x in c['analysis']['instructions']};assert set(cm)==set(rm)
    for at,row in rm.items():assert all(row[x]==cm[at][x] for x in ('rva','bytes','mnemonic','operands'))
    lines=[x.strip() for x in raw('disassembly.txt').decode().splitlines() if x.strip()]
    assert len(lines)==266
    for line,row in zip(lines,rows):assert line==f"{row['rva']}  {row['bytes']}  {row['mnemonic']} {row['operands']}".strip()
    calls=[r for r in rows if r['mnemonic']=='call'];branches=[r for r in rows if r['mnemonic'].startswith('j')]
    direct=[r for r in calls if bytes.fromhex(r['bytes'])[0]==0xe8];virtual=[r for r in calls if r not in direct]
    assert len(calls)==14 and len(direct)==12 and len(virtual)==2 and len(branches)==35
    assert [r['rva'] for r in virtual]==['0x97b997','0x97ba9b'] and all(r['bytes']=='ff5078' for r in virtual)
    targets={r['rva']:hex(direct_target(r)) for r in direct+branches}
    assert {targets[r['rva']] for r in direct}=={'0x97b8a0','0x1a33310','0x8f4f0','0x1c20d0','0x77e640'}
    assert [r['rva'] for r in direct if targets[r['rva']]=='0x97b8a0']==['0x97b90f']
    assert len(s['edges'])==len(c['analysis']['edges'])==49 and s['edges']==c['analysis']['edges']
    for e in s['edges']:
        r=rm[int(e['site'],16)]
        if r in virtual:assert e['target_rva'] is None and e['target_operand']==r['operands']
        else:
            t=direct_target(r);assert int(e['target_rva'],16)==t==int(r['operands'],16)
            assert e['inside_owned_window'] is (0x97b8a0<=t<0x97bc8b)
        assert e['callee_followed'] is False
        if r['mnemonic']!='jmp':assert int(e['fallthrough'],16)==int(r['rva'],16)+len(bytes.fromhex(r['bytes']))
    successors={}
    for at,r in rm.items():
        nxt=at+len(bytes.fromhex(r['bytes']))
        successors[at]=([] if r['mnemonic']=='ret' else [direct_target(r)] if r['mnemonic']=='jmp' else
            [direct_target(r),nxt] if r['mnemonic'].startswith('j') else [nxt])
        assert all(x in rm for x in successors[at])
    reachable=set();pending=[0x97b8a0]
    while pending:
        at=pending.pop()
        if at not in reachable:reachable.add(at);pending.extend(successors[at])
    assert len(reachable)==266
    assert [r['rva'] for r in rows if r['mnemonic']=='ret']==['0x97bc8a']
    assert not [r for r in rows if r['mnemonic'] in ('int3','ud2','hlt')]
    stores=[r for r in rows if is_store(r)]
    assert len(stores)==11 and [r['rva'] for r in stores]==[r['rva'] for r in s['explicit_store_sites']]
    for a,b in zip(stores,s['explicit_store_sites']):assert a['bytes']==b['raw_hex']
    assert s['store_counts']=={'explicit_sites':11,'stack_sites':4,'P_header_DWORD_sites':4,'P_data_QWORD_sites':3}
    assert [r['rva'] for r in stores]==['0x97b8a0','0x97b8a5','0x97b8b9','0x97b90a','0x97ba04','0x97ba10','0x97bb14','0x97bb24','0x97bbf4','0x97bc00','0x97bc63']
    # Concrete machine anchors independently checked for every major path/width.
    anchors={
      0x97b8b9:'c7421400000000',0x97b8c0:'4d8be8',0x97b8c3:'488bda',0x97b8c6:'4c8bf9',
      0x97b8c9:'4584c9',0x97b8d2:'488b81a8000000',0x97b8d9:'482b81a0000000',
      0x97b8e0:'4883f808',0x97b8e4:'7318',0x97b8e6:'488b81c0000000',0x97b8ed:'482b81b8000000',
      0x97b8f4:'4883f808',0x97b8f8:'0f8232020000',0x97b8fe:'410f1000',
      0x97b902:'4533c9',0x97b905:'4c8d442420',0x97b90a:'0f29442420',0x97b90f:'e88cffffff',
      0x97b914:'4d8ba7a8000000',0x97b928:'492b97a0000000',0x97b92f:'48c1fa03',0x97b933:'035314',
      0x97b936:'3bd7',0x97b93a:'03ff',0x97b943:'0f4ffa',0x97b946:'8bcf',0x97b948:'48f7e1',0x97b94b:'490f40c1',
      0x97b957:'448bc7',0x97b95a:'488bd0',0x97b95d:'488bcb',0x97b965:'4d8ba7a8000000',
      0x97b96c:'4d8bb7a0000000',0x97b973:'49c7c7ffffffff',0x97b989:'498b36',
      0x97b98c:'488d542420',0x97b991:'488bce',0x97b994:'488b06',0x97b997:'ff5078',
      0x97b99a:'488bc8',0x97b99d:'418b4500',0x97b9a1:'3901',0x97b9a5:'4883790800',
      0x97b9ac:'8b4314',0x97b9b2:'8d6801',0x97b9e4:'8b4314',0x97b9eb:'4863c8',0x97b9ee:'4863d5',
      0x97ba00:'488b4308',0x97ba04:'488934c8',0x97ba08:'48ffc1',0x97ba10:'896b14',
      0x97ba13:'4983c608',0x97ba1c:'4c8b7c2470',0x97ba24:'498bafc0000000',0x97ba2e:'4d2b87b8000000',
      0x97ba35:'49c1f803',0x97ba39:'44034314',0x97ba76:'498bafc0000000',0x97ba7d:'498bb7b8000000',
      0x97ba8d:'488b3e',0x97ba90:'488d542420',0x97ba95:'488bcf',0x97ba98:'488b07',0x97ba9b:'ff5078',
      0x97ba9e:'418b4d00',0x97baa2:'3908',0x97baaa:'4883780800',0x97bab1:'448b4314',
      0x97bab5:'33d2',0x97bab7:'33c9',0x97bab9:'4585c0',0x97babe:'4c8b4b08',0x97bac5:'483938',
      0x97baca:'ffc2',0x97bacc:'48ffc1',0x97bad3:'413bd0',0x97bade:'4883f9ff',
      0x97bae4:'488d4101',0x97bae8:'448d5201',0x97baf1:'452bc2',0x97baf4:'498d0cc9',
      0x97baf8:'4d63c0',0x97bafb:'4d8d0cc1',0x97bb04:'4c2bc9',0x97bb10:'498b0409',
      0x97bb14:'488901',0x97bb1b:'4983e801',0x97bb21:'412bd2',0x97bb24:'015314',
      0x97bb30:'4d8b6008',0x97bb3d:'488b81d0000000',0x97bb47:'488b90b0030000',
      0x97bb4e:'482b90a8030000',0x97bb55:'48c1fa03',0x97bb5e:'498b87d0000000',
      0x97bb6c:'4c8bb0a8030000',0x97bb73:'4c8bb8b0030000',0x97bb89:'498b36',0x97bb8c:'4c396630',
      0x97bb98:'8d6801',0x97bbca:'8b4314',0x97bbcd:'49c7c0ffffffff',
      0x97bbd8:'4863c8',0x97bbdb:'4863d5',0x97bbf0:'488b4308',0x97bbf4:'488934c8',0x97bc00:'896b14',
      0x97bc0c:'488b91d8000000',0x97bc13:'482b91d0000000',0x97bc1a:'48b9abaaaaaaaaaaaaaa',
      0x97bc24:'48c1fa03',0x97bc28:'480fafd1',0x97bc34:'418b4500',0x97bc38:'488d0c40',
      0x97bc3c:'498b87d0000000',0x97bc43:'488b3cc8',0x97bc47:'488b74c808',
      0x97bc55:'488b07',0x97bc58:'4c8d442478',0x97bc5d:'8b5314',0x97bc60:'488bcb',
      0x97bc63:'4889442478',0x97bc68:'e8d329e0ff',0x97bc73:'488b9c2480000000',0x97bc8a:'c3'}
    for at,value in anchors.items():assert rm[at]['bytes']==value,hex(at)
    assert sum(r['mnemonic']=='push' for r in rows)==7 and -7*8-0x30==-0x68
    # CMOVO is retained literally. Shown MUL operands are bounded zeroextended32 cap times8.
    for at in (0x97b948,0x97b9c7,0x97ba52,0x97bbad):assert rm[at]['bytes']=='48f7e1'
    assert 8*((1<<32)-1)<(1<<64)
    machine=dict(
      common='DWORD[P+14]=0 before flag or CALL; P/W/F memory may alias and are not typed.',
      high_gate='low8R9!=0 and (u64(Wa8-Wa0)>=8 or u64(Wc0-Wb8)>=8); wrapped pointer differences are not bounds checks',
      self_call='sameW/sameP/&16BcopyF, R9D0; child does not take its local selfCALL; transitive reentry/termination remains unknown',
      A='fresh A begin/end stride8; virtual(E,&stack20) returnsK; load32K==freshF0 and load64(K+8)==0; conditional append E then store newcount',
      B='fresh B begin/end stride8, same virtual filter; signedpositive Pcount scansfirst equalpointer; shift following QWORDsleft; ADD32 count by -1 on ordinary matching index',
      append_count='new=s32(addmod32(oldCount,1)); signed capacity comparisons; oldcount reloaded after growth; signed64fill compares signextended low32 values',
      preallocation='required=s32(low32(sar64(submod64(end,begin),3)+Pcount)); doubledcap=addmod32(cap,cap); signed CMOVG; RCX=u32(chosencap)*8',
      growth='1a33310(RCXbytecount,otherargsunknown) then8f4f0(P,returnedRAX,R8Dcap); no success/type/free/lifetime inferred',
      nonzeroF8='R12=load64(F+8); Q=load64(W+d0), spanQ3a8/3b0; after1c20d0 freshQ/span; compare64(E+30)==savedF8 then append E',
      zeroF8='capacityarg=low64(sar64(submod64(Wd8,Wd0),3)*aaaaaaaaaaaaaaab); after1c20d0 freshI=u32(F0), freshbase=Wd0, begin/end at24I/+8; record+10 unread',
      zeroF8_call='77e640(P,EDXfreshPcount,&stack78QWORDE); R9/XMM/calleeappend/count/alias effects unknown',
      return_value='no uniform RAX assignment on epilogue; source/destination fields and lastcalls/loads leave different values',
      base_layouts='F8 nonzero dereferences Wd0 as Q with3a8/3b0; F8zero uses Wd0 as24Brecordbase. Do not merge into a guessed class.',
      lifetime='normalcallee ABI preserves nonvolatile registers only, not pointed fields; validmemory/alias/loop/exception assumptions remain')
    # Authenticate exact three-review admission/source/auth/claim links using retained pins, not re-executing admission.
    auth=obj('run-authorization.json');claim=obj('claim.json');receipt=obj('acquisition-receipt.json');base=obj('source-manifest.json')
    assert auth['source_manifest']==pin(raw('source-manifest.json')) and auth['producer_pin']==pin(raw('produce.py')) and auth['entry_seed_pin']==pin(raw('entry-seed.json'))
    assert auth['root_explicit_start_received'] is True and auth['seed_review_passed'] is True and auth['automatic_retry'] is False
    assert c['authorization_pin']==pin(raw('run-authorization.json'))==receipt['authorization']
    assert claim['source_manifest']==auth['source_manifest'] and claim['authorization_pin']==c['authorization_pin'] and claim['automatic_retry'] is False
    def declared(path,pn):assert {x:files[path][x] for x in ('bytes','sha256')}==pn
    declared(auth['seed_review_path'],auth['seed_review_pin'])
    rootreview=json.loads(bytes.fromhex(files[auth['seed_review_path']]['raw_hex']))
    assert rootreview['sealed'] is True and rootreview['passed'] is True and rootreview['entry_seed_pin']==auth['entry_seed_pin']
    assert rootreview['entry_rva']=='0x97b8a0' and rootreview['raw_call']=='e87c050000'
    for group in ('upstream_body_review','source_peer_review'):
        for part,pn in auth[group].items():declared(pn['path'],{x:pn[x] for x in ('bytes','sha256')})
        doc=json.loads(bytes.fromhex(files[auth[group]['findings']['path']]['raw_hex']))
        assert doc['sealed'] is True and doc['passed'] is True and doc['blocking_findings']==[]
        if group=='upstream_body_review':assert doc['subject_manifest']==base['upstream_R63_subject_manifest']
        else:
            assert doc['subject_source_manifest']==auth['source_manifest'] and doc['subject_producer']==auth['producer_pin'] and doc['subject_entry_seed']==auth['entry_seed_pin']
    assert c['source_pins']==base['source_pins'] and c['decoder_expected_pins']==m['decoder_expected_witness_pins']
    assert c['source_engine_before_after_equal'] is True and receipt['all_admission_pins_prepost_equal'] is True
    assert sum(e['bytes'] for e in c['source_file_reads'])==16850433
    for phase in ('source_engine_before','source_engine_after'):
        events=[e for e in c['source_file_reads'] if e['phase']==phase]
        for path,expected in base['source_pins'].items():
            matches=[e for e in events if e['path'].replace('\\','/').endswith('/'+path)]
            assert matches and all(e['bytes']==expected['bytes'] for e in matches),(phase,path)
    for name,pn in receipt['source_pins'].items():assert pin(raw(name))==pn
    assert receipt['exit_code']==0 and receipt['direct_owned_child_collected'] is True and receipt['automatic_retry'] is False
    assert receipt['elapsed_ns']==471019100 and receipt['hard_Job_installed'] is False
    assert receipt['stdout']==pin(raw('producer.stdout.json')) and receipt['stderr']==pin(raw('producer.stderr.txt'))
    assert json.loads(raw('producer.stdout.json'))['capture_pin']==pin(raw('capture.json'))
    text=raw('produce.py').decode();tree=ast.parse(text);mainnode=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    maintext=ast.get_source_segment(text,mainnode)
    assert maintext.index("if stream is not None:stream.close()")<maintext.index("save('capture.json',value)")
    assert maintext.index("save('claim.json'")<maintext.index("stream=(ROOT.parent/'eu4.exe').open('rb')")
    # Cached section and pdata/raw/resource replay only, no target file access.
    anchorpath='work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'
    sections=json.loads(bytes.fromhex(files[anchorpath]['raw_hex']))['sections']
    def offset(rva,size):
        for sec in sections:
            start=int(sec['rva'],16)
            if start<=rva and rva+size<=start+sec['raw_size']:return sec['raw_file_offset']+rva-start
        raise AssertionError('unmapped retained address')
    assert offset(0x97b8a0,1003)==o['file_offset']
    pdata=c['pdata_requests'];assert len(pdata)==20 and len({r['index'] for r in pdata})==18
    for r in pdata:
        assert struct.unpack('<III',bytes.fromhex(r['raw_hex']))==tuple(int(r[x],16) for x in ('begin_rva','end_exclusive','unwind_rva'))
        assert offset(int(r['rva'],16),12)==r['file_offset']
    assert c['selected']['index']==19062 and c['selected']['raw_hex']=='a0b897008bbc9700ccc0e701' and c['exact_pdata_begin'] is True
    assert c['pdata_physical_bytes']==240 and c['pdata_unique_bytes']==216
    assert c['total_PE_physical_bytes']==2*38462504+240+1003==76926251
    assert sum(x['bytes'] for x in c['sparse_reads'])==240+1003
    assert [x['bytes'] for x in c['sparse_reads'] if x['kind']=='single_entry_code']==[1003]
    for h in c['full_PE_authentication_reads']:assert h['completed'] is True and h['bytes_read']==38462504 and h['sha256']==GAME
    assert len(c['full_PE_authentication_reads'])==2
    look=c['analysis']['lookahead_inputs'];assert len(look)==266 and sum(r['bytes'] for r in look)==3916
    union=set()
    for r in look:
        at=int(r['rva'],16);assert at in rm and r['bytes']==min(15,0x97bc8b-at)
        union.update(range(at,at+r['bytes']))
    assert len(union)==1003 and 3916-1003==2913
    delivery=obj('delivery-manifest.json');fc=obj('filecheck.json');acc=obj('seal-read-accounting.json')
    for name,pn in delivery['pins'].items():assert pin(raw(name))==pn,name
    assert acc['retained_explicit_bytes_before_filecheck']==1161044+552606+244162==1957812
    assert fc['retained_explicit_upper_before_delivery']==1957812+880861+250000==3088673
    assert delivery['retained_explicit_upper_including_delivery_and_manual_allowance']==3088673+517931==3606604
    assert 16850433+276303==delivery['producer_source_engine_IO_including_final_stdout_capture_pin']==17126736
    assert delivery['combined_explicit_upper']==17126736+3606604==20733340<50331648
    assert c['peak_committed_bytes_observed']==26136576<MEMORY
    assert all(v is False for v in contract['authority'].values())
    assert c['new_header_data_literal_vtable_unwind_callee_bytes']==0
    assert all(c[x]==0 for x in ('game_process_accesses','Frida_operations','native_game_calls','requests','tests'))
    for path,item in files.items():read(path,{x:item[x] for x in ('bytes','sha256')})
    proof=write('raw-replay.json',dict(schema='EU4-R64-INDEPENDENT-RAW-REPLAY/1',sealed=True,
        subject_manifest=M_PIN,rows=rows,owned_bytes=1003,all_raw_bytes_match=True,
        control_targets=targets,virtual_sites=[r['rva'] for r in virtual],virtual_slot='0x78',
        successors={hex(x):[hex(y) for y in ys] for x,ys in successors.items()},
        possible_local_reachable_rows_under_normalCALLreturns=266,RET='0x97bc8a',INT3_count=0,
        explicit_stores=s['explicit_store_sites'],machine_paths=machine,
        selected_anchor_count=len(anchors),growth_MUL64_overflow_fallback_locally_infeasible=True,
        growth_infeasibility_reason='Before each MUL, EAX=8 and ECX=u32(cap); product<=8*(2^32-1)<2^64. CMOVO stays syntactically recorded, not a reachable overflow proof.',
        exact3reviews_auth_and_claim_bound=True,normal_close_before_capture=True,
        no_PE_engine_decoder_program_tests_game_native=True))
    known=snapshot['source_physical_bytes']+supp['source_physical_bytes']+2*len(sr)+sum(x['bytes'] for x in reads)
    assert known<LIMIT
    findings=dict(schema='EU4-R64-INDEPENDENT-FINDINGS/1',sealed=True,passed=True,
        subject_manifest=M_PIN,subject_contract=pin(raw('contract.json')),subject_capture=pin(raw('capture.json')),
        blocking_findings=[],author_frozen_source_needs_change=False,raw_replay=proof,
        checks=dict(actual_source_pins=38,additional_accounting_files=10,engine_metadata_witness_pins_unopened=38,
            full_rows=266,full_owned_bytes=1003,CALL_sites=14,direct_CALL_sites=12,direct_targets=5,
            self_CALL_sites=1,virtual_CALL_sites=2,branches=35,recorded_edges=49,RET_sites=1,INT3_sites=0,
            explicit_stores=dict(stack=4,P_header_DWORD=4,P_data_QWORD=3),
            all_raw_bytes_and_CFG_and_integer_widths_replayed=True,three_review_gate_auth_claim_bound=True,
            source_current_postguard_equal=True),machine_contract=machine,
        precision_notes=[
            'Self-call target is already in owned bytes. Flag0 bypasses that child\'s local self-call only; external reentry/termination are not closed.',
            'Unsigned pointer subtraction gates, signed32 counts/capacity and wrapped arithmetic are raw operations, not bounds or typed container invariants.',
            'MUL/CMOVO(-1) is syntactically present, but cap is zeroextended32 and RAX8 at each MUL, so local unsigned64 overflow fallback is infeasible. No allocator success follows.',
            'A allows duplicate pointers; B removes the first pointer match per encountered B element. Header/data/inputs may alias and transitive calls may mutate fresh-read fields.',
            'Virtual78 returns opaque K; fresh K0/F0 equality and K8zero do not identify enum0, C++ class, currency or recipient.',
            'F8nonzero compares QWORD E30, unlike R63 DWORD E30. F8zero uses unsigned freshF0 with24Brecords; thirdQWORD is unread.',
            '77e640 is only a fixed CALL target with bound selectedGP arguments, not a proven append helper. R9/XMM can be callee-dependent.',
            'No uniformRAX, cardinality1, finaloutT, amountunit, business direction or runtime effect is proved.',
            'Retained3606604/combined20733340 are explicit upper accounts including250000 manual-console allowance, not allOS/loader I/O.',
            'Source/PE/engine/elapsed/peak/child-exit execution facts are authenticated retained witnesses; not re-executed in this review. Failure journals remain incomplete physical-I/O witnesses.',
        ],resource_witness=dict(source_journal=16850433,capture_pin_read=276303,producer_including_pin=17126736,
            retained_upper=3606604,manual_allowance=250000,combined_upper=20733340,
            PE_twoSHA=76925008,pdata_physical=240,pdata_unique=216,code=1003,PE_total=76926251,
            decoder_input_total=3916,decoder_unique=1003,overlap=2913,
            producer_peak=26136576,elapsed_ns=471019100,elapsed_scope=receipt['elapsed_scope'],hard_Job=False,
            collected_owned_child_exit0=True),
        independent_resources=dict(known_explicit_data_reads_before_final_seal=known,source_file_limit=4194304,
            source_budget=LIMIT,self_peak=peak,memory_guard=MEMORY,not_all_OS_tool_source_interpreter_IO=True),
        operations=dict(PE_reads=0,engine_opens=0,decoder_imports=0,author_producer_runs=0,
            old_tests=0,game_process_access=0,Frida=0,native_calls=0,requests=0),
        authority={x:False for x in ('native_ready','callable','reader_adoption_allowed','selected_effect_verified',
            'amount_units_verified','recipient_direction_verified','peace_completion_verified','world_lease','atomic_snapshot','authorizes_retry')},
        self_diagnostic='R1 retained cache lacked verify_actual.py pin present only in delivery; R1 source/failure retained. R2 adds exactly that2749B frozen text supplement and accounting only; author bytes unchanged.',
        all_shells_collected=True,next_scope_auto_authorized=False)
    fp=write('findings.json',findings)
    write('read-accounting.json',dict(schema='EU4-R64-ACTUAL-REVIEW-READS/1',reads=reads,
        initial_retention_bytes=snapshot['source_physical_bytes'],prior_owned_inspection_and_preliminary_review_bytes=2*len(sr),
        known_explicit_data_reads=known,self_peak=peak,budget=LIMIT))
    print(json.dumps(dict(passed=True,findings=fp,raw_replay=proof,known_bytes=known,self_peak=peak)))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        write('review-r2-failure.json',dict(type=type(exc).__name__,detail=str(exc),reads=reads,self_peak=peak))
        raise
