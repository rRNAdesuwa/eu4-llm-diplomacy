"""Build a new read-only research catalog; old catalog rows are immutable data."""
from pathlib import Path
import ast
import copy
import ctypes
from ctypes import wintypes
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / 'work/candidates/war-peace-api-lookup-1375-v2'
GAME = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
OLD_PINS = {
    'index.json': {'bytes':114746,'sha256':'4d9bec2a4721fe47b32e93028ae53234e86689f44a199db262fa13becbc998d9'},
    'data-manifest.json': {'bytes':5255,'sha256':'6f4cb91a1798df84a3ff10b5f2f7244a536a30d2995124f23fe68bb2451cf874'},
    'source-manifest.json': {'bytes':8568,'sha256':'7c72ee48d57a753526c4731b894e751255eb8267fdc83b086820305770ef6bc6'},
    'war_peace_lookup.py': {'bytes':3373,'sha256':'3d983b60efdcc1711887a149b0d6203a750b99b352edd05476acbf987d799f92'},
}
MAX_FILE = 4*1024*1024
MAX_TOTAL = 32*1024*1024
MEMORY = 768*1024*1024
FALSE_FLAGS = ('callable','native_ready','sender_authorized','gameplay_effect_verified',
    'process_authenticated','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry')
DOCS = {
  "work/reports/war-peace-api-20261015-r57-independent-review/findings.json": {
    "bytes": 8026,
    "sha256": "6488ab6b689a2da53acd579bd24a7ca9e8fd65882791b3e877f1e50a8622520e"
  },
  "work/reports/war-peace-api-20261015-r57-independent-review/manifest.json": {
    "bytes": 16713,
    "sha256": "db6bb2c8987df980d6fc1d0331726eca669bccccd0af32c8a627c3740252e002"
  },
  "work/reports/war-peace-api-20261015-r57-nonzero-gold-helper/contract.json": {
    "bytes": 11067,
    "sha256": "29bbc1c652a4ca47fa83d61cbbcab65b135e805def542b1f853cae1200d95300"
  },
  "work/reports/war-peace-api-20261015-r58-independent-review/findings.json": {
    "bytes": 4475,
    "sha256": "1b7537c364fc2bebeb21670294da7e550da75378c9a2b331d1c0a0491e14b8ad"
  },
  "work/reports/war-peace-api-20261015-r58-independent-review/manifest.json": {
    "bytes": 10402,
    "sha256": "1341150111f1f040b00810ae6a9e599c7d21a9a776194bb1f6a1ff766dc39fc0"
  },
  "work/reports/war-peace-api-20261015-r58-pending-id-source/contract.json": {
    "bytes": 6262,
    "sha256": "bdf98826b1746f19d2cb0ebc301e057a6be09430cc247034b79a803388803c9c"
  },
  "work/reports/war-peace-api-20261016-r59-independent-review/findings.json": {
    "bytes": 7859,
    "sha256": "8cdc789336619307d0f75f6aed0f3761b3a43a41cabe663c99ae7763b508d382"
  },
  "work/reports/war-peace-api-20261016-r59-independent-review/manifest.json": {
    "bytes": 16411,
    "sha256": "334998a5de21586d49793db2cc294c3cca5f4cde836a41405a3f8a6b61024397"
  },
  "work/reports/war-peace-api-20261016-r59-pending-id-kind5/contract.json": {
    "bytes": 9565,
    "sha256": "c688a89a6cdb668cbbb7696558580271e2f6dc2d285e1b3dc9ac59e9394fda69"
  },
  "work/reports/war-peace-api-20261016-r60-balance-sink/contract.json": {
    "bytes": 8821,
    "sha256": "2efa516dfed890ed00b41750b64c460168aead2f9aeb67861e13724a6cbd7737"
  },
  "work/reports/war-peace-api-20261016-r60-independent-review/findings.json": {
    "bytes": 5413,
    "sha256": "d9f0059b1520355443ef8a1fc219801982adb46e68729a3cf9ed827e0fb3b979"
  },
  "work/reports/war-peace-api-20261016-r60-independent-review/manifest.json": {
    "bytes": 9866,
    "sha256": "22959db9c50e7725bf80cd2083bb7d9271c6e39e0c959b55d6fc27d5f2fb8379"
  },
  "work/reports/war-peace-api-20261016-r61-independent-review/findings.json": {
    "bytes": 5782,
    "sha256": "9f0c5819045968ba9253f55f30b92182417e1792229b822d2e2026a62926a027"
  },
  "work/reports/war-peace-api-20261016-r61-independent-review/manifest.json": {
    "bytes": 15469,
    "sha256": "c78d09582cecb9953695bde507f2182dbcf68bb26be85f84cdbd9f695f5ca1f0"
  },
  "work/reports/war-peace-api-20261016-r61-pending-id-return/contract.json": {
    "bytes": 10638,
    "sha256": "c4625af496eb7f561d6a2fe6ab5bc06c02cba779a50f3e5d8d9befd10baf26e3"
  },
  "work/reports/war-peace-api-20261016-r62-gold-recipient-generator/contract.json": {
    "bytes": 9485,
    "sha256": "b72b70f5f78c5e95f5e7984dc415dd4b4fab3ecbbaa72034e6081f0ae0e2295b"
  },
  "work/reports/war-peace-api-20261016-r62-independent-review/findings.json": {
    "bytes": 6819,
    "sha256": "8efc64a9385ca1472f6d4cf3c913f755ed8cdfffcd5082b1c55e87821aac15ad"
  },
  "work/reports/war-peace-api-20261016-r62-independent-review/manifest.json": {
    "bytes": 12593,
    "sha256": "660065e49bac4d637b609fa218058a79034fd9d5f5f7fe24c1f902f57695d42c"
  }
}
GROUPS = {
 'r57': ['work/reports/war-peace-api-20261015-r57-nonzero-gold-helper/contract.json',
         'work/reports/war-peace-api-20261015-r57-independent-review/findings.json',
         'work/reports/war-peace-api-20261015-r57-independent-review/manifest.json'],
 'r58': ['work/reports/war-peace-api-20261015-r58-pending-id-source/contract.json',
         'work/reports/war-peace-api-20261015-r58-independent-review/findings.json',
         'work/reports/war-peace-api-20261015-r58-independent-review/manifest.json'],
 'r59': ['work/reports/war-peace-api-20261016-r59-pending-id-kind5/contract.json',
         'work/reports/war-peace-api-20261016-r59-independent-review/findings.json',
         'work/reports/war-peace-api-20261016-r59-independent-review/manifest.json'],
 'r60': ['work/reports/war-peace-api-20261016-r60-balance-sink/contract.json',
         'work/reports/war-peace-api-20261016-r60-independent-review/findings.json',
         'work/reports/war-peace-api-20261016-r60-independent-review/manifest.json'],
 'r61': ['work/reports/war-peace-api-20261016-r61-pending-id-return/contract.json',
         'work/reports/war-peace-api-20261016-r61-independent-review/findings.json',
         'work/reports/war-peace-api-20261016-r61-independent-review/manifest.json'],
 'r62': ['work/reports/war-peace-api-20261016-r62-gold-recipient-generator/contract.json',
         'work/reports/war-peace-api-20261016-r62-independent-review/findings.json',
         'work/reports/war-peace-api-20261016-r62-independent-review/manifest.json'],
}

