"""R75 retained raw-entry audit. Never imports or executes an author producer."""
import ast
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import struct
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
SUB = 'work/reports/war-peace-api-20261016-r75-null-successor-fragment/'
UP = 'work/reports/war-peace-api-20261016-r69-generator-divisor-source/'
REV = 'work/reports/war-peace-api-20261016-r69-actual-independent-review/'
PRO = 'work/reports/war-peace-api-20261016-r75-null-successor-proposal/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r75-entry-independent-review'
GAME = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
EXPECTED = {
    SUB+'source-manifest.json': {'bytes':22012,'sha256':'5e44ed379c98638b701d89d2c6e4d24ae991f0fd16c3f9c94d0a9e77a45fe2e6'},
    SUB+'produce.py': {'bytes':24926,'sha256':'f2f620d849526ad639303436d70d82d4dede5c6372556d0a50aff06873253f0f'},
    SUB+'entry-seed.json': {'bytes':12644,'sha256':'9a2d0ff680202f537998dd786a6b77401eb50532d16ddec1ff04f14ff01bfba1'},
    SUB+'final-manifest.json': {'bytes':13372,'sha256':'940d0b5ff95760cf79e0391a70bc778e60ed758590886670141574fba05d1aeb'},
}
JOURNAL = []
PEAK = 0
MANUAL_ALLOWANCE = 512*1024

def require(ok, message):
    if not ok:
        raise AssertionError(message)

