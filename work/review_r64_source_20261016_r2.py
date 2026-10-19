"""Non-author source-only audit, using frozen retained text and raw upstream rows."""
from pathlib import Path
import ast
import ctypes
from ctypes import wintypes
import difflib
import hashlib
import json
import struct

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/war-peace-api-20261016-r64-source-independent-review'
SUBJECT='work/reports/war-peace-api-20261016-r64-gold-element-selection/'
OLD='work/reports/war-peace-api-20261016-r63-gold-scalar-source/'
MEMORY=768*1024*1024;LIMIT=24*1024*1024
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
    with (OUT/name).open('xb') as f:f.write(raw)
    guard();return pin(raw)

def main():
    snapshot_path=str((OUT/'retained-source.json').relative_to(ROOT)).replace('\\','/')
    sr=read(snapshot_path);snapshot=json.loads(sr);files=snapshot['files']
    def raw(path):return bytes.fromhex(files[path]['raw_hex'])
    def obj(path):return json.loads(raw(path))
    for path,item in files.items():assert pin(raw(path))=={x:item[x] for x in ('bytes','sha256')}
    m=obj(SUBJECT+'source-manifest.json');seed=obj(SUBJECT+'entry-seed.json');budget=obj(SUBJECT+'budget.json')
    assert m['sealed'] is True and m['entry_rva']=='0x97b8a0'
    assert len(m['actual_source_pins'])==14 and len(m['decoder_expected_witness_pins'])==38
    assert m['source_pins']=={**m['actual_source_pins'],**m['decoder_expected_witness_pins']}
    for path,expected in m['actual_source_pins'].items():assert pin(raw(path))==expected
    oldtext=raw(OLD+'produce.py').decode();newtext=raw(SUBJECT+'produce.py').decode()
    oldast=ast.parse(oldtext);newast=ast.parse(newtext)
    oldfunc={n.name:n for n in oldast.body if isinstance(n,ast.FunctionDef)}
    newfunc={n.name:n for n in newast.body if isinstance(n,ast.FunctionDef)}
    assert set(oldfunc)==set(newfunc) and len(newfunc)==11
    unchanged=[name for name in oldfunc if ast.dump(oldfunc[name],include_attributes=False)==ast.dump(newfunc[name],include_attributes=False)]
    assert len(unchanged)==10 and 'main' not in unchanged
    replacements=[
      ('R63','R64'),('offline97b2c0 scalar-source body','offline97b8a0 element-selection body'),
      ('ENTRY=0x97b2c0','ENTRY=0x97b8a0'),
      ("ORIGIN='work/reports/war-peace-api-20261016-r62-gold-recipient-generator/'","ORIGIN='"+OLD+"'"),
      ("UPSTREAM_SUBJECT={'bytes':14300,'sha256':'d3516fdbc60b2c66115b9a0aa907daace7e5a8adac0c5dbd4c53f0840eba6db4'}",
       "UPSTREAM_SUBJECT={'bytes':14796,'sha256':'965c8f654428410f47ff327a7de28252c9650d8ae02f2f8876560881a6ffdca5'}"),
      ("review.get('call_site_rva')=='0x9844f7'","review.get('call_site_rva')=='0x97b31f'"),
      ("review.get('raw_call')=='e8c46dffff'","review.get('raw_call')=='e87c050000'"),
      ('Full R62 actualreview','Full R63 actualreview'),('Fixed upstreamR62 subjectmanifest','Fixed upstreamR63 subjectmanifest'),
      ("at=0x9844f7;call=bytes.fromhex(retained['raw_hex'])[at-0x9844d0:at-0x9844d0+5]",
       "at=0x97b31f;call=bytes.fromhex(retained['raw_hex'])[at-0x97b2c0:at-0x97b2c0+5]"),
      ("call.hex()=='e8c46dffff'","call.hex()=='e87c050000'"),('Exact retained R62 CALL seed','Exact retained R63 CALL seed'),
      ('all128bits_zero_inherited_from9b4064_no_R62_prefix_XMM_write','copied_stack20_16B_DWORD0_paddingDWORD_unknown_QWORD0'),
      ('InheritedXMM0 precision boundary','Stackpadding/XMM0 precision boundary'),
      ('EU4-R64-SCALAR-SOURCE-STATIC-CAPTURE/1','EU4-R64-ELEMENT-SELECTION-STATIC-CAPTURE/1')]
    normalized=oldtext
    for a,b in replacements:
        assert a in normalized,a
        normalized=normalized.replace(a,b)
    assert normalized==newtext,'Unexpected source bytes beyond explicit target/namespace/seed/precision changes'
    assert ast.dump(ast.parse(normalized),include_attributes=False)==ast.dump(newast,include_attributes=False)
    # The entire real retained caller prefix and postcall selection window are checked against upstream owned bytes.
    capture=obj(OLD+'capture.json');owned=obj(OLD+'owned-code.json');upstream=obj(OLD+'manifest.json')
    assert pin(raw(OLD+'manifest.json'))==m['upstream_R63_subject_manifest']==seed['upstream_R63_manifest']
    code=bytes.fromhex(owned['raw_hex']);assert len(code)==199 and hashlib.sha256(code).hexdigest()==owned['sha256']
    rows=capture['analysis']['instructions'];rm={r['rva']:r for r in rows}
    prefix=seed['R63_entry_to_CALL_raw_rows'];after=seed['R63_postCALL_selection_rows']
    assert len(prefix)==21 and len(after)==6
    assert b''.join(bytes.fromhex(r['bytes']) for r in prefix)==code[:0x64]
    assert b''.join(bytes.fromhex(r['bytes']) for r in after)==code[0x64:0x78]
    for row in prefix+after:assert row==rm[row['rva']]
    call=bytes.fromhex(seed['raw_call']);assert call==code[0x5f:0x64]
    assert 0x97b31f+5+struct.unpack('<i',call[1:])[0]==0x97b8a0 and seed['signed_rel32']==1404
    assert seed['descriptor_raw']['Cpp_class_vtable_identity_proved'] is False
    assert seed['descriptor_raw']['module_pointer_rva']=='0x1c3def0'
    assert seed['descriptor_raw']['QWORDsteady+40']=='0x80'
    assert seed['XMM0_at_call']=='copied_stack20_16B_DWORD0_paddingDWORD_unknown_QWORD0'
    assert seed['callee_XMM_consumption_proved'] is False
    assert rm['0x97b2d2']['bytes']=='488bda' and rm['0x97b31a']['bytes']=='488d542430'
    assert rm['0x97b312']['bytes']=='41b101' and rm['0x97b315']['bytes']=='4c8d442420'
    assert rm['0x97b307']['bytes']=='0f28442420' and rm['0x97b30c']['bytes']=='660f7f442420'
    # No CALL occurs before this target, and no RCX write or selector24..27 initialization is inferred.
    assert all(r['mnemonic']!='call' for r in prefix[:-1])
    assert not any(x in ('rcx','ecx') for r in prefix[:-1] for x in r['registers_written'])
    assert [rm[x]['bytes'] for x in ('0x97b2fe','0x97b302')]==['897c2420','48897c2428']
    # Review ordering and one-scope mechanics are checked as source/AST, never by invoking the program.
    maintext=ast.get_source_segment(newtext,newfunc['main'])
    ordered=["No external address/path override","root_explicit_start_received",'raw_call_entry_seed_only',
        "for label in ('upstream_body_review','source_peer_review')",'Full R63 actualreview',
        'New R64 fullsourcepeer exact subjects required',"PHASE='source_engine_before'",'base,pins=source_guard()',
        "save('claim.json'","stream=(ROOT.parent/'eu4.exe').open('rb')"]
    positions=[maintext.index(x) for x in ordered];assert positions==sorted(positions)
    assert "require(set(group)=={'findings','manifest'}" in maintext
    assert "values.get('subject_source_manifest')==base_pin and values.get('subject_producer')==producer_pin" in maintext
    assert "values.get('subject_entry_seed')==seed_pin" in maintext
    assert "not any((HERE/n).exists() for n in ('claim.json','capture.json','owned-code.json','failure.json','preflight-failure.json'))" in maintext
    for literal in ("kind in ('pdata_record','single_entry_code')",'len(PADATA)<32','len(PADATA)<29',
        "rva==ENTRY and 0<size<=8192",'amount=extent if extent<=8192 else 2048',
        "authenticate('before')","authenticate('after')",'if exact:',
        "if stream is not None:stream.close()","save('capture.json',value)"):
        assert literal in maintext,literal
    assert maintext.index("if stream is not None:stream.close()")<maintext.index("save('capture.json',value)")
    imports=[node for node in ast.walk(newast) if isinstance(node,ast.Import) and any(a.name=='capstone' for a in node.names)]
    exacts=[node for node in ast.walk(newfunc['main']) if isinstance(node,ast.If) and isinstance(node.test,ast.Name) and node.test.id=='exact']
    assert len(imports)==1 and len(exacts)==1 and imports[0] in list(ast.walk(exacts[0]))
    saveopens=[n for n in ast.walk(newfunc['save']) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='open']
    assert len(saveopens)==1 and isinstance(saveopens[0].args[0],ast.Constant) and saveopens[0].args[0].value in ('x','xb')
    # Retained prep files do not need any engine or target opening/import.
    for path in ('prepare.py','check_prepared.py','seal_prepared.py'):
        text=raw(SUBJECT+path).decode();tree=ast.parse(text)
        assert not [n for n in ast.walk(tree) if isinstance(n,ast.Import) and any(a.name in ('capstone','frida') for a in n.names)]
        assert not [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='exec']
    assert budget['pdata_requests_max']==32 and budget['pdata_record_bytes']==12
    assert budget['new_unique_code_bytes_max']==8192 and budget['new_code_read_count_max']==1
    assert budget['producer_explicit_source_engine_IO_budget']==33554432
    assert budget['retained_seal_check_explicit_IO_budget']==16777216 and budget['combined_explicit_source_stage_budget']==50331648
    assert budget['software_committed_memory_guard_bytes']==MEMORY and budget['hard_Job_installed'] is False
    assert budget['single_exclusive_claim'] is True and budget['automatic_retry'] is False
    prep=obj(SUBJECT+'preparation.json');delta=obj(SUBJECT+'preparation-accounting-delta.json');delivery=obj(SUBJECT+'preparation-delivery.json')
    estimate=2*(sum(x['bytes'] for x in m['actual_source_pins'].values())+sum(x['bytes'] for x in m['decoder_expected_witness_pins'].values()))
    assert estimate==prep['source_engine_two_guard_byte_estimate']==16516520
    assert estimate+2097152==prep['estimated_producer_explicit_source_engine_bytes']==18613672<33554432
    assert delta['original_delivery']==pin(raw(SUBJECT+'preparation-delivery.json'))
    assert delta['extra_bytes']==sum(x['bytes'] for x in delta['extra_events_producer_witness'])
    assert delta['corrected_known_accounted_preparation_file_bytes']==delivery['known_accounted_preparation_file_bytes']+delta['extra_bytes']==1611663
    assert delta['corrected_preparation_explicit_upper']==1611663+250000==1861663
    # Re-hash only the same28 prep/upstream text files; no reading a future auth/claim/actual namespace.
    for path,item in files.items():read(path,{x:item[x] for x in ('bytes','sha256')})
    proof=write('source-proof.json',dict(schema='EU4-R64-INDEPENDENT-SOURCE-PROOF/1',sealed=True,
        source_manifest=pin(raw(SUBJECT+'source-manifest.json')),producer=pin(raw(SUBJECT+'produce.py')),
        seed=pin(raw(SUBJECT+'entry-seed.json')),unchanged_function_AST=unchanged,
        changed_function_AST=['main'],exact_whole_source_targeted_replacements=replacements,
        whole_source_bytes_after_targeted_replacements_equal=True,
        textual_delta=''.join(difflib.unified_diff(oldtext.splitlines(True),newtext.splitlines(True),fromfile='sealedR63',tofile='preparedR64')),
        first_gate_positions=positions,first_gate_labels=ordered,
        seed_prefix_rows=21,seed_prefix_bytes=100,postcall_rows=6,postcall_bytes=20,
        raw_CALL='e87c050000',signed_rel32=1404,target_RVA='0x97b8a0',
        RCX='opaque original W',RDX='descriptor steady30, distinct originalout saved RBX',
        R8='selector steady20',R9='onlylowbyte1, upper56unknown',
        XMM0='selector DWORD0, paddingDWORDunknown, QWORD0',
        Cpp_type_enum_currency_unit_or_effect_inferred=False,
        three_gates_before_engine_target=True,exclusive_claim_before_target=True,
        exact_pdata_or_unknown=True,full_8192_or_prefix_2048=True,
        no_external_follow=True,normal_close_before_success_publication=True,
        no_actual_or_author_source_execution=True))
    known=snapshot['source_physical_bytes']+3*len(sr)+sum(x['bytes'] for x in reads)
    # Two inspections and one preliminary review read this same owned snapshot.
    assert known<LIMIT
    findings=dict(schema='EU4-R64-INDEPENDENT-SOURCE-FINDINGS/1',sealed=True,passed=True,
        subject_source_manifest=pin(raw(SUBJECT+'source-manifest.json')),
        subject_producer=pin(raw(SUBJECT+'produce.py')),subject_entry_seed=pin(raw(SUBJECT+'entry-seed.json')),
        entry_rva='0x97b8a0',scope='full_frozen_source_and_budget_peer_review_only_no_actual_authorization',
        blocking_findings=[],author_frozen_source_needs_change=False,source_proof=proof,
        checks=dict(actual_text_pins=14,extra_prep_files=13,source_manifest_pin=1,engine_metadata_pins_unopened=38,
            original_source_prepost_equal=True,ten_acquisition_helpers_exact_AST=True,
            main_only_explicit_namespace_upstream_seed_and_XMM_precision_changes=True,
            all_three_review_gates_precede_engine_target=True,exclusive_claim_precedes_target=True,
            no_external_callee_data_header_vtable_unwind_autofollow=True),
        precision_notes=[
            'This report is a source-peer receipt only. Root still must supply a separately passed raw-entry review, exact fullR63 result review and new explicit actual authorization.',
            'Byte authentication proves selected receipts match, not human authorship/independence. Root must choose nonauthor reviews.',
            'RDX is descriptor, not oldout savedRBX. R9 onlylow8 is1; incoming XMM0 zero does not survive MOVAPS selectorpadding24..27.',
            'Raw selectorDWORD0 is not an established enum0 or currency tag. Descriptor/modulepointer/capacity80 do not certify C++ type, size or allocation.',
            'A nonexact pdata result may still have authenticated engine files earlier, but imports no Capstone/reads0code. It is unknown, not callable rejection.',
            '18,613,672B future source estimate includes a conditional2MiB auth/review allowance, not a universal bound. Actual32MiB charging remains decisive.',
            'Preparation corrected upper1,861,663 includes250,000 manual console allowance, not exact complete OS/loader I/O.',
            'Failure journals/streamNone do not prove complete physical reads or no attempted open. Existing R63 source limits and exception qualifications remain.',
        ],
        preparation_accounting=dict(known=1611663,manual_allowance=250000,upper=1861663,
            future_two_guard_estimate=16516520,extra_auth_reviews_assumption=2097152,future_estimate=18613672),
        independent_resources=dict(known_explicit_data_reads_before_final_seal=known,self_peak=peak,
            source_file_limit=4194304,source_stage_limit=LIMIT,memory_guard=MEMORY,
            not_all_OS_interpreter_or_tool_source_loading_IO=True),
        operations=dict(target_PE_stat_open=0,engine_stat_open_hash_import=0,decoder_import=0,
            author_producer_import_run=0,old_tests=0,game_process_access=0,native_calls=0,
            actual_auth_claim_created_or_read=0),
        authority={x:False for x in ('actual_authorized','native_ready','callable','reader_adoption_allowed',
            'selected_effect_verified','amount_units_verified','recipient_direction_verified','world_lease','atomic_snapshot','authorizes_retry')},
        self_diagnostic='R1 checker wrongly required xb literal; actual source uses equally exclusive x text mode. R1 source/failure preserved; R2 fixes AST mode check/accounting schema key only.',
        all_shells_collected=True,next_scope_auto_authorized=False)
    fp=write('findings.json',findings)
    write('read-accounting.json',dict(schema='EU4-R64-SOURCE-PEER-READS/1',reads=reads,
        initial_retention_bytes=snapshot['source_physical_bytes'],prior_owned_inspection_and_preliminary_review_bytes=3*len(sr),
        known_explicit_data_reads=known,self_peak=peak,budget=LIMIT))
    print(json.dumps(dict(passed=True,findings=fp,source_proof=proof,known_bytes=known,self_peak=peak)))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        write('source-review-r2-failure.json',dict(type=type(exc).__name__,detail=str(exc),reads=reads,self_peak=peak))
        raise
