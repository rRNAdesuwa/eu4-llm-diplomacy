"""R89 fixed direct-CALL prefix. Source-only; no actual grant exists."""
import ctypes
from ctypes import wintypes
import hashlib,json,struct,sys,types,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ENTRY=0xc9d60
R87='work/reports/war-peace-api-20261016-r87-dual-frontier-source/'
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
GAME_BYTES=38462504
ANCHORS='work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'
TARGET_CONTEXT_NORMAL_EXIT=False
SOURCE_LIMIT=30*1024*1024
MEMORY_LIMIT=768*1024*1024
SOURCE_IO=[]
PHASE='authorization_preflight'
PE_READS=[]
PE_AUTH=[]
PADATA=[]
MAX_OBSERVED_COMMIT=0
CFG_PIN={'bytes': 5317, 'sha256': '5f0b566a36b7a765c895dd0068941ab828e82d34c088fc33250d6083b9d43252'}
CONTRACT_PIN={'bytes': 7777, 'sha256': '824eba3705c3bd0b7f33917f40c6bfc34de9de31e1093115e3ad47ceab7f1e67'}

META_PIN={'bytes': 4120, 'sha256': 'ea32c610a8b578911eb2c8696535b3becf3db20d86977d91bc2463f8b563b4d0'}

def require(ok,message):
    if not ok:raise ValueError(message)

def save(name,value):
    text=json.dumps(value,indent=2)+'\n'
    require(len(text.encode('utf8'))<=4*1024*1024,'Retained output exceeds4MiB')
    with (HERE/name).open('x',encoding='utf8',newline='\n') as stream:
        stream.write(text)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def charge(n):
    require(type(n) is int and n>=0 and sum(e['bytes'] for e in SOURCE_IO)+n<=SOURCE_LIMIT,'Producer explicit source/engine IO exceeds32MiB')

def read_source(path):
    path=path.resolve();require(path.is_relative_to(ROOT),'Project-local text source only')
    require(not path.is_relative_to((ROOT/'work/deps').resolve()),'Engine is streaming-pin only, not text source')
    st=path.stat();require(0<st.st_size<=4*1024*1024,'Ordinary source exceeds4MiB')
    charge(st.st_size+1)
    with path.open('rb') as f:raw=f.read(st.st_size+1)
    SOURCE_IO.append({'phase':PHASE,'operation':'read','path':str(path),'bytes':len(raw)})
    post=path.stat();require(len(raw)==st.st_size==post.st_size and post.st_mtime_ns==st.st_mtime_ns,'Source changed or short')
    return raw

def stream_pin(path):
    path=path.resolve();require(path.is_relative_to(ROOT),'Project-local fixed source/engine pin only')
    engine=path.is_relative_to((ROOT/'work/deps/capstone-5.0.7').resolve())
    maximum=8*1024*1024 if engine and path.name=='capstone.dll' else 4*1024*1024
    before=path.stat();require(0<before.st_size<=maximum,'Source/locked-engine bound')
    charge(before.st_size);h=hashlib.sha256();total=0
    with path.open('rb') as f:
        while block:=f.read(min(1024*1024,maximum-total+1)):
            total+=len(block);require(total<=maximum,'Source grew');h.update(block)
            if MAX_OBSERVED_COMMIT:memory_guard()
    after=path.stat();require(total==before.st_size==after.st_size and after.st_mtime_ns==before.st_mtime_ns,'Source changed while pinning')
    SOURCE_IO.append({'phase':PHASE,'operation':'streaming_engine_pin' if engine else 'streaming_pin','path':str(path),'bytes':total})
    return {'bytes':total,'sha256':h.hexdigest()}

def memory_guard():
    """Only this Python process; no target/process-enumeration API."""
    global MAX_OBSERVED_COMMIT
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in (
          'peak_working','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype=wintypes.BOOL
    c=Counters();c.cb=ctypes.sizeof(c)
    require(bool(psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(c),c.cb)),'Own committed memory unavailable')
    observed=max(int(c.private),int(c.peak_pagefile));MAX_OBSERVED_COMMIT=max(MAX_OBSERVED_COMMIT,observed)
    require(observed<1024*1024*1024,'OneGiB own-process hard stop')
    require(0<observed<=MEMORY_LIMIT,'Own-process768MiB software guard')
    return MAX_OBSERVED_COMMIT