class PMC(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
              ('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),
              ('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),
              ('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),
              ('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]

def guard():
    global PEAK
    info=PMC(); info.cb=ctypes.sizeof(info)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    psapi=ctypes.WinDLL('psapi',use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
    require(psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(info),info.cb),'self memory guard')
    PEAK=max(PEAK,info.PeakPagefileUsage)
    require(info.PagefileUsage<=768*1024*1024 and PEAK<=1024*1024*1024,'self memory budget')
    require(sum(x['bytes'] for x in JOURNAL)+MANUAL_ALLOWANCE<=8*1024*1024,'audit read budget')

def pin(raw):
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def pairs(items):
    result={}
    for key,value in items:
        require(key not in result,'duplicate JSON key')
        result[key]=value
    return result

def parse(raw):
    return json.loads(raw.decode('utf8'),object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))

def read(path, expected=None, phase='before'):
    require(path.startswith('work/reports/') or path=='work/review_r75_entry_20261016.py','admitted text only')
    require('work/deps/' not in path and not path.lower().endswith(('.exe','.dll')),'no binary/engine access')
    p=ROOT/path
    require(p.stat().st_size<=4*1024*1024,'ordinary file limit')
    raw=p.read_bytes()
    JOURNAL.append({'phase':phase,'path':path,'bytes':len(raw)})
    guard()
    if expected is not None:
        require(pin(raw)==expected,'pin differs: '+path)
    return raw

def write(name, value):
    raw=(json.dumps(value,indent=2,ensure_ascii=True)+'\n').encode('utf8')
    with (OUT/name).open('xb') as f:
        f.write(raw)
    return pin(raw)

def audit():
    OUT.mkdir(exist_ok=False)
    (OUT/'inspection-filename-diagnostic.txt').write_text(
        'Prior ad-hoc inspection used preparation-final-manifest.json instead of actual final-manifest.json.\n'
        'FileNotFoundError; no author code executed, no PE/decoder access, no author changes.\n'
        'Completed manual text reads conservatively charged within 512KiB allowance.\n',encoding='utf8')
    raw={path:read(path,expected) for path,expected in EXPECTED.items()}
    final=parse(raw[SUB+'final-manifest.json'])
    base=parse(raw[SUB+'source-manifest.json'])
    require(final['sealed'] is True and base['sealed'] is True,'prepared manifests sealed')
    require(final['source_manifest_pin']==EXPECTED[SUB+'source-manifest.json'],'base subject')
    require(final['actual_authorized'] is False and base['actual_authorized'] is False,'no actual grant')
    admitted=[SUB+'PROTOCOL.md',SUB+'budget.json',UP+'manifest.json',UP+'capture.json',
              UP+'owned-code.json',UP+'selected-evidence.json',UP+'contract.json',
              REV+'findings.json',REV+'manifest.json',
              'work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json',
              PRO+'manifest.json',PRO+'proposal.json',PRO+'selected-seed.json']
    for path in admitted:
        require(path in final['source_pins'],'flat final pin missing')
        raw[path]=read(path,final['source_pins'][path])
    pins={path:pin(data) for path,data in raw.items()}
    for path in base['actual_source_pins']:
        if path in pins:
            require(base['actual_source_pins'][path]==pins[path],'base/final subset conflict')
    seed=parse(raw[SUB+'entry-seed.json'])
    cap=parse(raw[UP+'capture.json'])
    owned=parse(raw[UP+'owned-code.json'])
    selected=parse(raw[UP+'selected-evidence.json'])
    accepted=parse(raw[REV+'findings.json'])
    anchors=parse(raw['work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'])
    require(accepted['sealed'] is True and accepted['passed'] is True and accepted['blocking_findings']==[],'upstream review')
    require(accepted['subject_manifest']==pins[UP+'manifest.json'] and accepted['subject_capture']==pins[UP+'capture.json']
            and accepted['subject_contract']==pins[UP+'contract.json'],'upstream review subjects')
    require(seed['upstream_capture_pin']==pins[UP+'capture.json'] and seed['upstream_manifest_pin']==pins[UP+'manifest.json'],'seed upstream pins')
    for data in (base,seed,cap,owned,selected,anchors):
        require(data['game_sha256']==GAME,'same fixed PE identity witness')
    code=bytes.fromhex(owned['raw_hex'])
    require(len(code)==55 and owned['window']==['0x993570','0x9935a7'],'owned prefix span')
    require(hashlib.sha256(code).hexdigest()==owned['sha256'],'owned code hash')
    require(selected['raw_hex']==owned['raw_hex'] and selected['raw_sha256']==owned['sha256'],'selected owned bytes')
    rows=selected['instructions']
    require(rows==cap['analysis']['instructions'] and len(rows)==18,'capture selected 18 rows exact')
    cursor=0x993570
    for row in rows:
        data=bytes.fromhex(row['bytes']); address=int(row['rva'],16)
        require(address==cursor and code[address-0x993570:address-0x993570+len(data)]==data,'row raw slice')
        cursor+=len(data)
    require(cursor==0x9935a7,'all55B row coverage')
    prefix=[r for r in rows if int(r['rva'],16)<=0x993595]
    require(prefix==seed['retained_prefix_rows'] and len(prefix)==15,'seed exact15 retained rows')
    require(sum(len(bytes.fromhex(r['bytes'])) for r in prefix)==seed['retained_prefix_bytes']==43,'seed43B')
    by={r['rva']:r for r in rows}
    require(by['0x993595']==seed['source_branch'],'branch exact row')
    branch=bytes.fromhex(seed['source_branch']['bytes'])
    require(branch.hex()=='0f84bd000000' and branch[:2]==b'\x0f\x84','nearJE opcode')
    displacement=struct.unpack('<i',branch[2:])[0]
    target=0x993595+len(branch)+displacement
    require(displacement==189 and target==0x993658 and seed['computed_target']==hex(target),'signed rel32 JE')
    require(by['0x99358f']['bytes']=='4c8be0' and by['0x993592']['bytes']=='4885c0','MOVR12/RAX then TEST64')
    require([r['bytes'] for r in rows[:6]]==['4055','56','4154','4155','4156','4883ec30'],'fivepush/sub30')
    require(by['0x99357d']['bytes']=='33f6' and by['0x99357f']['bytes']=='498be8'
            and by['0x993582']['bytes']=='8932' and by['0x993584']['bytes']=='4c8bf2'
            and by['0x993587']['bytes']=='4c8be9','precall state raw')
    call=bytes.fromhex(by['0x99358a']['bytes'])
    require(call.hex()=='e8a187feff' and 0x99358a+5+struct.unpack('<i',call[1:])[0]==0x97bd30,'opaque prior call')
    require([r['bytes'] for r in rows[15:]]==['4d8b4578','4d2b4570','49c1f803'],'nonnull suffix skipped')
    requests=cap['pdata_requests']
    previous=requests[14]; following=requests[13]
    require(seed['previous_retained']=={'capture_pointer':'/pdata_requests/14',**previous},'previous exact cached record')
    require(seed['next_retained']=={'capture_pointer':'/pdata_requests/13',**following},'following exact cached record')
    require(previous['index']==19162 and following['index']==19164,'adjacent indices')
    require(previous['raw_hex']=='433699005836990024dde701' and following['raw_hex']=='70369900a736990048dde701','cached raw12s')
    for record in (previous,following):
        values=struct.unpack('<III',bytes.fromhex(record['raw_hex']))
        require(values==tuple(int(record[k],16) for k in ('begin_rva','end_exclusive','unwind_rva')),'pdata DWORD interpretation')
    require(all(r['index']!=19163 for r in requests),'19163 not cached')
    sections=anchors['sections']
    for section in sections:
        header=bytes.fromhex(section['section_header_raw_hex'])
        vs,va,rs,fo=struct.unpack_from('<IIII',header,8)
        require((vs,va,rs,fo)==(section['virtual_size'],int(section['rva'],16),section['raw_size'],section['raw_file_offset']),'retained section header fields')
    def mapping(address,size,name):
        matches=[s for s in sections if int(s['rva'],16)<=address and address+size<=int(s['rva'],16)+s['raw_size']]
        require(len(matches)==1 and matches[0]['name']==name,'unique cached raw mapping')
        s=matches[0]
        result=s['raw_file_offset']+address-int(s['rva'],16)
        require(result>=0 and result+size<=38462504,'cached file bounds')
        return result
    pdata=[s for s in sections if s['name']=='.pdata']
    require(len(pdata)==1,'one cached pdata section')
    record_rva=int(pdata[0]['rva'],16)+19163*12
    record_offset=mapping(record_rva,12,'.pdata')
    code_offset=mapping(target,24,'.text')
    require(record_rva==0x249d244 and record_offset==37139012 and code_offset==10037848,'future mapping arithmetic')
    plan=seed['metadata_plan']
    require(plan['index']==19163 and plan['rva']==hex(record_rva) and plan['file_offset']==record_offset and plan['bytes']==12,'one metadata plan')
    require(plan['required_begin']==hex(target) and plan['maximum_end']=='0x993670' and plan['maximum_full_code_bytes']==24
            and plan['missing_or_mismatch']=='unknown0code_no_search_no_fallback','plan conditional cap and refuse')
    require(previous['end_exclusive']==hex(target) and following['begin_rva']=='0x993670'
            and 0x993670-target==24,'cached neighbor bound')
    producer=raw[SUB+'produce.py'].decode('utf8')
    tree=ast.parse(producer)
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    main_source=ast.get_source_segment(producer,main)
    required=["findings.get('scope')=='retained_null_edge_and_one_metadata_slot_only'",
              "findings.get('entry_rva')==hex(ENTRY)","findings.get('branch_site_rva')==hex(BRANCH_SITE)",
              "findings.get('raw_branch_hex')==RAW_BRANCH","findings['pdata_record_index']==PDATA_INDEX",
              "findings.get('subject_source_manifest')==base_pin","findings.get('subject_producer')==producer_pin",
              "findings.get('subject_entry_seed')==seed_pin"]
    for text in required:
        require(text in main_source,'raw gate actual source field: '+text)
    require('max_code_bytes' in main_source and 'Sole fixed12B metadata read' in main_source
            and 'One complete inherited fragment of at most24B only' in main_source,'fixed read scope source witness')
    replay={
        'schema':'EU4-R75-INDEPENDENT-RAW-ENTRY-REPLAY/1','sealed':True,
        'rows_replayed':18,'owned_bytes_replayed':55,'selected_prefix_rows':15,'selected_prefix_bytes':43,
        'branch':{'site':'0x993595','raw_hex':branch.hex(),'next_rva':'0x99359b','signed_rel32':displacement,'target_rva':hex(target)},
        'frame':{'five_push_bytes':40,'sub_rsp_bytes':48,'F':'S69-0x58','prior_call':'0x97bd30','normal_balanced_return_required':True},
        'selected_null_state':{'RAX':0,'R12':0,'width_bits':64,'ZF':1,'SF':0,'PF':1,'CF':0,'OF':0,'AF':'undefined','DF':'unknown'},
        'cached_previous':previous,'cached_next':following,'selected_record19163_cached':False,
        'future_only':{'metadata_rva':hex(record_rva),'metadata_file_offset':record_offset,'metadata_bytes':12,
                       'required_begin_rva':hex(target),'maximum_end_rva':'0x993670','maximum_code_bytes':24,'code_file_offset':code_offset,
                       'requires_new_metadata_exact_begin_positive_span_disjoint_neighbors_unique_text_mapping':True,
                       'mismatch':'unknown;0code;no search/fallback','actual_record_or_target_code_read_by_review':False},
        'raw_gate_fields_replayed_from_producer_source':required,
        'retained_section_headers_replayed':len(sections),
    }
    raw_pin=write('raw-replay.json',replay)
    for path,expected in pins.items():
        read(path,expected,'after')
    guard()
    findings={
        'schema':'EU4-R75-RAW-ENTRY-INDEPENDENT-REVIEW/1','sealed':True,'passed':True,'blocking_findings':[],
        'scope':'retained_null_edge_and_one_metadata_slot_only','entry_rva':'0x993658','branch_site_rva':'0x993595',
        'raw_branch_hex':'0f84bd000000','pdata_record_index':19163,
        'subject_source_manifest':pins[SUB+'source-manifest.json'],'subject_producer':pins[SUB+'produce.py'],
        'subject_entry_seed':pins[SUB+'entry-seed.json'],'subject_prepared_final_manifest':pins[SUB+'final-manifest.json'],
        'upstream_actual_manifest':pins[UP+'manifest.json'],'upstream_capture_pin':pins[UP+'capture.json'],
        'upstream_accepted_review':pins[REV+'findings.json'],'raw_replay':raw_pin,
        'reviewer_roles':{'current':'raw-entry-only independent retained audit; not full producer/source-peer audit',
                          'R69':'War designed original source and later independently reviewed Val actual; D source-peer remains distinct',
                          'R75_author':'Val; separate source-peer audit/root actual grant required'},
        'conclusions':[
            'Retained full64 TEST followed by JE proves only the selected edge RAX=R12=0; branch target is exact0x993658.',
            'Five pushes/sub0x30 give F=S69-0x58 only with normally balanced prior call and valid uncorrupted saved/control stack.',
            'Current R13/R14/RBP/RSI match original aliases/zero only under explicit prior nonvolatile preservation; pointee contents remain unknown.',
            'Skipped nonnull rows cannot supply R8 subtraction/SAR or R71/positive-branch saved registers on this direct edge.',
            'Cached neighbors bound a possible future full fragment to24B; record19163 itself and target code remain unread and unverified.',
            'Exact one-record arithmetic agrees with cached section raw headers and all retained rows/pins.'
        ],
        'precision_notes':[
            'D was written DWORDzero before97bd30; unknown callee/aliases prevent currentD0 or header-zero claims.',
            'No independent Win64 formals, function identity, wholefunction closure, output/unit/recipient meaning, actual native result or invocation permission follows.',
            'Producer gate labels were read from exact pinned source via AST/text only; this review does not execute or fully audit producer.',
            'Source pins before/after are observed file equality, not external atomicity or ABA exclusion.',
            'Initial ad-hoc filename inspection failed before nonexistent file contents; diagnostic retained, no author retry/change.'
        ],
        'source_pins_before_after_equal':True,'admitted_flat_file_count':len(pins),'recursive_closure_claimed':False,
        'resources':{'explicit_file_read_bytes_before_after':sum(x['bytes'] for x in JOURNAL),'manual_inspection_allowance_bytes':MANUAL_ALLOWANCE,
                     'read_upper_before_retained_and_check':sum(x['bytes'] for x in JOURNAL)+MANUAL_ALLOWANCE,
                     'retained_and_filecheck_allowance_bytes':1024*1024,'stage_limit_bytes':8*1024*1024,'ordinary_file_limit_bytes':4*1024*1024,
                     'software_guard_bytes':768*1024*1024,'observed_self_peak_committed_bytes':PEAK,'accounting_scope':'explicit text reads plus stated allowances; not OS/loader IO'},
        'operations':{'PE_stat_or_open':0,'engine_body_accesses':0,'decoder_imports_or_calls':0,'author_programs_or_tests':0,
                      'game_process_accesses':0,'Frida_operations':0,'native_game_calls':0,'requests':0},
        'actual_authorized':False,'tests_authorized':False,'native_ready':False,'callable':False,'reader_adoption_allowed':False,
        'selected_effect_verified':False,'world_lease':False,'atomic_snapshot':False,'authorizes_retry':False,
        'all_shells_collected':True,'next_scope_auto_authorized':False,
    }
    finding_pin=write('findings.json',findings)
    journal_pin=write('read-journal.json',JOURNAL)
    manifest_pins=dict(pins)
    manifest_pins['work/review_r75_entry_20261016.py']=pin(Path(__file__).read_bytes())
    for name,p in [('findings.json',finding_pin),('raw-replay.json',raw_pin),('read-journal.json',journal_pin)]:
        manifest_pins[(OUT/ name).relative_to(ROOT).as_posix()]=p
    diagnostic=OUT/'inspection-filename-diagnostic.txt'
    manifest_pins[diagnostic.relative_to(ROOT).as_posix()]=pin(diagnostic.read_bytes())
    manifest_pin=write('manifest.json',{'schema':'EU4-R75-RAW-ENTRY-REVIEW-MANIFEST/1','sealed':True,'passed':True,
                                      'scope':'retained_null_edge_and_one_metadata_slot_only','source_pins':manifest_pins,
                                      'pin_count':len(manifest_pins),'engine_pins_are_upstream_metadata_only':True,
                                      'actual_authorized':False,'native_ready':False})
    print(json.dumps({'passed':True,'findings':finding_pin,'manifest':manifest_pin,'flat_files':len(pins),'peak':PEAK}))

def check():
    raw=read((OUT/'manifest.json').relative_to(ROOT).as_posix(),phase='review_check')
    manifest=parse(raw)
    for path,expected in manifest['source_pins'].items():
        read(path,expected,'review_check')
    require(manifest['pin_count']==len(manifest['source_pins']),'review count')
    result={'schema':'EU4-R75-RAW-ENTRY-REVIEW-VERIFICATION/1','passed':True,'pin_count':manifest['pin_count'],
            'manifest_pin':pin(raw),'file_only':True,'author_program_executions':0,'PE_or_engine_accesses':0,'actual_authorized':False}
    p=write('verification.json',result)
    print(json.dumps({'passed':True,'verification':p,'pins':manifest['pin_count']}))

if __name__=='__main__':
    try:
        if sys.argv[1:]==['--check']:
            check()
        else:
            require(not sys.argv[1:],'audit takes no arguments or --check')
            audit()
    except Exception:
        if OUT.exists():
            with (OUT/'failure.txt').open('x',encoding='utf8') as f:
                f.write(traceback.format_exc())
        raise
