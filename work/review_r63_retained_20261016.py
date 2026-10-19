"""Independent R63 raw-byte, dataflow, CFG and retained-accounting review."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import struct

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/war-peace-api-20261016-r63-independent-review'
SUBJECT='work/reports/war-peace-api-20261016-r63-gold-scalar-source/'
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
SUBJECT_PIN=dict(bytes=14796,sha256='965c8f654428410f47ff327a7de28252c9650d8ae02f2f8876560881a6ffdca5')
MAX_FILE=4*1024*1024;MAX_TOTAL=24*1024*1024;MEMORY=768*1024*1024
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
    guard();file=ROOT/path;a=file.stat();assert a.st_size<=MAX_FILE
    raw=file.read_bytes();b=file.stat()
    assert (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns) and len(raw)==a.st_size
    value=pin(raw)
    if expected is not None:assert value==expected,(path,value,expected)
    reads.append(dict(path=path,**value));guard();return raw

def write(name,obj):
    raw=(json.dumps(obj,ensure_ascii=True,indent=2)+'\n').encode()
    assert len(raw)<=MAX_FILE
    with (OUT/name).open('xb') as f:f.write(raw)
    guard();return pin(raw)

def target(row):
    rva=int(row['rva'],16);raw=bytes.fromhex(row['bytes'])
    if raw[0]==0xe8:
        assert len(raw)==5
        disp=struct.unpack('<i',raw[1:])[0]
    else:
        assert raw[0] in (0x74,0x75,0xeb) and len(raw)==2
        disp=struct.unpack('<b',raw[1:])[0]
    return rva+len(raw)+disp

def explicit_store(row):
    raw=bytes.fromhex(row['bytes']);i=0
    while raw[i] in (0x66,0xf2,0xf3) or 0x40<=raw[i]<=0x4f:i+=1
    op=raw[i]
    if op==0x0f:
        assert raw[i+1] in (0x11,0x28,0x57,0x7f)
        return raw[i+1] in (0x11,0x7f) and raw[i+2]>>6!=3
    if op in (0x89,0xc7):return raw[i+1]>>6!=3
    assert op in (0x33,0x3b,0x57,0x5f,0x74,0x75,0x81,0x83,0x85,0x8b,0x8d,0xb1,0xc3,0xe8,0xeb),row
    return False

def main():
    snapraw=read(str((OUT/'retained-sources.json').relative_to(ROOT)).replace('\\','/'))
    supraw=read(str((OUT/'supplement-retained.json').relative_to(ROOT)).replace('\\','/'))
    snap=json.loads(snapraw);supp=json.loads(supraw);files={**snap['files'],**supp['files']}
    assert len(snap['files'])==41 and len(supp['files'])==9 and len(files)==50
    for path,item in files.items():assert pin(bytes.fromhex(item['raw_hex']))=={x:item[x] for x in ('bytes','sha256')}
    def raw(name):return bytes.fromhex(files[SUBJECT+name]['raw_hex'])
    def obj(name):return json.loads(raw(name))
    m=obj('manifest.json');c=obj('capture.json');s=obj('selected-native.json');o=obj('owned-code.json');contract=obj('contract.json')
    assert pin(raw('manifest.json'))==SUBJECT_PIN
    assert m['sealed'] is True and len(m['source_pins'])==40 and len(m['decoder_expected_witness_pins'])==38
    assert c['game_sha256']==o['game_sha256']==GAME
    code=bytes.fromhex(o['raw_hex']);assert len(code)==199
    assert hashlib.sha256(code).hexdigest()==o['sha256']==s['raw_code_sha256']
    assert o['window']==s['window']==['0x97b2c0','0x97b387'] and o['full_extent_owned'] is True
    rows=s['instructions'];assert len(rows)==49
    cursor=0x97b2c0;rowmap={};joined=bytearray()
    for row in rows:
        site=int(row['rva'],16);rb=bytes.fromhex(row['bytes'])
        assert site==cursor and 1<=len(rb)<=15
        assert rb==code[site-0x97b2c0:site-0x97b2c0+len(rb)]
        rowmap[site]=row;joined.extend(rb);cursor+=len(rb)
    assert cursor==0x97b387 and bytes(joined)==code
    capmap={int(x['rva'],16):x for x in c['analysis']['instructions']}
    assert set(capmap)==set(rowmap)
    for at,row in rowmap.items():assert all(row[x]==capmap[at][x] for x in ('rva','bytes','mnemonic','operands'))
    disasm=[x.strip() for x in raw('disassembly.txt').decode().splitlines() if x.strip()]
    assert len(disasm)==49
    for line,row in zip(disasm,rows):
        expected=f"{row['rva']}  {row['bytes']}  {row['mnemonic']} {row['operands']}".strip()
        assert line==expected,(line,expected)
    calls=[x for x in rows if x['mnemonic']=='call'];branches=[x for x in rows if x['mnemonic'].startswith('j')]
    assert len(calls)==2 and len(branches)==4
    transfer={x['rva']:hex(target(x)) for x in calls+branches}
    assert transfer=={'0x97b31f':'0x97b8a0','0x97b36a':'0x17394f0','0x97b329':'0x97b34b',
        '0x97b349':'0x97b368','0x97b363':'0x97b36f','0x97b368':'0x97b36f'}
    assert len(c['analysis']['edges'])==6 and c['analysis']['edges']==s['edges']
    for edge in c['analysis']['edges']:
        row=rowmap[int(edge['site'],16)]
        assert hex(target(row))==edge['target_rva']==row['operands']
        assert edge['inside_owned_window'] is (0x97b2c0<=target(row)<0x97b387)
        assert edge['callee_followed'] is False
        if row['mnemonic']!='jmp':assert int(edge['fallthrough'],16)==int(row['rva'],16)+len(bytes.fromhex(row['bytes']))
    successors={}
    for at,row in rowmap.items():
        nxt=at+len(bytes.fromhex(row['bytes']))
        successors[at]=([] if row['mnemonic']=='ret' else [target(row)] if row['mnemonic']=='jmp' else
            [target(row),nxt] if row['mnemonic'].startswith('j') else [nxt])
        assert all(x in rowmap for x in successors[at])
    visited=set();pending=[0x97b2c0]
    while pending:
        at=pending.pop()
        if at not in visited:visited.add(at);pending.extend(successors[at])
    assert len(visited)==49 and [x['rva'] for x in rows if x['mnemonic']=='ret']==['0x97b386']
    assert not [x for x in rows if x['mnemonic']=='int3']
    stores=[r for r in rows if explicit_store(r)]
    assert len(stores)==15 and [r['rva'] for r in stores]==[x['rva'] for x in s['manual_explicit_store_sites']]
    for r,x in zip(stores,s['manual_explicit_store_sites']):assert r['bytes']==x['raw_hex']
    stack=[r['rva'] for r in stores if r['memory_operands'][0]['base']=='rsp']
    output=[r['rva'] for r in stores if r['memory_operands'][0]['base']=='rbx']
    assert len(stack)==13 and output==['0x97b336','0x97b34b']
    assert all(r['memory_operands'][0]['base'] in ('rsp','rbx') for r in stores)
    # Full 49-instruction identity for selected machine dataflow, no new decoding.
    expected=['48895c2408','4889742410','57','4881ec50040000','488bda','0f57c0','0f11442430','33ff',
        '48c744244080000000','488d35012c2c01','4889742430','488d442448','4889442438',
        '897c2420','48897c2428','0f28442420','660f7f442420','41b101','4c8d442420','488d542430',
        'e87c050000','837c244401','7520','488b4c2438','488b01','8b5030','8913','4889742430',
        '897c2444','488d442448','483bc8','eb1d','893b','4889742430','897c2444','488d442448',
        '488b4c2438','483bc8','740a','4885c9','7405','e881e1db00','488bc3','4c8d9c2450040000',
        '498b5b10','498b7318','498be3','5f','c3']
    assert [r['bytes'] for r in rows]==expected
    assert 0x97b2e8+7+struct.unpack('<i',bytes.fromhex(rowmap[0x97b2e8]['bytes'])[3:])[0]==0x1c3def0
    # Stack deltas, selector initialized bytes and the first external call ABI.
    steady=-8-0x450;assert steady==-0x458 and (8+steady)%16==0
    initialized=set()
    for r in stores:
        if int(r['rva'],16)>=0x97b307:break
        mem=r['memory_operands'][0]
        if mem['base']=='rsp' and int(r['rva'],16)>0x97b2cb:
            initialized.update(range(mem['displacement'],mem['displacement']+mem['width_bytes']))
    missing=[x for x in range(0x20,0x30) if x not in initialized]
    assert missing==[0x24,0x25,0x26,0x27]
    assert rowmap[0x97b2d8]['memory_operands'][0]['width_bytes']==16
    # The explicit raw MOVUPS store is counted without trusting its missing decoder write flag.
    assert rowmap[0x97b2d8] in stores
    assert not [r for r in rows if int(r['rva'],16)<0x97b31f and
        any(x in ('rcx','ecx','cx','cl') for x in r['registers_written'])]
    assert steady+0x450==-8 and steady+0x450+0x10==8 and steady+0x450+0x18==0x10
    # Count==1: CMP flags survive the unconditional JMP to JE; there is no extra NULL gate.
    assert rowmap[0x97b346]['bytes']=='483bc8' and rowmap[0x97b349]['mnemonic']=='jmp'
    assert target(rowmap[0x97b349])==0x97b368 and rowmap[0x97b368]['mnemonic']=='je'
    # Retained parent CALL/zero-prefix evidence, not a fresh runtime guarantee.
    parentcap=json.loads(bytes.fromhex(files['work/reports/war-peace-api-20261016-r62-gold-recipient-generator/capture.json']['raw_hex']))
    parentmap={int(r['rva'],16):r for r in parentcap['analysis']['instructions']}
    assert target(parentmap[0x9844f7])==0x97b2c0
    assert not [r for at,r in parentmap.items() if at<0x9844f7 and
        any(x.startswith('xmm') for x in r['registers_written'])]
    parentseed=json.loads(bytes.fromhex(files['work/reports/war-peace-api-20261016-r62-gold-recipient-generator/entry-seed.json']['raw_hex']))
    assert any(r['rva']=='0x9b4064' and r['bytes']=='0f57c0' for r in parentseed['minimal_caller_context'])
    # Cached PE section mapping and individual .pdata records only, no PE file open.
    anchor=json.loads(bytes.fromhex(files['work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json']['raw_hex']))
    def fileoff(rva,size):
        for sec in anchor['sections']:
            start=int(sec['rva'],16)
            if start<=rva and rva+size<=start+sec['raw_size']:return sec['raw_file_offset']+rva-start
        raise AssertionError('unmapped retained address')
    assert fileoff(0x97b2c0,199)==o['file_offset']==9938624
    assert len(c['pdata_requests'])==19 and len({x['index'] for x in c['pdata_requests']})==16
    for r in c['pdata_requests']:
        assert struct.unpack('<III',bytes.fromhex(r['raw_hex']))==tuple(int(r[x],16) for x in ('begin_rva','end_exclusive','unwind_rva'))
        assert fileoff(int(r['rva'],16),12)==r['file_offset']
    assert c['selected']['raw_hex']=='c0b2970087b39700b8bfe701' and c['exact_pdata_begin'] is True
    assert c['selected']['index']==19051
    assert c['pdata_physical_bytes']==228 and c['pdata_unique_bytes']==192
    assert c['total_PE_physical_bytes']==2*38462504+228+199==76925435
    assert sum(x['bytes'] for x in c['sparse_reads'])==228+199
    assert [x['bytes'] for x in c['sparse_reads'] if x['kind']=='single_entry_code']==[199]
    for h in c['full_PE_authentication_reads']:assert h['sha256']==GAME and h['completed'] is True and h['bytes_read']==38462504
    assert len(c['full_PE_authentication_reads'])==2
    look=c['analysis']['lookahead_inputs'];assert len(look)==49 and sum(x['bytes'] for x in look)==690
    union=set()
    for r in look:
        at=int(r['rva'],16);assert at in rowmap and r['bytes']==min(15,0x97b387-at)
        union.update(range(at,at+r['bytes']))
    assert len(union)==199 and 690-199==491
    # Frozen source/decoder guards are retained producer witnesses; do not open those engine files.
    base=obj('source-manifest.json')
    assert c['source_pins']==base['source_pins'] and c['decoder_expected_pins']==m['decoder_expected_witness_pins']
    assert c['source_engine_before_after_equal'] is True
    assert sum(x['bytes'] for x in c['source_file_reads'])==c['source_file_read_bytes']==16971754
    for phase in ('source_engine_before','source_engine_after'):
        events=[x for x in c['source_file_reads'] if x['phase']==phase]
        for path,expectedpin in base['source_pins'].items():
            matching=[x for x in events if x['path'].replace('\\','/').endswith('/'+path)]
            assert matching and all(x['bytes']==expectedpin['bytes'] for x in matching),(phase,path)
    receipt=obj('acquisition-receipt.json');stdout=obj('producer.stdout.json')
    assert receipt['exit_code']==0 and receipt['direct_owned_child_collected'] is True
    assert receipt['elapsed_ns']==433912200 and receipt['hard_Job_installed'] is False
    assert receipt['automatic_retry'] is False and receipt['failure_files']==[]
    assert receipt['stdout']==pin(raw('producer.stdout.json')) and receipt['stderr']==pin(raw('producer.stderr.txt'))
    assert stdout['capture_pin']==pin(raw('capture.json'))
    assert receipt['wrapper_explicit_file_read_bytes']==sum(x['bytes'] for x in receipt['wrapper_file_read_journal'])==234214
    accounting=obj('seal-read-accounting.json');fc=obj('filecheck.json');delivery=obj('delivery-manifest.json')
    for name,expectedpin in delivery['pins'].items():assert pin(raw(name))==expectedpin
    assert accounting['retained_explicit_bytes_before_filecheck']==1071065+352970+63016+234214==1721265
    assert fc['retained_accounted_explicit_bytes']==1721265+169061+638928==2529254
    assert fc['retained_upper_including_manual_console_allowance']==2529254+250000==2779254
    assert delivery['retained_explicit_upper_including_delivery_and_manual_allowance']==2779254+194204==2973458
    assert delivery['combined_explicit_upper']==16971754+107151+2973458==20052363
    assert delivery['combined_explicit_upper']<delivery['combined_limit']==50331648
    assert c['peak_committed_bytes_observed']==22822912<MEMORY
    assert all(x is False for x in contract['authority'].values())
    assert all(c[x]==0 for x in ('game_process_accesses','Frida_operations','native_game_calls','requests','tests'))
    assert c['new_header_data_literal_vtable_unwind_callee_bytes']==0
    # Independent postguard on exactly the 50 retained data/control files; no closure expansion.
    for path,item in files.items():read(path,{x:item[x] for x in ('bytes','sha256')})
    rawreview=dict(schema='EU4-R63-INDEPENDENT-RAW-REVIEW/1',sealed=True,
        subject_manifest=SUBJECT_PIN,bytes=199,rows=rows,
        full_raw_match=True,control_targets=transfer,
        successors={hex(x):[hex(y) for y in ys] for x,ys in successors.items()},
        reachable_rows_under_normal_callee_return=49,stack_store_sites=stack,output_store_sites=output,
        initialized_selector_bytes_before_MOVAPS=[hex(x) for x in range(0x20,0x30) if x in initialized],
        uninitialized_selector_bytes=[hex(x) for x in missing],
        XMM0_first_call={'low32':'zero','bits32_63':'uninitialized prior stack bytes','high64':'zero',
            'all128zero_proved':False,'callee_consumption':'unknown'},
        descriptor={'pointer30':'module+1c3def0','data38':'steady+48 beforecall; fresh postcall read',
            'qword40':128,'count44_initial':0,'count44_postcall':'rawDWORD comparedto1'},
        steady_rsp_minus_entryQ=steady,
        output_expression_count1='load32(load64(load64(steady+38))+0x30)',
        output_expression_other='0',return_RAX='original savedout pointer under normalcallee ABI',
        cleanup_count1='same B in RCX != inline =>17394f0; no inserted NULL gate',
        cleanup_other='fresh B != inline and B!=NULL =>17394f0',
        output_final_preserved_through_cleanup=False,all_callee_bodies_followed=False,
        no_new_PE_decoder_engine_game_native=True)
    rp=write('raw-review.json',rawreview)
    ownbytes=snap['source_physical_bytes']+supp['bytes']+supp['owned_snapshot_inspection_bytes']+sum(x['bytes'] for x in reads)
    assert ownbytes<MAX_TOTAL
    findings=dict(schema='EU4-R63-INDEPENDENT-FINDINGS/1',sealed=True,passed=True,
        subject_manifest=SUBJECT_PIN,subject_contract=pin(raw('contract.json')),blocking_findings=[],
        author_frozen_source_needs_change=False,raw_review=rp,
        checks=dict(actual_source_pins=40,additional_accounting_pins=9,engine_witness_pins_unopened=38,
            all49rows_199bytes_match=True,rel32_rel8_targets_recomputed=True,local_normal_CFG=True,
            CALL_sites=2,branch_sites=4,control_transfer_records=6,RET_sites=1,INT3_sites=0,
            explicit_stores=15,stack_stores=13,output_DWORD_stores=2,
            MOVUPS_raw_store_recovered=True,XMM0_padding_unknown_retained=True,
            cached_pdata_section_arithmetic=True,source_and_engine_witness_before_after=True,
            original_files_independent_postguard_equal=True),
        machine_contract=dict(RCX='opaque W forwarded to97b8a0',RDX='savedout DWORD pointer in RBX',
            first_call='97b8a0(W,&descriptor,&raw16selector,R9B=1); high56R9 unknown',
            count1='fresh descriptorDATA->QWORDelement->DWORD+30 ->savedout',
            other='savedoutDWORD=0',RAX='savedout pointer, not scalar',
            final_output_after_cleanup='unknown under unfollowed17394f0 aliases',
            class_units_direction_recipient_amount='unknown'),
        precision_notes=[
            'Incoming/caller XMM0 zero is a conditional retained-prefix fact. Body XORPS zero is later replaced by MOVAPS of a 16B selector with padding24..27 uninitialized.',
            'R9B=1 initializes only eight bits. Firstcall floating/XMM consumption and full prototype remain unknown.',
            'Count1 path dereferences B and E before any NULL/type/fullhandle checks; none are invented by the audit.',
            'CMP flags survive JMP349 to JE368. Count1 cleanup has no extra NULL test; other branch tests fresh B.',
            'All explicit output stores precede optional cleanup. No finalT invariant, pure/readonly/world lifetime or effect follows.',
            '15 explicit store sites omit PUSH/CALL implicit stack writes and RET stack reads.',
            'Retained2973458/combined20052363 are documented explicit upper accounts including250000 manual-console allowance, not exact allOS physical I/O.',
            'Producer source/engine/PE/elapsed/peak execution is retained witness only. This review did not re-open PE or engine or rerun source/decoder.',
        ],
        resource_witness=dict(source_through_capture=16971754,capture_pin_read=107151,
            producer_source_including_stdoutpin=17078905,retained_upper=2973458,
            manual_console_allowance=250000,combined_explicit_upper=20052363,
            PE_twoSHA=76925008,pdata=228,code=199,PE_total=76925435,
            decoder_inputs=690,decoder_unique=199,decoder_overlap=491,
            producer_peak=22822912,elapsed_ns=433912200,elapsed_scope=receipt['elapsed_scope'],
            hard_Job=False,direct_child_collected_exit0=True),
        independent_resources=dict(known_explicit_data_read_bytes_before_own_final_seal=ownbytes,
            source_file_cap=MAX_FILE,source_budget=MAX_TOTAL,self_peak_bytes=peak,memory_guard=MEMORY,
            not_all_OS_interpreter_tool_source_loading_IO=True),
        operations=dict(PE_reads=0,engine_opens=0,decoder_imports=0,author_program_runs=0,
            old_tests=0,game_process_access=0,Frida=0,native_calls=0,requests=0),
        authority={x:False for x in ('callable','native_ready','reader_adoption_allowed','selected_effect_verified',
            'amount_units_verified','recipient_direction_verified','peace_completion_verified','world_lease',
            'atomic_snapshot','authorizes_retry')},all_shells_collected=True,next_scope_auto_authorized=False)
    fp=write('findings.json',findings)
    write('read-accounting.json',dict(schema='EU4-R63-INDEPENDENT-READS/1',reads=reads,
        retained_initial_bytes=snap['source_physical_bytes'],supplement_bytes=supp['bytes'],
        first_owned_inspection_bytes=supp['owned_snapshot_inspection_bytes'],
        current_explicit_bytes=sum(x['bytes'] for x in reads),known_explicit_data_bytes=ownbytes,
        self_peak=peak,source_budget=MAX_TOTAL))
    print(json.dumps(dict(passed=True,findings=fp,raw_review=rp,own_data_bytes=ownbytes,self_peak=peak)))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        write('semantic-review-failure.json',dict(type=type(exc).__name__,detail=str(exc),reads=reads,self_peak=peak))
        raise