def source_guard(expected_manifest_pin):
    raw_manifest=read_source(HERE/'source-manifest.json')
    require({'bytes':len(raw_manifest),'sha256':digest(raw_manifest)}==expected_manifest_pin,
      'Authorized source manifest buffer differs before parsing or engine selection')
    manifest=json.loads(raw_manifest)
    require(manifest['sealed'] is True and manifest['entry_rva']==hex(ENTRY),'Exact sealed source-budget manifest required')
    pins=manifest['source_pins']
    require(len(manifest['decoder_expected_witness_pins'])==38,'Locked decoder metadata count')
    for name,expected in pins.items():require(stream_pin(ROOT/name)==expected,'Source/engine differs: '+name)
    return manifest,pins

def raw_write_review(raw):
    p=0
    while p<len(raw) and (raw[p] in (0x26,0x2e,0x36,0x3e,0x64,0x65,0x66,0x67,0xf0,0xf2,0xf3) or 0x40<=raw[p]<=0x4f):p+=1
    value={'raw_hex':raw.hex(),'status':'unclassified_requires_manual_review','explicit_memory_write':None,'not_a_no_write_proof':True}
    if p==len(raw):return value
    op=raw[p];n=2 if op==0x0f and p+1<len(raw) else 1;code=raw[p:p+n];value['opcode_hex']=code.hex()
    if op in (0xa4,0xa5,0xaa,0xab):
        value.update(status='implicit_string_destination',implicit_memory_write=True);return value
    destination=code in (b'\x88',b'\x89',b'\xc6',b'\xc7',b'\x01',b'\x09',b'\x11',b'\x19',b'\x21',b'\x29',b'\x31',b'\x0f\x11',b'\x0f\x29',b'\x0f\x7f')
    if p+n<len(raw) and (destination or op in (0x80,0x81,0x83,0xff,0xf6,0xf7)):
        modrm=raw[p+n];mod=modrm>>6;group=(modrm>>3)&7
        write=destination or op in (0x80,0x81,0x83) and group!=7 or op==0xff and group in (0,1) or op in (0xf6,0xf7) and group in (2,3)
        value.update(modrm_hex=hex(modrm),mod=mod,group=group,
          status='recognized_memory_destination_write' if write and mod!=3 else 'recognized_register_or_no_destination_form',
          explicit_memory_write=bool(write and mod!=3))
    return value

def cfg(raw,begin,cs):
    require(begin==0xc9d60 and len(raw)==256,'Exact raw single-seed window')
    core_raw=read_source(HERE/'cfg_core.py')
    require({'bytes':len(core_raw),'sha256':digest(core_raw)}==CFG_PIN,'Pinned worklist source before compile')
    module=types.ModuleType('_r89_cfg');module.__file__=str(HERE/'cfg_core.py')
    exec(compile(core_raw,module.__file__,'exec'),module.__dict__)
    engine=cs.Cs(cs.CS_ARCH_X86,cs.CS_MODE_64);engine.detail=True
    def decode_one(chunk,cursor):
        insn=next(engine.disasm(chunk,cursor,count=1),None)
        if insn is None:return None
        read,write=insn.regs_access();mem=[];imm=[]
        for op in insn.operands:
            if op.type==cs.x86.X86_OP_MEM:
                m=op.mem;mem.append({'base':insn.reg_name(m.base),'index':insn.reg_name(m.index),'scale':m.scale,
                  'displacement':m.disp,'segment':insn.reg_name(m.segment),'width_bytes':op.size,
                  'read':bool(op.access&cs.CS_AC_READ),'write':bool(op.access&cs.CS_AC_WRITE),
                  'rip_target_rva':hex(cursor+insn.size+m.disp) if m.base==cs.x86.X86_REG_RIP else None})
            elif op.type==cs.x86.X86_OP_IMM:imm.append(op.imm)
        row={'rva':hex(cursor),'bytes':insn.bytes.hex(),'mnemonic':insn.mnemonic,'operands':insn.op_str,
          'registers_read':[insn.reg_name(x) for x in read],'registers_written':[insn.reg_name(x) for x in write],
          'memory_operands':mem,'immediates':imm,'raw_memory_write_review':raw_write_review(bytes(insn.bytes))}
        call=insn.group(cs.CS_GRP_CALL);jump=insn.group(cs.CS_GRP_JUMP) or insn.mnemonic.startswith('loop')
        direct=bool(insn.operands) and insn.operands[0].type==cs.x86.X86_OP_IMM
        target=insn.operands[0].imm if direct else None
        kind='ret' if insn.group(cs.CS_GRP_RET) else ('abnormal' if insn.mnemonic in ('int3','ud2','hlt','int','iret','iretq') else ('call' if call else ('jump' if jump else 'ordinary')))
        return row,{'kind':kind,'target':target,'unconditional':kind=='jump' and insn.mnemonic=='jmp'}
    return module.run_cfg(raw,decode_one,memory_guard)