class PMC(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[
        (x,ctypes.c_size_t) for x in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
        'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage',
        'PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True)
p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE
p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
peak=0
reads=[]

def guard():
    global peak
    x=PMC();x.cb=ctypes.sizeof(x)
    assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
    peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage)
    assert peak<=MEMORY

def pin(raw):
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def read(path,expected=None):
    guard();a=path.stat();assert a.st_size<=MAX_FILE
    assert sum(x['bytes'] for x in reads)+a.st_size<=MAX_TOTAL
    raw=path.read_bytes();b=path.stat()
    assert (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns) and len(raw)==a.st_size
    if expected is not None:assert pin(raw)==expected,(path,pin(raw),expected)
    reads.append(dict(path=str(path.relative_to(ROOT)).replace('\\','/'),**pin(raw)))
    guard();return raw

def pairs(items):
    result={}
    for key,value in items:
        assert key not in result,'duplicate_json_key'
        result[key]=value
    return result

def parse(raw):
    def invalid(_):raise ValueError('nonfinite_json_number')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)

def write(name,value):
    raw=(json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
    assert len(raw)<=MAX_FILE
    with (HERE/name).open('xb') as f:f.write(raw)
    guard();return pin(raw)

def pointer(doc,where):
    assert where.startswith('/')
    for part in where.split('/')[1:]:
        part=part.replace('~1','/').replace('~0','~')
        doc=doc[int(part)] if isinstance(doc,list) else doc[part]
    return doc

def contains_pin(value,path,expected):
    if isinstance(value,dict):
        if path in value and value[path]==expected:return True
        return any(contains_pin(x,path,expected) for x in value.values())
    if isinstance(value,list):return any(contains_pin(x,path,expected) for x in value)
    return False

def main():
    claim=write('build-claim.json',dict(schema='EU4-LOOKUP-V3-BUILD-CLAIM/1',
        game_sha256=GAME,source_budget=MAX_TOTAL,memory_guard=MEMORY,PE_reads=0,
        decoder_imports=0,game_process_access=0,author_program_runs=0,native_calls=0,old_tests=0))
    try:
        oldraw={name:read(OLD/name,pn) for name,pn in OLD_PINS.items()}
        old=parse(oldraw['index.json']);oldmanifest=parse(oldraw['data-manifest.json'])
        assert len(old['entries'])==50 and len(oldmanifest['sources'])==26
        assert pin(oldraw['index.json'])==oldmanifest['index']
        assert old['game_sha256']==oldmanifest['game_sha256']==GAME
        docs={};sources=copy.deepcopy(oldmanifest['sources'])
        for path,expected in {**sources,**DOCS}.items():
            docs[path]=parse(read(ROOT/path,expected))
            sources[path]=expected
        assert len(DOCS)==18 and len(sources)==44
        for group,(contract,review,reviewmanifest) in GROUPS.items():
            assert docs[contract]['sealed'] is True and docs[contract]['game_sha256']==GAME
            assert docs[review]['sealed'] is True and docs[review]['passed'] is True
            assert docs[review]['blocking_findings']==[]
            assert docs[reviewmanifest]['sealed'] is True
            assert contains_pin(docs[reviewmanifest],contract,DOCS[contract]),group
        def ref(path,where):return dict(path=path,json_pointer=where,**sources[path])
        def evidence(group,pointers):
            contract,review,reviewmanifest=GROUPS[group]
            return ([ref(contract,x) for x in pointers]+[ref(review,'/passed'),
                    ref(review,'/subject_manifest'),ref(reviewmanifest,'/schema')])
        def entry(identifier,rva,title,summary,params,returns,aliases,unknowns,owned,borrowed,evidence,ranges,**extra):
            return dict(id=identifier,rva=rva,kind='function',stage='static',actions=['peace'],
                title=title,summary=summary,stage_scope='Retained fixed-PE machine contract only; no observed business execution or callable authority.',
                signature=dict(status='partial_static',complete_prototype='unknown',parameters=params,returns=returns),
                ownership=dict(owned=owned,borrowed=borrowed),call_sites=[],aliases=aliases,
                unresolved=unknowns,evidence=evidence,owned_code_ranges=ranges,
                independent_review_status='full_independent_file_audit_passed_for_each_retained_scope',
                **extra,**{x:False for x in FALSE_FLAGS})
        additions=[
          entry('peace.gold_component_helper','0x9b46a0','Gold-term caller component helper: partial machine contract',
            'Consumes opaque component RCX, DWORD-key pointer RDX and QWORD payload R8. Uses signed16 payload slot, '
            'resource-shaped calls and a direct scaled add/clamp at selected object+bd4. No local component+30 read; '
            'this is not a positive-gold transfer oracle.',
            ['RCX=opaque component S','RDX=addressable DWORD Kptr; re-read after callees, values need not match',
             'R8=QWORD H; only signed16 bits32..47 index module233d8d0 DB+118',
             'Incoming R9/XMM unknown; two resource-shaped call sites explicitly set R9D=0'],
            'One normal RET, not normalized or typed. Caller reloads its own values; helper return is not a confirmed effect.',
            ['gold component','nonzero gold helper','9b46a0','bd4 scaled add'],
            ['Complete prototype, object class/fullhandles/slot bounds and lifetime remain unknown.',
             'Resource-shaped338540/339c10/3387f0 bodies and units/direction remain unbound.',
             'Component+30 nonzero at caller does not prove positive Kptr or gold units.',
             'TLS/module lazy initialization, returned aliases, exception/allocator and final effects remain unknown.'],
            ['Selected local stack scratch only; no game-object ownership transfer proved.'],
            ['Opaque component, Kptr, DB-selected A/B, module/TLS and unfollowed callees.'],
            evidence('r57',['/entry','/input_provenance','/slot_object_selection','/numeric_dataflow','/reader_consequence']),
            [['0x9b46a0','0x9b4a65']],scope_kind='bounded_function_machine_contract'),
          entry('shared.scalar_add_clamp','0x3383b0','Receiver+BB0 scalar add followed by signed clamp',
            'Re-reads DWORD[M] after optional calls, stores add_mod32(C+bb0,input), then applies signed +/-1000000000 clamp. '
            'Conditional module-byte writes and B+388 OR40 are additional effects. This is not a pure helper or a returned balance.',
            ['RCX=opaque receiver C, retained in RDI','RDX=DWORD pointer M, retained in RSI',
             'Incoming R8/R9 may be consumed by unfollowed callees; not a complete signature'],
            'RAX is path-dependent: unfollowed call return, selected QWORD>>32, or B pointer. It is not the new balance or a BOOL.',
            ['BB0 add','scalar clamp','wrapped addition','3383b0','balance-shaped sink'],
            ['Input/receiver class, complete layout, currency units and business settlement are unknown.',
             '32bit addition wraps before the signed clamp; no pre-add overflow prevention.',
             'Callee aliases may change M or pointed fields; later B+388 may alias unknown storage.',
             '16bit slot comparison is not a full handle/identity check; lifetime/exception behavior unknown.'],
            ['Only selected local stack storage; no receiver allocation or release established.'],
            ['Opaque C/M, module globals, returned G/B pointers and unfollowed callees.'],
            evidence('r60',['/scope','/observations','/writes','/unknowns']),
            [['0x3383b0','0x3384b2']],scope_kind='bounded_function_machine_contract'),
          entry('shared.pending_kind_counter_path','0x771be0','Conditional pending-kind5 postincrement path; full function unknown',
            'CONDITIONAL_PATH only: EDX=5 and R8D=ffffffff. Three owned ranges compose selected slot5 growth/read and '
            'postincrement; unselected gap10 is not read. If oldV!=ffffffff, writes V+1 modulo32 and returns zeroextendedoldV. '
            'If oldV==ffffffff, writes0 before unknown error call/INT3. Not a confirmed native request-ID binding.',
            ['Known entry771be0 with RCX=opaque receiver S, EDX=5, R8D=0xffffffff',
             'Original R9B saved to entryQ+20; growth path may overwrite that cell with DWORD1',
             'Selected path uses S+2508/+2510/+2518 DWORD buffer; count/capacity validity remains a premise',
             'Callee-dependent volatile registers and generic EBP!=ffffffff path remain unknown'],
            'Conditional normal composition returns zeroextendedoldV only for V!=ffffffff, after slot5 DWORD write(V+1 mod32). '
            'FFFFFFFF has no proved normal return; it writes0 then calls unknown1a36038 and reachesINT3 if returned.',
            ['kind5 conditional path','pending ID source','postincrement','771be0','oldV counter'],
            ['Three fragments are not separate callable entries or a complete function contract.',
             'Gap[771cbd,771cc7)10B and generic other-input paths are unselected.',
             'Valid readable/writable buffer, normal callee ABI/stack discipline and growth alias/termination assumptions remain.',
             'OldV may be0 or signbit-set; no positive ID rule, uniqueness, reset, bridge request-ID mapping or retry authority.'],
            ['Selected stack frame and transient local DWORD; no buffer ownership/retirement proved.'],
            ['Opaque receiver buffer and42d850/error-callee aliases; no world lease.'],
            evidence('r58',['/scope','/observations'])+evidence('r59',['/scope','/inherited_state','/EAX_source','/selected_exit'])+
            evidence('r61',['/scope','/post_increment','/normal_composition','/max_bitpattern_path']),
            [['0x771be0','0x771c06'],['0x771c06','0x771cbd'],['0x771cc7','0x771cf6']],
            scope_kind='conditional_path',conditional_inputs={'EDX':5,'R8D':'0xffffffff'},
            unselected_code_gaps=[['0x771cbd','0x771cc7']],owned_code_unique_bytes=268,
            whole_function_closed=False,independent_fragment_callable=False),
          entry('peace.generated_record_body','0x9844d0','Generated 12-byte records: units and recipients unknown',
            'Reads T after97b2c0 and D after993570; neither pre-call local initialization nor actual helper out-write is proved. '
            'Simple branch forms(T,freshW18). Complex branch scales signed DWORD components, copiesQWORD4, '
            'appends only signedlow32EBP>0, and uses16bit slot comparison plus ADD32 remainder.994f00 may change finalH/records.',
            ['RCX=opaque W saved/reloaded from entryQ+8','RDX=opaque outputheader H, retained in R14',
             'R8/R9 incoming unknown; caller XMM0 zero is local fact, first external call occurs before local use',
             'T=post97b2c0 DWORD atQ+18; D=post993570 DWORD atQ+20; no typed outparam assumption'],
            'RET984775 does not normalize RAX. Caller replaces RAX with its own header end; final output/membership is unknown after994f00.',
            ['gold recipient generator candidate','generated records','9844d0','record allocation','amount distribution'],
            ['No currency/amount units/recipient class/direction/fullhandle or complete recipient set proved.',
             'Low32 signed append gate, mixed IDIV widths and ADD32 wrapping are machine arithmetic, not gold conservation.',
             'Unknown97b2c0/975110/993570/996e30/994f00 can alter data and headers.',
             'Allocator/error/exception/cleanup ownership and world lifetime remain unknown.'],
            ['Selected local frame and zeroed temporary three-QWORD header only; resulting payload ownership unknown.'],
            ['Opaque W/H, postcall temp buffers, output payloads and unfollowed callees.'],
            evidence('r62',['/entry','/input_machine_contract','/first_scalar_and_dispatch','/simple_branch',
                '/per_record_machine_construction','/remainder_candidate_and_postprocess','/cleanup_and_return']),
            [['0x9844d0','0x98477c']],scope_kind='bounded_function_machine_contract'),
        ]
        duplicates=[x['rva'] for x in additions if any(x['rva']==y['rva'] for y in old['entries'])]
        assert not duplicates,'existing RVA would require a separate supplement, not modifying old rows'
        index=copy.deepcopy(old);index['entries']=sorted(index['entries']+additions,key=lambda x:x['id'])
        oldmap={x['id']:x for x in old['entries']};newmap={x['id']:x for x in index['entries']}
        assert all(newmap[k]==v for k,v in oldmap.items()) and len(index['entries'])==54
        proof=[]
        for key,row in oldmap.items():
            canonical=json.dumps(row,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()
            proof.append(dict(id=key,rva=row['rva'],canonical_row_sha256=pin(canonical)['sha256'],data_equal=True))
        used=set()
        for row in index['entries']:
            for flag in ('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated'):
                assert row[flag] is False
            for ref in row['evidence']:
                assert {k:ref[k] for k in ('bytes','sha256')}==sources[ref['path']]
                pointer(docs[ref['path']],ref['json_pointer']);used.add(ref['path'])
        assert used==set(sources)
        indexpin=write('index.json',index)
        datap=write('data-manifest.json',dict(schema='EU4-WAR-PEACE-LOOKUP-DATA-MANIFEST/1',
            version='1.37.5',game_sha256=GAME,scope='offline_selected_evidence_only',index=indexpin,sources=sources))
        write('lineage-proof.json',dict(schema='EU4-LOOKUP-V3-LINEAGE/1',sealed=True,
            original50_data_equal=True,original50=proof,duplicates_with_added_RVAs=duplicates,
            original_selected_sources=26,new_selected_sources=18,selected_sources=44,
            old_pins=OLD_PINS,new_pins=DOCS,R63_included=False,
            query_engine='exact frozen Python file-query engine, not Capstone decoder',
            source_graph_is_flat_selected_JSON_not_transitive_PE_engine_authentication=True))
        oldcli=oldraw['war_peace_lookup.py'].decode()
        cli=oldcli.replace("DATA_SHA = '"+OLD_PINS['data-manifest.json']['sha256']+"'", "DATA_SHA = '"+datap['sha256']+"'")
        cli=cli.replace('tool_revision=2','tool_revision=3').replace('revision 2','revision 3')
        cli=cli.replace("'gameplay_effect_verified', 'process_authenticated')", "'gameplay_effect_verified', 'process_authenticated',\n         'selected_effect_verified', 'world_lease', 'atomic_snapshot', 'authorizes_retry')")
        cli=cli.replace('original_engine_source_guard_before_and_after=True)',
            'original_engine_source_guard_before_and_after=True,\n                      selected_effect_verified=False, world_lease=False,\n                      atomic_snapshot=False, authorizes_retry=False)')
        assert cli!=oldcli and datap['sha256'] in cli
        with (HERE/'war_peace_lookup.py').open('xb') as f:f.write(cli.encode())
        oldnodes={x.name:ast.dump(x,include_attributes=False) for x in ast.parse(oldcli).body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
        newnodes={x.name:ast.dump(x,include_attributes=False) for x in ast.parse(cli).body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
        changed=sorted(k for k in oldnodes if oldnodes[k]!=newnodes[k])
        assert changed==['main','run','unknown']
        write('source-delta.json',dict(schema='EU4-LOOKUP-V3-QUERY-DELTA/1',old_cli=OLD_PINS['war_peace_lookup.py'],
            new_cli=pin(cli.encode()),changed_function_AST=changed,
            unchanged_function_class_AST=sorted(k for k in oldnodes if oldnodes[k]==newnodes[k]),
            substantive_guard_logic_changed=False,
            allowed_changes=['DATA_SHA constant','revision2->3 metadata/help','constant false additional output metadata/FLAGS'],
            frozen_query_engine_SHA='d4237d98c58e89be9419ff736f01d97f5fde0129c07c5c7f778baf010071746e'))
        for name,expected in OLD_PINS.items():read(OLD/name,expected)
        for path,expected in DOCS.items():read(ROOT/path,expected)
        guard()
        write('build-receipt.json',dict(schema='EU4-LOOKUP-V3-BUILD-RECEIPT/1',passed=True,
            index=indexpin,data_manifest=datap,entries=54,selected_sources=44,
            new_rows=4,old50_data_equal=True,read_journal=reads,explicit_source_read_bytes=sum(x['bytes'] for x in reads),
            source_budget=MAX_TOTAL,self_peak_bytes=peak,memory_guard=MEMORY,
            PE_decoder_oldCLI_oldtests_game_native_requests=0,claim=claim,all_shells_collected=True))
        print(json.dumps(dict(entries=54,sources=44,index=indexpin,data_manifest=datap,
            CLI=pin(cli.encode()),source_bytes=sum(x['bytes'] for x in reads),self_peak_bytes=peak)))
    except Exception as exc:
        write('build-failure.json',dict(type=type(exc).__name__,detail=str(exc),read_journal=reads,
            explicit_source_read_bytes=sum(x['bytes'] for x in reads),self_peak_bytes=peak))
        raise

if __name__=='__main__':main()