def main():
    global PHASE,TARGET_CONTEXT_NORMAL_EXIT
    require(len(sys.argv)==2 and re.fullmatch('[0-9a-f]{64}',sys.argv[1]),'Only exact future R89 grant SHA argument')
    require(not any((HERE/n).exists() for n in ('claim.json','capture.json','owned-code.json','failure.json')),'Static attempt already exists')
    auth_raw=read_source(HERE/'run-authorization.json')
    require(digest(auth_raw)==sys.argv[1],'Root grant raw SHA before any parse')
    runtime_raw=read_source(HERE/'runtime_contract.py')
    require({'bytes':len(runtime_raw),'sha256':digest(runtime_raw)}==CONTRACT_PIN,'Fixed runtime contract source')
    runtime=types.ModuleType('_r89_runtime');runtime.__file__=str(HERE/'runtime_contract.py')
    exec(compile(runtime_raw,runtime.__file__,'exec'),runtime.__dict__)
    state=runtime.verify(read_source,sys.argv[1]);base_pin=state['manifest_pin']
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.IsProcessInJob.argtypes=[wintypes.HANDLE,wintypes.HANDLE,ctypes.POINTER(wintypes.BOOL)]
    kernel.IsProcessInJob.restype=wintypes.BOOL
    in_job=wintypes.BOOL()
    require(kernel.IsProcessInJob(kernel.GetCurrentProcess(),None,ctypes.byref(in_job)) and in_job.value,'Reviewed hard-Job launcher required')
    require(stream_pin(HERE/'source-manifest.json')==base_pin,'Manifest outer before guard')
    PHASE='source_engine_before';base,pins=source_guard(base_pin)
    require(stream_pin(HERE/'source-manifest.json')==base_pin,'Manifest outer after guard')
    require(base['fixed_raw_window']==runtime.WINDOW,'No raw window override')
    seed=runtime.decode(state['data'][(HERE/'entry-seed.json').relative_to(ROOT).as_posix()])
    require(seed['fixed_raw_window']==runtime.WINDOW and seed['metadata_policy']==state['build']['metadata_policy']
      and seed['gap_policy']==state['build']['gap_policy'],'Fixed diagnostic-only policy')
    old=runtime.decode(state['data'][R87+'capture.json'])
    owned87=runtime.decode(state['data'][R87+'owned-code.json']);raw87=bytes.fromhex(owned87['raw_hex'])
    sites=[v for v in old['analysis']['instructions'] if v['rva']=='0xcc305']
    require(len(sites)==1 and sites[0]['bytes']=='e856daffff','Unique retained direct CALL row')
    require(raw87[0x9f:0xa4].hex()=='e856daffff' and 0xcc30a+struct.unpack('<i',raw87[0xa0:0xa4])[0]==ENTRY,'Exact owned direct CALL target')
    cached=runtime.decode(state['data'][ANCHORS]);sections=cached['sections']
    require(cached['game_sha256']==GAME and cached['game_bytes']==GAME_BYTES,'Cached section identity')
    pdata_sections=[s for s in sections if s['name']=='.pdata'];require(len(pdata_sections)==1,'Unique cached pdata section')
    pdata=pdata_sections[0];prva=int(pdata['rva'],16);pbytes=pdata['virtual_size']
    def mapping(rva,size,name):
        require(type(rva)is int and type(size)is int and rva>=0 and size>0,'Exact raw span')
        matches=[s for s in sections if int(s['rva'],16)<=rva and rva+size<=int(s['rva'],16)+s['raw_size']]
        if len(matches)!=1 or matches[0]['name']!=name:return None
        where=matches[0]['raw_file_offset']+rva-int(matches[0]['rva'],16)
        return where if 0<=where<=GAME_BYTES-size else None
    cached_valid=(type(pbytes)is int and pbytes>0 and pbytes%12==0 and mapping(prva,pbytes,'.pdata')is not None)
    meta_raw=read_source(HERE/'metadata_core.py')
    require({'bytes':len(meta_raw),'sha256':digest(meta_raw)}==META_PIN,'Diagnostic metadata source before compile')
    meta=types.ModuleType('_r89_metadata');meta.__file__=str(HERE/'metadata_core.py')
    exec(compile(meta_raw,meta.__file__,'exec'),meta.__dict__)
    require(meta.ENTRY==ENTRY and meta.WINDOW==runtime.WINDOW,'No diagnostic entry override')
    save('claim.json',{'schema':'EU4-R89-STATIC-EXCLUSIVE-CLAIM/1','fixed_raw_window':runtime.WINDOW,
      'source_manifest':base_pin,'authorization_pin':state['auth_pin'],'source_pins':pins,
      'review_pins':state['review_pins'],'automatic_retry':False,'producer_source_limit':SOURCE_LIMIT})
    owned=analysis=diagnostic=None;decoder_loaded=False;valid=False;issues=[]
    PHASE='target_before_authentication'
    with (ROOT.parent/'eu4.exe').open('rb') as target:
        def authenticate(phase):
            target.seek(0);h=hashlib.sha256();count=0
            event={'phase':phase,'bytes_read':0,'completed':False,'sha256':None};PE_AUTH.append(event)
            while block:=target.read(1024*1024):
                count+=len(block);event['bytes_read']=count;require(count<=GAME_BYTES,'Target grew');h.update(block);memory_guard()
            require(count==GAME_BYTES and h.hexdigest()==GAME,'Fixed complete EXE identity')
            event.update(completed=True,sha256=h.hexdigest())
        def diagnostic_record(index,reason):
            require(cached_valid and type(index)is int and 0<=index<pbytes//12 and len(PADATA)<32,'At most32 bounded metadata records')
            rva=prva+12*index;where=mapping(rva,12,'.pdata')
            event={'kind':'diagnostic_pdata_record','reason':reason,'index':index,'rva':hex(rva),
              'file_offset':where,'requested_bytes':12,'bytes':0,'complete':False}
            PE_READS.append(event);PADATA.append(event)
            if where is None:return None
            target.seek(where);value=target.read(12);event.update(bytes=len(value),complete=len(value)==12);memory_guard();return value
        authenticate('before');PHASE='bounded_diagnostic_metadata'
        if cached_valid:
            diagnostic=meta.diagnose(diagnostic_record,pbytes//12,memory_guard)
            valid=diagnostic['metadata_valid'];issues=list(diagnostic['issues'])
        else:
            issues=['cached_pdata_mapping_or_count_invalid']
        if mapping(ENTRY,256,'.text') is None:issues.append('fixed_raw_mapping_invalid')
        valid=valid and not issues
        if valid:
            PHASE='one_fixed_raw_window';where=mapping(ENTRY,256,'.text')
            event={'kind':'fixed_single_seed_window','rva':hex(ENTRY),'file_offset':where,'requested_bytes':256,'bytes':0,'complete':False}
            PE_READS.append(event);target.seek(where);raw=target.read(256);event.update(bytes=len(raw),complete=len(raw)==256)
            require(len(raw)==256,'Short fixed code read');memory_guard()
            owned={'schema':'EU4-R89-FIXED-OWNED-WINDOW/1','game_sha256':GAME,'fixed_raw_window':runtime.WINDOW,
              'file_offset':where,'raw_hex':raw.hex(),'bytes':256,'sha256':digest(raw),
              'is_function_extent':False,'metadata_classification':diagnostic['classification'],
              'function_metadata_unknown':diagnostic['function_metadata_unknown'],'source_manifest':base_pin}
            save('owned-code.json',owned)
            PHASE='locked_decoder_on_owned_bytes';depdir=ROOT/'work/deps/capstone-5.0.7'
            sys.path.insert(0,str(depdir));import capstone
            require(capstone.__version__=='5.0.7' and Path(capstone.__file__).resolve().is_relative_to(depdir.resolve()),'Locked decoder')
            decoder_loaded=True;analysis=cfg(raw,ENTRY,capstone)
            require(analysis['decoded_unique_bytes']<=256 and analysis['decoder_input_total_bytes']<=3840,'Unique/lookahead budgets')
        authenticate('after')
    TARGET_CONTEXT_NORMAL_EXIT=True;PHASE='source_engine_after'
    _,post=source_guard(base_pin);after=runtime.verify(read_source,sys.argv[1])
    require(post==pins and after['manifest_pin']==base_pin and after['auth_pin']==state['auth_pin']
      and after['review_pins']==state['review_pins'] and stream_pin(HERE/'source-manifest.json')==base_pin,'Final source/engine/review/auth guards')
    own_pin=stream_pin(HERE/'owned-code.json') if owned else None;peak=memory_guard()
    value={'schema':'EU4-R89-FIXED-SINGLE-SEED-CAPTURE/1','evidence_kind':'ordinary_locked_Capstone_not_REA_EvidenceID',
      'game_sha256':GAME,'game_bytes':GAME_BYTES,'fixed_raw_window':runtime.WINDOW,'source_manifest':base_pin,
      'seed_semantics':runtime.SEED_SEMANTICS,'authorization_pin':state['auth_pin'],'review_pins':state['review_pins'],'source_pins':pins,
      'diagnostic_metadata':diagnostic,'metadata_physical_bytes':sum(x['bytes'] for x in PE_READS if x['kind']=='diagnostic_pdata_record'),
      'metadata_issues':issues,'metadata_valid':valid,'code_extent_selected_from_metadata':False,
      'owned_code_pin':own_pin,'decoder_loaded':decoder_loaded,'analysis':analysis,
      'status':'fixed_direct_call_prefix_static_capture' if valid else 'unknown_metadata_or_fixed_mapping0code',
      'source_file_reads':list(SOURCE_IO),'source_file_read_bytes':sum(x['bytes'] for x in SOURCE_IO),
      'source_limit':SOURCE_LIMIT,'parent_control_reserved_bytes':2*1024*1024,
      'sparse_reads':PE_READS,'full_PE_authentication_reads':PE_AUTH,
      'total_PE_physical_bytes':sum(x['bytes_read'] for x in PE_AUTH)+sum(x['bytes'] for x in PE_READS),
      'source_engine_before_after_equal':True,'normal_target_context_exit':True,'commit_after_target_close_and_final_guards':True,
      'own_process_job_membership_observed':True,'hard_Job_limits_verified_here':False,'hard_Job_limits_require_launcher_receipt':True,
      'peak_committed_bytes_observed':peak,'decoder_expected_witness_pins':base['decoder_expected_witness_pins'],
      'game_process_accesses':0,'Frida_operations':0,'native_game_calls':0,'requests':0,'tests':0,
      'native_ready':False,'callable':False,'reader_adoption_allowed':False,'selected_effect_verified':False,
      'world_lease':False,'atomic_snapshot':False,'authorizes_retry':False,'further_actual_authorized':False}
    save('capture.json',value)
    print(json.dumps({'status':value['status'],'fixed_raw_window':runtime.WINDOW,
      'code_bytes':256 if owned else 0,'rows':analysis['instruction_count'] if analysis else 0,'native_ready':False}))

if __name__=='__main__':
    try:main()
    except BaseException as exc:
        if not(HERE/'failure.json').exists():
            save('failure.json',{'schema':'EU4-R89-STATIC-FAILURE/1','phase':PHASE,'type':type(exc).__name__,
              'message':str(exc),'source_completed_reads':list(SOURCE_IO),'sparse_reads':PE_READS,
              'target_authentication_reads':PE_AUTH,'normal_target_context_exit':TARGET_CONTEXT_NORMAL_EXIT,
              'partial_failure_IO_not_complete':True,'automatic_retry':False,'native_ready':False})
        raise
